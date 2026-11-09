extends HSplitContainer
## Room [1] Automation Grid & Code IDE — the Coding & AI track.
## Left: animated grid. Right: CodeEdit on real files in ~/Learning/code/drones/.

const UI = preload("res://scripts/UI.gd")
const GridController = preload("res://scripts/GridController.gd")

const DRONE_DIR := "code/drones"
const SPEEDS := [1.0, 2.0, 5.0]
const PY_KEYWORDS := ["False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]
const PY_BUILTINS := ["print", "range", "len", "sum", "min", "max", "abs", "round", "list", "dict", "set", "tuple", "str", "int", "float", "enumerate", "zip", "sorted", "map", "filter", "any", "all", "open", "isinstance", "self"]
const API := ["move", "scan", "harvest_data", "clean_outlier", "run_abm_step", "plot_csv", "submit_result", "get_pos", "world_size", "bandwidth", "log", "dataset_path", "graph", "node_pos", "is_wall", "training_data", "test_inputs", "abm_grid"]

var grid: GridController
var code: CodeEdit
var terminal: RichTextLabel
var file_pick: OptionButton
var challenge_pick: OptionButton
var speed_pick: OptionButton
var title_label: Label
var info_label: Label
var bw_bar: ProgressBar
var bw_label: Label
var plot_rect: TextureRect
var run_btn: Button
var test_btn: Button

var current_file := ""
var current_challenge := "c1_loops"
var _challenges: Array = []
var _dirty := false
var _pending_result: Dictionary = {}


func _ready() -> void:
	split_offset = 80
	_build_left()
	_build_right()
	GameManager.status_changed.connect(_on_status)
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)
	_reload_files()


func _build_left() -> void:
	var left := UI.vbox(8)
	UI.expand(left)
	left.custom_minimum_size = Vector2(520, 0)
	var top := UI.hbox()
	title_label = UI.title("Challenge", 20)
	top.add_child(title_label)
	top.add_child(UI.spacer())
	top.add_child(UI.label("Speed", 13, UI.MUTED))
	speed_pick = OptionButton.new()
	for s in SPEEDS:
		speed_pick.add_item("%dx" % int(s))
	speed_pick.item_selected.connect(func(i): grid.set_speed(SPEEDS[i]))
	top.add_child(speed_pick)
	left.add_child(top)
	info_label = UI.label("", 13, UI.MUTED, true)
	left.add_child(info_label)

	grid = GridController.new()
	UI.expand(grid)
	grid.frame_played.connect(_on_frame)
	grid.playback_finished.connect(_on_playback_done)
	left.add_child(UI.expand(UI.panel(grid, UI.BG)))

	var bwrow := UI.hbox()
	bwrow.add_child(UI.header("Cognitive Bandwidth", UI.ACCENT))
	bw_bar = UI.bar(UI.ACCENT, 100, 100, 12)
	UI.expand(bw_bar, true, false)
	bwrow.add_child(bw_bar)
	bw_label = UI.label("100 / 100", 13, UI.TEXT)
	bwrow.add_child(bw_label)
	left.add_child(bwrow)

	plot_rect = TextureRect.new()
	plot_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	plot_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	plot_rect.custom_minimum_size = Vector2(0, 200)
	plot_rect.visible = false
	left.add_child(plot_rect)
	add_child(left)


func _build_right() -> void:
	var right := UI.vbox(8)
	UI.expand(right)
	right.custom_minimum_size = Vector2(520, 0)

	var row1 := UI.hbox(8)
	row1.add_child(UI.header("Challenge"))
	challenge_pick = OptionButton.new()
	UI.expand(challenge_pick, true, false)
	challenge_pick.item_selected.connect(_on_challenge_selected)
	row1.add_child(challenge_pick)
	right.add_child(row1)

	var row2 := UI.hbox(8)
	row2.add_child(UI.header("File"))
	file_pick = OptionButton.new()
	UI.expand(file_pick, true, false)
	file_pick.item_selected.connect(func(i): _load_file(file_pick.get_item_text(i)))
	row2.add_child(file_pick)
	row2.add_child(UI.button("New", _new_file, "Create a new drone script"))
	row2.add_child(UI.button("Save", _save, "Save (Ctrl/Cmd+S)"))
	row2.add_child(UI.button("Open externally", _open_external, "Open in your default editor (VS Code)"))
	right.add_child(row2)

	code = CodeEdit.new()
	UI.expand(code)
	code.custom_minimum_size = Vector2(0, 320)
	code.gutters_draw_line_numbers = true
	code.indent_automatic = true
	code.indent_use_spaces = true
	code.indent_size = 4
	code.auto_brace_completion_enabled = true
	code.highlight_current_line = true
	code.draw_tabs = false
	code.syntax_highlighter = _python_highlighter()
	code.text_changed.connect(func(): _dirty = true)
	right.add_child(code)

	var row3 := UI.hbox(8)
	run_btn = UI.accent_button("▶  Run & Commit", _run.bind(false))
	test_btn = UI.button("Test run (no commit, no cost)", _run.bind(true))
	row3.add_child(run_btn)
	row3.add_child(test_btn)
	row3.add_child(UI.spacer())
	row3.add_child(UI.button("Clear", func(): terminal.clear()))
	right.add_child(row3)

	terminal = RichTextLabel.new()
	terminal.bbcode_enabled = true
	terminal.scroll_following = true
	terminal.selection_enabled = true
	terminal.custom_minimum_size = Vector2(0, 190)
	right.add_child(terminal)
	_print("[color=#39d98a]PRAXIS STATION TERMINAL[/color] — drone scripts live in [b]~/Learning/code/drones/[/b]. Edit here or in VS Code.")
	add_child(right)


