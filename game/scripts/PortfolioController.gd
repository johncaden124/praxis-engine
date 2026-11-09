extends HBoxContainer
## Room [5] Character Sheet, Live Résumé & Public Exporter — Portfolio & Writing.

const UI = preload("res://scripts/UI.gd")

var stats_grid: GridContainer
var tracks_box: VBoxContainer
var heat: Heatmap
var essays: ItemList
var essay_info: Label
var critique_btn: Button
var publish_btn: Button
var log_label: RichTextLabel

var _essays: Array = []


class Heatmap:
	extends Control
	const U = preload("res://scripts/UI.gd")
	var daily: Dictionary = {}
	var weeks := 18

	func _ready() -> void:
		custom_minimum_size = Vector2(0, 7 * 16 + 20)

	func _draw() -> void:
		var cell: float = min((size.x - 20.0) / weeks, 16.0)
		var today := Time.get_date_dict_from_system()
		var today_unix := Time.get_unix_time_from_datetime_dict({"year": today["year"], "month": today["month"], "day": today["day"]})
		var wd := int(today["weekday"])  # 0 = Sunday
		var monday_offset := (wd + 6) % 7
		var start := today_unix - (monday_offset + 7 * (weeks - 1)) * 86400
		for w in range(weeks):
			for d in range(7):
				var ts := start + (w * 7 + d) * 86400
				var key := Time.get_date_string_from_unix_time(ts)
				var hours := 0.0
				if daily.has(key):
					hours = float(daily[key].get("hours", 0))
				var col := Color("1a2230")
				if ts > today_unix:
					col = Color(0, 0, 0, 0)
				elif hours > 0.0:
					col = Color(0.22, 0.85, 0.54, clamp(0.25 + hours / 3.0, 0.25, 1.0))
				draw_rect(Rect2(Vector2(w * cell, d * cell), Vector2(cell - 3, cell - 3)), col)
		draw_string(ThemeDB.fallback_font, Vector2(0, 7 * cell + 14), "last %d weeks · darker = more deep-work hours" % weeks, HORIZONTAL_ALIGNMENT_LEFT, -1, 11, U.MUTED)


func _ready() -> void:
	add_theme_constant_override("separation", 14)
	add_child(_build_sheet())
	add_child(_build_broadcast())
	GameManager.status_changed.connect(_on_status)
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)


func _build_sheet() -> Control:
	var v := UI.vbox(12)
	UI.expand(v)
	v.add_child(UI.header("Character sheet · academic RPG stats", UI.ACCENT))
	stats_grid = GridContainer.new()
	stats_grid.columns = 3
	stats_grid.add_theme_constant_override("h_separation", 10)
	stats_grid.add_theme_constant_override("v_separation", 10)
	v.add_child(stats_grid)
	v.add_child(UI.header("Streak heatmap"))
	heat = Heatmap.new()
	v.add_child(heat)
	v.add_child(UI.header("Curriculum tracks (lifetime hours · items done)"))
	tracks_box = UI.vbox(8)
	v.add_child(tracks_box)
	var sc := ScrollContainer.new()
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	UI.expand(v, true, false)
	sc.add_child(v)
	var p := UI.panel(sc)
	UI.expand(p)
	p.custom_minimum_size = Vector2(520, 0)
	return p


func _build_broadcast() -> Control:
	var v := UI.vbox(10)
	UI.expand(v)
	v.add_child(UI.header("Essay broadcast terminal · 04 Writing/", UI.ACCENT_2))
	essays = ItemList.new()
	essays.custom_minimum_size = Vector2(0, 200)
	essays.item_selected.connect(_on_essay_selected)
	v.add_child(essays)
	essay_info = UI.label("Select an essay.", 13, UI.MUTED, true)
	v.add_child(essay_info)
	var row := UI.hbox(8)
	row.add_child(UI.button("Open in Obsidian", _open_essay))
	critique_btn = UI.accent_button("Run Harsh AI Critique", _critique, UI.WARN)
	publish_btn = UI.accent_button("📡 Publish to Portfolio", _publish, UI.ACCENT)
	row.add_child(critique_btn)
	row.add_child(publish_btn)
	v.add_child(row)
	v.add_child(HSeparator.new())
	v.add_child(UI.header("Living résumé & lead magnet"))
	v.add_child(UI.accent_button("Compile & View Live Résumé", _compile, UI.ACCENT_2))
	v.add_child(UI.accent_button("Export Public Lead Magnet (praxis-engine)", _export, UI.VIOLET))
	var r2 := UI.hbox(8)
	r2.add_child(UI.button("Sync (cards + portfolio + git)", func(): GameManager.learn(["sync"], _log_result)))
	r2.add_child(UI.button("Run learn doctor", func(): GameManager.learn(["doctor"], _log_doctor, false)))
	v.add_child(r2)
	log_label = RichTextLabel.new()
	log_label.bbcode_enabled = true
	log_label.scroll_following = true
	UI.expand(log_label)
	log_label.custom_minimum_size = Vector2(0, 160)
	v.add_child(log_label)
	var p := UI.panel(v)
	UI.expand(p)
	p.custom_minimum_size = Vector2(480, 0)
	return p


func _stat(value: String, label: String, color: Color = UI.TEXT) -> Control:
	var v := UI.vbox(2)
	var l := UI.label(value, 28, color)
	l.add_theme_font_override("font", UI.mono_font())
	v.add_child(l)
	v.add_child(UI.label(label, 12, UI.MUTED))
	var p := UI.panel(v, UI.PANEL_2)
	p.custom_minimum_size = Vector2(150, 0)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return p


