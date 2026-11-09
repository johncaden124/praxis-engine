extends Node
## Autoload bridge between the game and the real vault.
##
## Every action goes through `_scripts/learn.py --json --headless` via
## OS.execute (on a worker thread so the UI never freezes), and the game
## re-reads `learn status --json` afterwards. The CLI and the game share the
## same files, so changes made in the terminal show up here within seconds.

signal status_changed(status: Dictionary)
signal message(text: String, level: String)
signal busy_changed(busy: bool)

var vault_root: String = ""
var python_bin: String = "python3"
var status: Dictionary = {}
var state: Dictionary = {}
var config: Dictionary = {}

var _busy := 0
var _running := false
var _queue: Array = []
var _threads: Array = []
var _state_mtime := 0
var _watch: Timer


func _ready() -> void:
	vault_root = _find_vault_root()
	config = _read_json(path("_scripts/config.json"))
	python_bin = _find_python()
	_watch = Timer.new()
	_watch.wait_time = 2.5
	_watch.autostart = true
	_watch.timeout.connect(_check_state_file)
	add_child(_watch)
	refresh()


func _exit_tree() -> void:
	for t in _threads:
		if t.is_started():
			t.wait_to_finish()


# ------------------------------------------------------------------ paths

func _find_vault_root() -> String:
	var env := OS.get_environment("PRAXIS_ROOT")
	if env != "" and DirAccess.dir_exists_absolute(env):
		return env
	var saved := "user://praxis_root.txt"
	if FileAccess.file_exists(saved):
		var p := FileAccess.get_file_as_string(saved).strip_edges()
		if DirAccess.dir_exists_absolute(p):
			return p
	# res:// is ~/Learning/game/ when run from the project folder
	var game_dir := ProjectSettings.globalize_path("res://").rstrip("/\\")
	var root := game_dir.get_base_dir()
	if FileAccess.file_exists(root.path_join("_scripts/learn.py")):
		return root
	# exported build: look next to the executable
	var exe_dir := OS.get_executable_path().get_base_dir()
	for cand in [exe_dir, exe_dir.get_base_dir(), OS.get_environment("HOME").path_join("Learning")]:
		if FileAccess.file_exists(String(cand).path_join("_scripts/learn.py")):
			return cand
	return root


func path(rel: String) -> String:
	return vault_root.path_join(rel)


func _find_python() -> String:
	var custom := str(config.get("python_bin", ""))
	if custom != "" and FileAccess.file_exists(custom):
		return custom
	if OS.get_name() == "Windows":
		return "python"
	for p in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/Library/Frameworks/Python.framework/Versions/Current/bin/python3", "/usr/bin/python3"]:
		if FileAccess.file_exists(p):
			return p
	return "python3"


# ------------------------------------------------------------------ files

func _read_json(p: String) -> Dictionary:
	if not FileAccess.file_exists(p):
		return {}
	var data = JSON.parse_string(FileAccess.get_file_as_string(p))
	return data if data is Dictionary else {}


func read_text(rel: String) -> String:
	var p := path(rel)
	if not FileAccess.file_exists(p):
		return ""
	return FileAccess.get_file_as_string(p)


func write_text(rel: String, text: String) -> bool:
	var p := path(rel)
	DirAccess.make_dir_recursive_absolute(p.get_base_dir())
	var f := FileAccess.open(p, FileAccess.WRITE)
	if f == null:
		emit_signal("message", "Could not write %s" % rel, "error")
		return false
	f.store_string(text)
	f.close()
	return true


func list_files(rel_dir: String, ext: String) -> PackedStringArray:
	var out := PackedStringArray()
	var d := DirAccess.open(path(rel_dir))
	if d == null:
		return out
	for f in d.get_files():
		if f.ends_with(ext):
			out.append(f)
	out.sort()
	return out


func open_external(target: String) -> void:
	OS.shell_open(target)


func open_vault_file(rel: String) -> void:
	OS.shell_open(path(rel))


func obsidian_open(rel: String) -> void:
	var vault := str(config.get("obsidian_vault_name", vault_root.get_file()))
	OS.shell_open("obsidian://open?vault=%s&file=%s" % [vault.uri_encode(), rel.uri_encode()])


# ------------------------------------------------------------------ CLI bridge

func is_busy() -> bool:
	return _busy > 0


