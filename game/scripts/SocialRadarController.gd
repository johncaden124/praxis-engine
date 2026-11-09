extends HSplitContainer
## Room [4] Social Topology Radar — People Skills & Discussion track.
## Draws 06 People.md as a radial network: distance from you = days since
## contact. Green ≤14 days, yellow 15–29, pulsing red ≥30.

const UI = preload("res://scripts/UI.gd")

var radar: RadarView
var detail: VBoxContainer
var name_edit: LineEdit
var detail_edit: TextEdit
var habit_label: Label
var plateau_label: Label
var quests: VBoxContainer


class RadarView:
	extends Control
	const U = preload("res://scripts/UI.gd")
	signal person_clicked(name: String)

	var people: Array = []
	var selected := ""
	var _t := 0.0
	var _hits: Array = []
	var _font: Font

	func _ready() -> void:
		_font = ThemeDB.fallback_font
		custom_minimum_size = Vector2(420, 420)
		mouse_filter = Control.MOUSE_FILTER_STOP

	func _process(delta: float) -> void:
		_t += delta
		queue_redraw()

	func _gui_input(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			for h in _hits:
				if event.position.distance_to(h["pos"]) <= float(h["r"]) + 6.0:
					emit_signal("person_clicked", str(h["name"]))
					return

	func _draw() -> void:
		var c := size / 2.0
		var r_max: float = min(size.x, size.y) * 0.44
		draw_rect(Rect2(Vector2.ZERO, size), U.BG)
		# rings: 14 / 30 / 60 days
		var rings := [[14.0, U.ACCENT], [30.0, U.WARN], [60.0, U.DANGER]]
		for ring in rings:
			var rr: float = r_max * float(ring[0]) / 60.0
			var col: Color = ring[1]
			col.a = 0.35
			draw_arc(c, rr, 0, TAU, 96, col, 1.0, true)
			draw_string(_font, c + Vector2(4, -rr - 2), "%dd" % int(ring[0]), HORIZONTAL_ALIGNMENT_LEFT, -1, 11, col)
		# sweep
		var ang := fmod(_t * 0.8, TAU)
		draw_line(c, c + Vector2(cos(ang), sin(ang)) * r_max, Color(0.22, 0.85, 0.54, 0.25), 2.0, true)
		_hits.clear()
		var n := people.size()
		for i in range(n):
			var p: Dictionary = people[i]
			var days := float(p.get("days_since", 0))
			var dist: float = r_max * clamp(0.18 + days / 60.0, 0.18, 1.0)
			var a := TAU * float(i) / float(maxi(n, 1)) - PI / 2.0
			var pos := c + Vector2(cos(a), sin(a)) * dist
			var col := U.status_color(str(p.get("status", "active")))
			var radius := 9.0 + minf(float(p.get("notes_count", 1)), 12.0)
			draw_line(c, pos, Color(col.r, col.g, col.b, 0.25), 1.0, true)
			if str(p.get("status", "")) == "dormant":
				var pulse := 0.5 + 0.5 * sin(_t * 4.0 + i)
				draw_circle(pos, radius + 6.0 + pulse * 8.0, Color(col.r, col.g, col.b, 0.18 * (1.0 - pulse) + 0.05))
			draw_circle(pos, radius, Color(col.r, col.g, col.b, 0.85))
			if str(p.get("name", "")) == selected:
				draw_arc(pos, radius + 4.0, 0, TAU, 32, U.ACCENT_2, 2.0, true)
			draw_string(_font, pos + Vector2(radius + 4, 4), "%s · %dd" % [p.get("name", ""), int(days)], HORIZONTAL_ALIGNMENT_LEFT, -1, 13, U.TEXT)
			_hits.append({"pos": pos, "r": radius, "name": p.get("name", "")})
		# you
		draw_circle(c, 14.0, U.ACCENT_2)
		draw_string(_font, c + Vector2(-12, 30), "you", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, U.ACCENT_2)


func _ready() -> void:
	split_offset = 200
	var left := UI.vbox(8)
	UI.expand(left)
	left.add_child(UI.header("Social topology radar  ·  ring = days since last contact", UI.ACCENT))
	radar = RadarView.new()
	UI.expand(radar)
	radar.person_clicked.connect(_select)
	left.add_child(UI.expand(UI.panel(radar, UI.BG)))
	add_child(left)

	var right := UI.vbox(10)
	right.custom_minimum_size = Vector2(420, 0)
	right.add_child(UI.header("Stage habit"))
	habit_label = UI.label("", 15, UI.TEXT, true)
	right.add_child(habit_label)
	plateau_label = UI.label("", 13, UI.WARN, true)
	right.add_child(plateau_label)
	right.add_child(HSeparator.new())
	right.add_child(UI.header("Quests"))
	quests = UI.vbox(4)
	right.add_child(quests)
	right.add_child(HSeparator.new())
	detail = UI.vbox(6)
	right.add_child(detail)
	right.add_child(HSeparator.new())
	right.add_child(UI.header("Log an interaction", UI.ACCENT))
	name_edit = LineEdit.new()
	name_edit.placeholder_text = "Name"
	right.add_child(name_edit)
	detail_edit = TextEdit.new()
	detail_edit.placeholder_text = "3 things you learned / a detail to remember next time…"
	detail_edit.custom_minimum_size = Vector2(0, 90)
	detail_edit.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	right.add_child(detail_edit)
	right.add_child(UI.accent_button("+ Log to 06 People.md", _log))
	right.add_child(UI.label("Listening tip: ask one follow-up question before sharing anything about yourself.", 12, UI.MUTED, true))
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(440, 0)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	UI.expand(right, true, false)
	scroll.add_child(right)
	add_child(UI.panel(scroll))

	GameManager.status_changed.connect(_on_status)
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)


