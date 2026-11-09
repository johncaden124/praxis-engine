extends Control
## Praxis: The Emergent Grid — root scene. Top navigation between the five
## rooms, a live HUD (stage, XP, streak, Cognitive Bandwidth, session) and a
## status line fed by every learn.py result.

const UI = preload("res://scripts/UI.gd")
const IdeController = preload("res://scripts/IdeController.gd")
const StudyController = preload("res://scripts/StudyController.gd")
const TechTreeController = preload("res://scripts/TechTreeController.gd")
const SocialRadarController = preload("res://scripts/SocialRadarController.gd")
const PortfolioController = preload("res://scripts/PortfolioController.gd")

const ROOMS := [
	["[1] Automation Grid & IDE", "IdeController"],
	["[2] Study Sanctum", "StudyController"],
	["[3] Tech Tree", "TechTreeController"],
	["[4] Social Radar", "SocialRadarController"],
	["[5] Character Sheet", "PortfolioController"],
]

var rooms: Array = []
var tab_buttons: Array = []
var stage_label: Label
var xp_label: Label
var streak_label: Label
var bw_bar: ProgressBar
var bw_label: Label
var session_label: Label
var status_label: Label
var busy_label: Label
var current := 0


func _ready() -> void:
	theme = UI.make_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = UI.BG
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(side, 14)
	add_child(margin)
	var root := UI.vbox(12)
	margin.add_child(root)

	root.add_child(_build_top_bar())
	var content := Control.new()
	UI.expand(content)
	root.add_child(content)
	for r in ROOMS:
		var room: Control = _make_room(r[1])
		room.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		room.visible = false
		content.add_child(room)
		rooms.append(room)
	root.add_child(_build_status_bar())

	GameManager.status_changed.connect(_on_status)
	GameManager.message.connect(_on_message)
	GameManager.busy_changed.connect(func(b): busy_label.text = "⟳ working…" if b else "")
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)
	show_room(0)
	_on_message("Vault: %s · Python: %s" % [GameManager.vault_root, GameManager.python_bin], "info")


func _make_room(kind: String) -> Control:
	match kind:
		"IdeController":
			return IdeController.new()
		"StudyController":
			return StudyController.new()
		"TechTreeController":
			return TechTreeController.new()
		"SocialRadarController":
			return SocialRadarController.new()
		_:
			return PortfolioController.new()


func _build_top_bar() -> Control:
	var bar := UI.hbox(8)
	var title := UI.label("PRAXIS", 22, UI.ACCENT)
	title.add_theme_font_override("font", UI.mono_font())
	bar.add_child(title)
	bar.add_child(UI.label("// THE EMERGENT GRID", 13, UI.MUTED))
	bar.add_child(UI.spacer())
	for i in range(ROOMS.size()):
		var b := UI.button(ROOMS[i][0], show_room.bind(i), "Alt+%d" % (i + 1))
		tab_buttons.append(b)
		bar.add_child(b)
	bar.add_child(UI.spacer())

	var hud := UI.vbox(2)
	var row := UI.hbox(10)
	stage_label = UI.label("Stage 1", 14, UI.ACCENT)
	xp_label = UI.label("0 XP", 14, UI.TEXT)
	streak_label = UI.label("0🔥", 14, UI.WARN)
	row.add_child(stage_label)
	row.add_child(xp_label)
	row.add_child(streak_label)
	hud.add_child(row)
	var brow := UI.hbox(6)
	brow.add_child(UI.label("⚡", 13, UI.ACCENT))
	bw_bar = UI.bar(UI.ACCENT, 100, 100, 10)
	bw_bar.custom_minimum_size = Vector2(160, 10)
	brow.add_child(bw_bar)
	bw_label = UI.label("100/100", 12, UI.MUTED)
	brow.add_child(bw_label)
	hud.add_child(brow)
	bar.add_child(hud)
	return UI.panel(bar, UI.PANEL)


func _build_status_bar() -> Control:
	var bar := UI.hbox(10)
	session_label = UI.label("", 13, UI.ACCENT_2)
	bar.add_child(session_label)
	status_label = UI.label("", 13, UI.MUTED)
	status_label.clip_text = true
	status_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	UI.expand(status_label, true, false)
	bar.add_child(status_label)
	busy_label = UI.label("", 13, UI.WARN)
	bar.add_child(busy_label)
	bar.add_child(UI.button("⟳", func(): GameManager.refresh(), "Reload from disk"))
	return bar


func show_room(i: int) -> void:
	current = i
	for k in range(rooms.size()):
		rooms[k].visible = k == i
		var b: Button = tab_buttons[k]
		if k == i:
			b.add_theme_stylebox_override("normal", UI.box(Color(0.22, 0.85, 0.54, 0.14), UI.ACCENT, 6, 12))
			b.add_theme_color_override("font_color", UI.ACCENT)
		else:
			b.remove_theme_stylebox_override("normal")
			b.remove_theme_color_override("font_color")


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.alt_pressed:
		var n: int = event.keycode - KEY_1
		if n >= 0 and n < ROOMS.size():
			show_room(n)
			get_viewport().set_input_as_handled()


func _on_status(st: Dictionary) -> void:
	var s: Dictionary = st.get("state", {})
	var stage: Dictionary = st.get("stage", {})
	stage_label.text = "Stage %d · %s" % [int(s.get("stage", 1)), str(stage.get("name", ""))]
	xp_label.text = "%d XP" % int(s.get("xp", 0))
	streak_label.text = "%d🔥" % int(s.get("streak_days", 0))
	var bw := float(s.get("cognitive_bandwidth", 0))
	var mx := float(s.get("max_bandwidth", 100))
	bw_bar.max_value = mx
	bw_bar.value = bw
	var col := UI.ACCENT if bw > mx * 0.3 else (UI.WARN if bw > 0 else UI.DANGER)
	bw_bar.add_theme_stylebox_override("fill", UI.box(col, col, 6, 0))
	bw_label.text = "%.0f/%.0f" % [bw, mx]
	var sess: Dictionary = s.get("active_session", {})
	session_label.text = "● %s session running" % str(sess.get("track", "")) if sess.get("running", false) else ""


func _on_message(text: String, level: String) -> void:
	var first := text.split("\n")[0]
	status_label.text = first
	status_label.add_theme_color_override("font_color", UI.DANGER if level == "error" else UI.MUTED)
	status_label.tooltip_text = text