## Run `learn.py <args> --json --headless` on a worker thread.
## `cb` receives the parsed Dictionary. Status is refreshed afterwards.
func learn(args: Array, cb: Callable = Callable(), refresh_after: bool = true, quiet: bool = false) -> void:
	var argv := PackedStringArray([path("_scripts/learn.py")])
	for a in args:
		argv.append(str(a))
	argv.append("--json")
	argv.append("--headless")
	_run(argv, cb, refresh_after, quiet)


## Commands run one at a time (they read-modify-write the same files), so
## requests made while another is running wait in a queue.
func _run(argv: PackedStringArray, cb: Callable, refresh_after: bool, quiet: bool) -> void:
	# collapse duplicate status refreshes
	if argv.size() >= 2 and argv[1] == "status":
		for job in _queue:
			if job["argv"].size() >= 2 and job["argv"][1] == "status":
				return
	_queue.append({"argv": argv, "cb": cb, "refresh": refresh_after, "quiet": quiet})
	_busy += 1
	emit_signal("busy_changed", true)
	_pump()


func _pump() -> void:
	if _running or _queue.is_empty():
		return
	var job: Dictionary = _queue.pop_front()
	_running = true
	var t := Thread.new()
	_threads.append(t)
	t.start(_thread_exec.bind(t, job["argv"], job["cb"], job["refresh"], job["quiet"]))


func _thread_exec(t: Thread, argv: PackedStringArray, cb: Callable, refresh_after: bool, quiet: bool) -> void:
	var output: Array = []
	var code := OS.execute(python_bin, argv, output, false)
	var text := ""
	for chunk in output:
		text += str(chunk)
	call_deferred("_on_exec_done", t, code, text, cb, refresh_after, quiet)


func _on_exec_done(t: Thread, code: int, text: String, cb: Callable, refresh_after: bool, quiet: bool) -> void:
	t.wait_to_finish()
	_threads.erase(t)
	_running = false
	_busy = max(0, _busy - 1)
	emit_signal("busy_changed", _busy > 0)
	var result: Dictionary = _parse_output(text)
	if result.is_empty():
		result = {"ok": false, "error": "No JSON from learn.py (exit %d)" % code, "raw": text}
		if code == -1:
			result["error"] = "Could not run Python at '%s'. Set python_bin in _scripts/config.json." % python_bin
	if not quiet:
		var msg := str(result.get("message", result.get("error", "")))
		if msg != "":
			var ok_flag = result.get("ok", result.get("success", true))
			emit_signal("message", msg, "info" if ok_flag else "error")
	if cb.is_valid():
		cb.call(result)
	if refresh_after:
		refresh()
	_pump()


func _parse_output(text: String) -> Dictionary:
	var lines := text.strip_edges().split("\n")
	for i in range(lines.size() - 1, -1, -1):
		var line := lines[i].strip_edges()
		if line.begins_with("{"):
			var data = JSON.parse_string(line)
			if data is Dictionary:
				return data
	var whole = JSON.parse_string(text)
	return whole if whole is Dictionary else {}


func refresh() -> void:
	learn(["status"], _on_status, false, true)


func _on_status(result: Dictionary) -> void:
	if not result.get("ok", false):
		emit_signal("message", "Status failed: %s" % str(result.get("error", result.get("raw", "?"))).left(300), "error")
		return
	status = result
	state = result.get("state", {})
	_state_mtime = FileAccess.get_modified_time(path("_scripts/state.json"))
	emit_signal("status_changed", status)


func _check_state_file() -> void:
	if is_busy():
		return
	var m := FileAccess.get_modified_time(path("_scripts/state.json"))
	if m != 0 and m != _state_mtime:
		_state_mtime = m
		refresh()


# ------------------------------------------------------------------ helpers

func bandwidth() -> float:
	return float(state.get("cognitive_bandwidth", 0))


func max_bandwidth() -> float:
	return float(state.get("max_bandwidth", 100))


## Seconds elapsed since a naive local ISO timestamp (as written by learn.py).
func seconds_since(iso_local: String) -> int:
	if iso_local == "":
		return 0
	var now_local := Time.get_datetime_string_from_system(false, false)
	return int(Time.get_unix_time_from_datetime_string(now_local) - Time.get_unix_time_from_datetime_string(iso_local))