func _on_status(st: Dictionary) -> void:
	radar.people = st.get("people", [])
	var stage: Dictionary = st.get("stage", {})
	habit_label.text = str(stage.get("people_habit", ""))
	plateau_label.text = "Plateau warning: " + str(stage.get("plateau_warning", ""))
	UI.clear(quests)
	var overdue := 0
	for p in radar.people:
		if int(p.get("days_since", 0)) >= 30:
			overdue += 1
			quests.add_child(UI.label("◉ Reach out to %s — %d days. Bring up: %s" % [p.get("name", ""), int(p.get("days_since", 0)), _last_detail(p)], 14, UI.DANGER, true))
		elif int(p.get("days_since", 0)) >= 15:
			quests.add_child(UI.label("◌ %s is cooling (%d days)." % [p.get("name", ""), int(p.get("days_since", 0))], 14, UI.WARN, true))
	if radar.people.is_empty():
		quests.add_child(UI.label("No one on the radar yet. Log your first conversation below.", 14, UI.MUTED, true))
	elif overdue == 0:
		quests.add_child(UI.label("No dormant ties. Practise this stage's habit instead.", 14, UI.ACCENT, true))
	_select(radar.selected)


func _last_detail(p: Dictionary) -> String:
	var recent: Array = p.get("recent", [])
	return str(recent[-1]) if not recent.is_empty() else "something new"


func _select(pname: String) -> void:
	radar.selected = pname
	UI.clear(detail)
	var person := {}
	for p in radar.people:
		if str(p.get("name", "")) == pname:
			person = p
	if person.is_empty():
		detail.add_child(UI.label("Click a node for details.", 14, UI.MUTED))
		return
	name_edit.text = pname
	detail.add_child(UI.title(pname, 20))
	detail.add_child(UI.label("Last contact %s (%d days) · %d notes" % [person.get("last_contact", ""), int(person.get("days_since", 0)), int(person.get("notes_count", 0))], 13, UI.status_color(str(person.get("status", "")))))
	for d in person.get("recent", []):
		detail.add_child(UI.label("• " + str(d), 14, UI.TEXT, true))


func _log() -> void:
	var n := name_edit.text.strip_edges()
	var d := detail_edit.text.strip_edges().replace("\n", "; ")
	if n == "" or d == "":
		GameManager.emit_signal("message", "Need both a name and a detail.", "error")
		return
	detail_edit.text = ""
	GameManager.learn(["person", "%s: %s" % [n, d]])