func _python_highlighter() -> CodeHighlighter:
	var h := CodeHighlighter.new()
	h.number_color = Color("f78c6c")
	h.symbol_color = Color("89ddff")
	h.function_color = Color("82aaff")
	h.member_variable_color = Color("e6edf3")
	for k in PY_KEYWORDS:
		h.add_keyword_color(k, Color("c792ea"))
	for k in PY_BUILTINS:
		h.add_keyword_color(k, Color("ffcb6b"))
	for k in API:
		h.add_keyword_color(k, UI.ACCENT)
	h.add_color_region("#", "", Color("5c6f84"), true)
	h.add_color_region("\"\"\"", "\"\"\"", Color("8fbf7f"))
	h.add_color_region("\"", "\"", Color("c3e88d"))
	h.add_color_region("'", "'", Color("c3e88d"))
	return h


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_S and (event.ctrl_pressed or event.meta_pressed):
		_save()
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------ files & challenges

func _reload_files(select: String = "") -> void:
	file_pick.clear()
	var files := GameManager.list_files(DRONE_DIR, ".py")
	for f in files:
		file_pick.add_item(f)
	var want := select if select != "" else current_file
	if want == "" and files.size() > 0:
		want = files[0]
	for i in range(file_pick.item_count):
		if file_pick.get_item_text(i) == want:
			file_pick.select(i)
			_load_file(want)
			return


func _load_file(fname: String) -> void:
	if _dirty and current_file != "":
		_save()
	current_file = fname
	code.text = GameManager.read_text(DRONE_DIR.path_join(fname))
	code.clear_undo_history()
	_dirty = false


func _save() -> void:
	if current_file == "":
		return
	if GameManager.write_text(DRONE_DIR.path_join(current_file), code.text):
		_dirty = false
		_print("[color=#8b98a7]saved %s[/color]" % current_file)


func _new_file() -> void:
	var n := 1
	var fname := "my_drone.py"
	while FileAccess.file_exists(GameManager.path(DRONE_DIR.path_join(fname))):
		n += 1
		fname = "my_drone_%d.py" % n
	GameManager.write_text(DRONE_DIR.path_join(fname), "from station_api import move, scan, harvest_data, log, submit_result\n\nlog(\"Hello, grid!\")\nharvest_data()\nmove(\"N\")\n")
	_reload_files(fname)


func _on_status(st: Dictionary) -> void:
	var s: Dictionary = st.get("state", {})
	var bw := float(s.get("cognitive_bandwidth", 0))
	var mx := float(s.get("max_bandwidth", 100))
	bw_bar.max_value = mx
	bw_bar.value = bw
	bw_label.text = "%.0f / %.0f" % [bw, mx]
	var effects: Dictionary = st.get("effects", {})
	grid.set_speed(SPEEDS[speed_pick.selected] * float(effects.get("clock_speed", 1.0)))
	_challenges = st.get("challenges", [])
	var keep := current_challenge
	challenge_pick.clear()
	var idx := 0
	for c in _challenges:
		var tag := "✅ " if c.get("passed", false) else ("🔒 " if c.get("locked", false) else "◻ ")
		challenge_pick.add_item("%s%s — %s" % [tag, c.get("id", ""), c.get("title", "")])
		challenge_pick.set_item_metadata(idx, c.get("id", ""))
		challenge_pick.set_item_disabled(idx, c.get("locked", false))
		idx += 1
	challenge_pick.add_item("◻ free — Free play sandbox (grid %d×%d)" % [int(effects.get("grid_size", 3)), int(effects.get("grid_size", 3))])
	challenge_pick.set_item_metadata(idx, "free")
	for i in range(challenge_pick.item_count):
		if str(challenge_pick.get_item_metadata(i)) == keep:
			challenge_pick.select(i)
			_show_challenge(keep, false)
			return
	if challenge_pick.item_count > 0:
		challenge_pick.select(0)
		_show_challenge(str(challenge_pick.get_item_metadata(0)), false)