func _on_status(st: Dictionary) -> void:
	var s: Dictionary = st.get("state", {})
	var stage: Dictionary = st.get("stage", {})
	UI.clear(stats_grid)
	var published := 0
	for e in st.get("essays", []):
		if str(e.get("status", "")) == "published":
			published += 1
	var lt: Dictionary = s.get("lifetime_stats", {})
	stats_grid.add_child(_stat("%d" % int(s.get("stage", 1)), "Stage · %s" % str(stage.get("name", "")), UI.ACCENT))
	stats_grid.add_child(_stat("%d" % int(s.get("xp", 0)), "XP"))
	stats_grid.add_child(_stat("%d🔥" % int(s.get("streak_days", 0)), "day streak", UI.WARN))
	stats_grid.add_child(_stat("%.1f" % float(st.get("lifetime_hours", 0)), "hours logged (target %s)" % str(stage.get("hours_target", "?"))))
	stats_grid.add_child(_stat("%d" % published, "papers published"))
	stats_grid.add_child(_stat("%d" % int(lt.get("pages_read", 0)), "pages read"))
	stats_grid.add_child(_stat("%d" % s.get("completed_benchmarks", []).size(), "benchmarks"))
	stats_grid.add_child(_stat("%d" % s.get("earned_credentials", []).size(), "credentials"))
	stats_grid.add_child(_stat("%d" % lt.get("challenges_passed", []).size(), "drone challenges"))
	heat.daily = s.get("daily_log", {})
	heat.queue_redraw()

	UI.clear(tracks_box)
	for t in st.get("tracks", []):
		var row := UI.vbox(2)
		var top := UI.hbox()
		top.add_child(UI.label(str(t.get("label", "")), 14))
		top.add_child(UI.spacer())
		top.add_child(UI.label("%.1fh · %d/%d" % [float(t.get("hours_lifetime", 0)), int(t.get("done", 0)), int(t.get("total", 0))], 12, UI.MUTED))
		row.add_child(top)
		row.add_child(UI.bar(Color(str(t.get("color", "#39d98a"))), float(t.get("pct", 0)), 100.0, 10))
		tracks_box.add_child(row)

	var keep := essays.get_selected_items()
	_essays = st.get("essays", [])
	essays.clear()
	for e in _essays:
		var badge := "📡" if str(e.get("status", "")) == "published" else "✎"
		essays.add_item("%s  %s   — %s · %d words%s" % [badge, e.get("title", ""), e.get("status", ""), int(e.get("words", 0)), " · critiqued" if e.get("has_critique", false) else ""])
	if keep.size() > 0 and keep[0] < essays.item_count:
		essays.select(keep[0])
		_on_essay_selected(keep[0])


func _selected_essay() -> Dictionary:
	var sel := essays.get_selected_items()
	if sel.is_empty() or sel[0] >= _essays.size():
		return {}
	return _essays[sel[0]]


func _on_essay_selected(_i: int) -> void:
	var e := _selected_essay()
	if e.is_empty():
		return
	var pub := str(e.get("status", "")) == "published"
	essay_info.text = "%s · due %s · %d words · %s" % [e.get("path", ""), e.get("due", "—"), int(e.get("words", 0)), "published" if pub else "draft"]
	publish_btn.text = "Unpublish" if pub else "📡 Publish to Portfolio"


func _open_essay() -> void:
	var e := _selected_essay()
	if not e.is_empty():
		GameManager.obsidian_open(str(e.get("path", "")))


func _critique() -> void:
	var e := _selected_essay()
	if e.is_empty():
		return
	_log("[color=#ffb74d]Requesting critique for %s…[/color]" % UI.bb_escape(str(e.get("title", ""))))
	GameManager.learn(["critique", str(e.get("path", ""))], _log_result)


func _publish() -> void:
	var e := _selected_essay()
	if e.is_empty():
		return
	var args := ["publish", str(e.get("path", ""))]
	if str(e.get("status", "")) == "published":
		args.append("--undo")
	GameManager.learn(args, _log_result)


func _compile() -> void:
	_log("[color=#4fc3f7]Compiling résumé…[/color]")
	GameManager.learn(["resume"], _on_compiled)


func _on_compiled(r: Dictionary) -> void:
	_log_result(r)
	if r.get("ok", false):
		GameManager.open_external(str(r.get("index_url", "file://" + GameManager.path("10 Portfolio/index.html"))))


func _export() -> void:
	_log("[color=#ba68c8]Exporting sanitized public engine…[/color]")
	GameManager.learn(["export-public"], _log_result, false)


func _log_result(r: Dictionary) -> void:
	var ok_flag = r.get("ok", r.get("success", true))
	_log(("[color=#39d98a]✔[/color] " if ok_flag else "[color=#ff5c7a]✘[/color] ") + UI.bb_escape(str(r.get("message", r.get("error", "")))))
	if r.has("critique"):
		_log(UI.bb_escape(str(r["critique"])))


func _log_doctor(r: Dictionary) -> void:
	_log_result(r)
	for c in r.get("checks", []):
		if not c.get("ok", false):
			_log("  [color=#ffb74d]%s[/color] %s" % [UI.bb_escape(str(c.get("name", ""))), UI.bb_escape(str(c.get("detail", "")))])


func _log(bb: String) -> void:
	log_label.append_text(bb + "\n")
