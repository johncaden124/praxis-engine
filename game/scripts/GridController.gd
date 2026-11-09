extends Control
## Draws the research grid and animates a drone_runner JSON trace frame by frame.

const UI = preload("res://scripts/UI.gd")

signal frame_played(frame: Dictionary)
signal playback_finished()

const TILE_COLORS := {
	"respondent": Color("1f6f5c"),
	"data_terminal": Color("1d4f7a"),
	"wall": Color("1a2230"),
	"person": Color("5a4417"),
	"plot": Color("2b5a2f"),
	"agent_1": Color("1d5e86"),
	"agent_2": Color("8a4b1d"),
	"anomaly": Color("4b2a63"),
}

var grid_w := 5
var grid_h := 5
var tiles: Dictionary = {}
var graph: Dictionary = {}
var positions: Dictionary = {}
var drone_cell := Vector2(0, 0)
var drone_draw := Vector2(0, 0)
var speed := 1.0
var base_step := 0.15
var trail: Array = []
var floaters: Array = []
var flash_color := Color(0, 0, 0, 0)
var flash_t := 0.0

var _frames: Array = []
var _idx := 0
var _timer: Timer
var _tween: Tween
var _font: Font


func _ready() -> void:
	clip_contents = true
	custom_minimum_size = Vector2(320, 320)
	_font = ThemeDB.fallback_font
	_timer = Timer.new()
	_timer.one_shot = false
	_timer.timeout.connect(_step)
	add_child(_timer)


func set_world(world: Dictionary) -> void:
	stop()
	var size_arr: Array = world.get("size", [5, 5])
	grid_w = int(size_arr[0])
	grid_h = int(size_arr[1])
	tiles = world.get("tiles", {}).duplicate(true)
	var data: Dictionary = world.get("data", {})
	graph = data.get("graph", {})
	positions = data.get("positions", {})
	var d: Array = world.get("drone", [0, 0])
	drone_cell = Vector2(float(d[0]), float(d[1]))
	drone_draw = drone_cell
	trail.clear()
	floaters.clear()
	queue_redraw()


func play(frames: Array, spd: float = 1.0) -> void:
	stop()
	_frames = frames
	_idx = 0
	speed = max(spd, 0.1)
	_timer.wait_time = base_step / speed
	if _frames.is_empty():
		emit_signal("playback_finished")
		return
	_timer.start()


func stop() -> void:
	if _timer:
		_timer.stop()
	_frames = []


func is_playing() -> bool:
	return _timer != null and not _timer.is_stopped()


func set_speed(spd: float) -> void:
	speed = max(spd, 0.1)
	if _timer:
		_timer.wait_time = base_step / speed


func _step() -> void:
	if _idx >= _frames.size():
		_timer.stop()
		emit_signal("playback_finished")
		return
	var f: Dictionary = _frames[_idx]
	_idx += 1
	_apply(f)
	emit_signal("frame_played", f)


func _apply(f: Dictionary) -> void:
	var action := str(f.get("action", ""))
	var pos_arr: Array = f.get("pos", [drone_cell.x, drone_cell.y])
	var target := Vector2(float(pos_arr[0]), float(pos_arr[1]))
	if target != drone_cell:
		trail.append(drone_cell)
		if trail.size() > 40:
			trail.pop_front()
		drone_cell = target
		if _tween and _tween.is_valid():
			_tween.kill()
		_tween = create_tween()
		_tween.tween_property(self, "drone_draw", drone_cell, _timer.wait_time * 0.9).set_trans(Tween.TRANS_SINE)
	var key := "%d,%d" % [int(target.x), int(target.y)]
	match action:
		"harvest_data":
			if f.get("value") != null and tiles.has(key):
				tiles[key]["harvested"] = true
				_float(target, "+%s" % str(f.get("value")), UI.ACCENT)
			else:
				_float(target, "∅", UI.MUTED)
		"clean_outlier":
			if tiles.has(key):
				tiles[key]["corrupt"] = false
			_float(target, "cleaned", UI.ACCENT_2)
		"scan":
			_float(target, "scan", UI.ACCENT_2)
		"bump":
			_flash(UI.WARN)
			_float(target, "bump!", UI.WARN)
		"run_abm_step":
			_apply_abm(f.get("grid", []))
			_float(Vector2(grid_w / 2.0, grid_h - 0.5), "seg %.2f" % float(f.get("segregation", 0)), UI.ACCENT)
		"plot_csv":
			_float(target, "plot saved", UI.ACCENT_2)
		"submit_result":
			_flash(UI.ACCENT)
			_float(target, "submitted", UI.ACCENT)
		"error", "out_of_bandwidth":
			_flash(UI.DANGER)
			_float(target, "!", UI.DANGER)
	queue_redraw()


func _apply_abm(rows: Array) -> void:
	if rows.is_empty():
		return
	tiles.clear()
	for r in range(rows.size()):
		var row := str(rows[r])
		for x in range(row.length()):
			var v := int(row[x])
			if v > 0:
				tiles["%d,%d" % [x, r]] = {"type": "agent_%d" % v, "value": v}


func _float(cell: Vector2, text: String, color: Color) -> void:
	floaters.append({"cell": cell, "text": text, "color": color, "t": 0.0})


func _flash(color: Color) -> void:
	flash_color = color
	flash_t = 0.35