func _on_challenge_selected(i: int) -> void:
	_show_challenge(str(challenge_pick.get_item_metadata(i)), true)


func _show_challenge(cid: String, load_starter: bool) -> void:
	var changed := cid != current_challenge or grid.tiles.is_empty()
	current_challenge = cid
	var info := {}
	for c in _challenges:
		if c.get("id", "") == cid:
			info = c
	title_label.text = str(info.get("title", "Free Play"))
	var bench = info.get("benchmark", null)
	info_label.text = "Stage %s · %s%s" % [str(info.get("stage", "-")), "passes benchmark `%s`" % bench if bench != null else "no benchmark", " · LOCKED: needs %s" % ", ".join(PackedStringArray(info.get("requires_tech", []))) if info.get("locked", false) else ""]
	if load_starter and info.has("starter"):
		var starter := str(info["starter"])
		if FileAccess.file_exists(GameManager.path(DRONE_DIR.path_join(starter))):
			_reload_files(starter)
	if changed and not grid.is_playing():
		GameManager.learn(["world", cid], _on_world, false, true)


func _on_world(r: Dictionary) -> void:
	if r.get("ok", false) and not grid.is_playing():
		grid.set_world(r.get("world", {}))


func _open_external() -> void:
	if current_file != "":
		GameManager.open_vault_file(DRONE_DIR.path_join(current_file))


# ------------------------------------------------------------------ run

func _run(dry: bool) -> void:
	if current_file == "":
		_print("[color=#ff5c7a]No drone script selected.[/color]")
		return
	_save()
	run_btn.disabled = true
	test_btn.disabled = true
	plot_rect.visible = false
	_print("\n[color=#4fc3f7]$ learn run-drone %s %s%s[/color]" % [current_file, current_challenge, " --dry-run" if dry else ""])
	var args := ["run-drone", current_file, current_challenge]
	if dry:
		args.append("--dry-run")
	GameManager.learn(args, _on_run_result, not dry, true)


func _on_run_result(r: Dictionary) -> void:
	_pending_result = r
	if r.has("world"):
		grid.set_world(r["world"])
	var frames: Array = r.get("frames", [])
	if frames.is_empty():
		_on_playback_done()
		return
	grid.play(frames, SPEEDS[speed_pick.selected] * float(GameManager.status.get("effects", {}).get("clock_speed", 1.0)))


func _on_frame(f: Dictionary) -> void:
	var color := "#e6edf3"
	match str(f.get("action", "")):
		"error", "out_of_bandwidth":
			color = "#ff5c7a"
		"bump":
			color = "#ffb74d"
		"submit_result", "plot_csv":
			color = "#39d98a"
		"log":
			color = "#4fc3f7"
	_print("[color=#4a5868]%4d[/color] [color=%s]%s[/color]" % [int(f.get("step", 0)), color, UI.bb_escape(str(f.get("log", f.get("action", ""))))])
	if f.has("traceback"):
		_print("[color=#ff5c7a]%s[/color]" % UI.bb_escape(str(f["traceback"])))


func _on_playback_done() -> void:
	run_btn.disabled = false
	test_btn.disabled = false
	var r := _pending_result
	if r.is_empty():
		return
	var out := str(r.get("stdout", "")).strip_edges()
	if out != "":
		_print("[color=#8b98a7]--- stdout ---[/color]\n" + UI.bb_escape(out))
	var err := str(r.get("stderr", "")).strip_edges()
	if err != "" and not r.get("success", true):
		_print("[color=#ff5c7a]" + UI.bb_escape(err.right(1500)) + "[/color]")
	var passed: bool = r.get("challenge_passed", false)
	_print(("[color=#39d98a][b]PASS[/b][/color] " if passed else "[color=#ffb74d][b]RESULT[/b][/color] ") + UI.bb_escape(str(r.get("message", r.get("error", "")))))
	if r.get("git_commit") != null:
		_print("[color=#4fc3f7]git:[/color] " + UI.bb_escape(str(r["git_commit"])))
	var techs: Array = r.get("unlocked_tech", [])
	if not techs.is_empty():
		_print("[color=#39d98a]Tech unlocked: %s[/color]" % ", ".join(PackedStringArray(techs)))
	if r.get("unlocked_benchmark") != null:
		_print("[color=#39d98a]Benchmark checked: %s → résumé rebuilt[/color]" % str(r["unlocked_benchmark"]))
	if r.has("image"):
		_show_image(str(r["image"]))
	_pending_result = {}


func _show_image(p: String) -> void:
	var img := Image.new()
	if img.load(p) == OK:
		plot_rect.texture = ImageTexture.create_from_image(img)
		plot_rect.visible = true


func _print(bb: String) -> void:
	terminal.append_text(bb + "\n")