func _process(delta: float) -> void:
	var dirty := false
	for fl in floaters:
		fl["t"] = float(fl["t"]) + delta
		dirty = true
	floaters = floaters.filter(func(fl): return float(fl["t"]) < 1.1)
	if flash_t > 0.0:
		flash_t -= delta
		dirty = true
	if dirty or (_tween and _tween.is_valid() and _tween.is_running()):
		queue_redraw()


# ------------------------------------------------------------------ drawing

func _cell_size() -> float:
	return floor(min(size.x / max(grid_w, 1), size.y / max(grid_h, 1)))


func _origin() -> Vector2:
	var cs := _cell_size()
	return Vector2((size.x - cs * grid_w) / 2.0, (size.y - cs * grid_h) / 2.0)


func cell_center(cell: Vector2) -> Vector2:
	var cs := _cell_size()
	var o := _origin()
	return o + Vector2((cell.x + 0.5) * cs, (grid_h - 1 - cell.y + 0.5) * cs)


func _draw() -> void:
	var cs := _cell_size()
	var o := _origin()
	draw_rect(Rect2(Vector2.ZERO, size), UI.BG)
	# tiles
	for y in range(grid_h):
		for x in range(grid_w):
			var r := Rect2(o + Vector2(x * cs, (grid_h - 1 - y) * cs), Vector2(cs, cs)).grow(-2)
			var key := "%d,%d" % [x, y]
			var base := Color("111820")
			if tiles.has(key):
				var t: Dictionary = tiles[key]
				var ttype := str(t.get("type", ""))
				base = TILE_COLORS.get(ttype, Color("223040"))
				if ttype == "plot":
					base = base.lerp(UI.ACCENT, clamp(float(t.get("value", 0)) / 25.0, 0.0, 0.8))
				if t.get("harvested", false):
					base = base.darkened(0.45)
				if t.get("corrupt", false):
					base = Color("6b1f3a")
			draw_rect(r, base)
			draw_rect(r, UI.LINE, false, 1.0)
			if tiles.has(key):
				_draw_tile_glyph(tiles[key], r, cs)
	# social graph edges
	if not graph.is_empty():
		for a in graph.keys():
			for b in graph[a]:
				if str(a) < str(b) and positions.has(a) and positions.has(b):
					var pa: Array = positions[a]
					var pb: Array = positions[b]
					var col := Color(1, 0.72, 0.3, 0.35)
					if graph[a].size() <= 2 or graph[b].size() <= 2:
						col = Color(0.31, 0.76, 0.97, 0.75)  # likely a weak tie
					draw_line(cell_center(Vector2(pa[0], pa[1])), cell_center(Vector2(pb[0], pb[1])), col, 1.5, true)
	# trail
	for i in range(trail.size()):
		var alpha := float(i + 1) / float(trail.size() + 1)
		draw_circle(cell_center(trail[i]), cs * 0.07, Color(0.22, 0.85, 0.54, alpha * 0.5))
	# drone
	var c := cell_center(drone_draw)
	draw_circle(c, cs * 0.34, Color(0.22, 0.85, 0.54, 0.15))
	var s := cs * 0.24
	var pts := PackedVector2Array([c + Vector2(0, -s), c + Vector2(s, 0), c + Vector2(0, s), c + Vector2(-s, 0)])
	draw_colored_polygon(pts, UI.ACCENT)
	draw_circle(c, s * 0.3, UI.BG)
	# floaters
	for fl in floaters:
		var t := float(fl["t"])
		var p := cell_center(fl["cell"]) + Vector2(-cs * 0.4, -cs * 0.3 - t * cs * 0.6)
		var col: Color = fl["color"]
		col.a = clamp(1.2 - t, 0.0, 1.0)
		draw_string(_font, p, str(fl["text"]), HORIZONTAL_ALIGNMENT_LEFT, cs * 1.6, int(clamp(cs * 0.22, 11, 18)), col)
	# flash
	if flash_t > 0.0:
		var fc := flash_color
		fc.a = flash_t
		draw_rect(Rect2(Vector2.ZERO, size), fc, false, 4.0)


func _draw_tile_glyph(t: Dictionary, r: Rect2, cs: float) -> void:
	var ttype := str(t.get("type", ""))
	var fs := int(clamp(cs * 0.2, 9, 16))
	var center := r.get_center()
	match ttype:
		"respondent":
			draw_circle(center, cs * 0.1, UI.ACCENT if not t.get("harvested", false) else UI.MUTED)
		"person":
			draw_circle(center, cs * 0.22, Color("ffb74d"))
			draw_string(_font, r.position + Vector2(4, r.size.y - 6), str(t.get("node", "")), HORIZONTAL_ALIGNMENT_LEFT, r.size.x - 6, fs, UI.TEXT)
		"agent_1":
			draw_circle(center, cs * 0.28, UI.ACCENT_2)
		"agent_2":
			draw_rect(Rect2(center - Vector2(cs * 0.24, cs * 0.24), Vector2(cs * 0.48, cs * 0.48)), UI.WARN)
		"data_terminal":
			draw_string(_font, r.position + Vector2(6, r.size.y * 0.6), "CSV", HORIZONTAL_ALIGNMENT_LEFT, r.size.x, fs + 4, UI.ACCENT_2)
		"plot":
			draw_string(_font, r.position + Vector2(4, fs + 2), "%.0f" % float(t.get("value", 0)), HORIZONTAL_ALIGNMENT_LEFT, r.size.x, fs, UI.TEXT)
		"anomaly":
			draw_arc(center, cs * 0.22, 0, TAU, 24, UI.VIOLET, 2.0)
		"wall":
			draw_line(r.position, r.end, Color("2a3646"), 1.0)
