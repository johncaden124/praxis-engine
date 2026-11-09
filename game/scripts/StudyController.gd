extends HBoxContainer
## Room [2] Study Sanctum & Anki Reactor — Reading, Math & timer tracks.

const UI = preload("res://scripts/UI.gd")

const TRACKS := ["Coding", "Math", "Reading", "Writing", "Discussion"]

var block_label: Label
var week_box: VBoxContainer
var focus_box: VBoxContainer
var today_label: Label
var track_pick: OptionButton
var clock_label: Label
var session_label: Label
var start_btn: Button
var stop_btn: Button
var hl_edit: LineEdit
var q_edit: LineEdit
var pages_spin: SpinBox
var card_front: Label
var card_back: Label
var card_meta: Label
var reveal_btn: Button
var good_btn: Button
var miss_btn: Button
var recharge_btn: Button

var _running := false
var _start_ts := ""
var _quiz: Array = []
var _qi := 0


func _ready() -> void:
	add_theme_constant_override("separation", 14)
	add_child(_build_plan_column())
	add_child(_build_session_column())
	add_child(_build_reactor_column())
	GameManager.status_changed.connect(_on_status)
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)


func _column(min_w: int) -> VBoxContainer:
	var v := UI.vbox(12)
	UI.expand(v)
	v.custom_minimum_size = Vector2(min_w, 0)
	return v


func _build_plan_column() -> Control:
	var v := _column(330)
	v.add_child(UI.header("Today's scheduled block", UI.ACCENT))
	block_label = UI.label("—", 26, UI.TEXT, true)
	v.add_child(block_label)
	today_label = UI.label("", 14, UI.MUTED, true)
	v.add_child(today_label)
	v.add_child(HSeparator.new())
	v.add_child(UI.header("Current focus"))
	focus_box = UI.vbox(6)
	v.add_child(focus_box)
	v.add_child(HSeparator.new())
	v.add_child(UI.header("This week (from schedule.yaml)"))
	week_box = UI.vbox(4)
	v.add_child(week_box)
	return UI.expand(UI.panel(v))


func _build_session_column() -> Control:
	var v := _column(380)
	v.add_child(UI.header("Deep work session", UI.ACCENT))
	var row := UI.hbox()
	row.add_child(UI.label("Track", 14, UI.MUTED))
	track_pick = OptionButton.new()
	for t in TRACKS:
		track_pick.add_item(t)
	UI.expand(track_pick, true, false)
	row.add_child(track_pick)
	v.add_child(row)
	clock_label = UI.label("00:00:00", 64, UI.TEXT)
	clock_label.add_theme_font_override("font", UI.mono_font())
	clock_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(clock_label)
	session_label = UI.label("Idle. Every deep-work minute earns XP and recharges the drone.", 14, UI.MUTED, true)
	session_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(session_label)
	var brow := UI.hbox()
	start_btn = UI.accent_button("▶  Start Deep Work Session", _start)
	stop_btn = UI.accent_button("■  Stop & Log", _stop, UI.WARN)
	UI.expand(start_btn, true, false)
	UI.expand(stop_btn, true, false)
	brow.add_child(start_btn)
	brow.add_child(stop_btn)
	v.add_child(brow)
	v.add_child(UI.button("Open session note in Obsidian", _open_target))
	v.add_child(HSeparator.new())

	v.add_child(UI.header("Quick capture"))
	var r1 := UI.hbox(6)
	hl_edit = LineEdit.new()
	hl_edit.placeholder_text = ">> highlight   (or  front :: back)"
	UI.expand(hl_edit, true, false)
	hl_edit.text_submitted.connect(func(_t): _highlight())
	r1.add_child(hl_edit)
	r1.add_child(UI.accent_button("+ Highlight  +10⚡", _highlight))
	v.add_child(r1)
	var r2 := UI.hbox(6)
	q_edit = LineEdit.new()
	q_edit.placeholder_text = "A question the author didn't answer…"
	UI.expand(q_edit, true, false)
	q_edit.text_submitted.connect(func(_t): _question())
	r2.add_child(q_edit)
	r2.add_child(UI.button("+ Unanswered Question", _question))
	v.add_child(r2)
	var r3 := UI.hbox(6)
	pages_spin = SpinBox.new()
	pages_spin.min_value = 1
	pages_spin.max_value = 500
	pages_spin.value = 20
	pages_spin.suffix = "pages"
	r3.add_child(pages_spin)
	r3.add_child(UI.button("+ Log Pages Read", _pages))
	v.add_child(r3)
	return UI.expand(UI.panel(v))


func _build_reactor_column() -> Control:
	var v := _column(360)
	v.add_child(UI.header("Flashcard reactor", UI.ACCENT_2))
	card_meta = UI.label("Cards from 08 Cards/ (your >> highlights).", 13, UI.MUTED, true)
	v.add_child(card_meta)
	recharge_btn = UI.accent_button("⚡ Recharge Bandwidth (5-card quiz)", _load_quiz, UI.ACCENT_2)
	v.add_child(recharge_btn)
	var card := UI.vbox(14)
	card_front = UI.label("Press Recharge to pull due cards.", 20, UI.TEXT, true)
	card_back = UI.label("", 17, UI.ACCENT, true)
	card.add_child(card_front)
	card.add_child(HSeparator.new())
	card.add_child(card_back)
	var cp := UI.panel(card, UI.PANEL_2)
	cp.custom_minimum_size = Vector2(0, 240)
	v.add_child(cp)
	reveal_btn = UI.button("Reveal answer", _reveal)
	v.add_child(reveal_btn)
	var row := UI.hbox()
	good_btn = UI.accent_button("✓ Got it  (+8⚡)", _answer.bind(true))
	miss_btn = UI.accent_button("✗ Missed", _answer.bind(false), UI.DANGER)
	UI.expand(good_btn, true, false)
	UI.expand(miss_btn, true, false)
	row.add_child(good_btn)
	row.add_child(miss_btn)
	v.add_child(row)
	v.add_child(UI.label("Grades use the Obsidian Spaced Repetition format, so reviews here are real reviews.", 12, UI.MUTED, true))
	_set_card_buttons(false, false)
	return UI.expand(UI.panel(v))


# ------------------------------------------------------------------ status

func _on_status(st: Dictionary) -> void:
	var s: Dictionary = st.get("state", {})
	var blk = st.get("scheduled_block", null)
	if blk is Dictionary:
		block_label.text = "%s · %s · %sh" % [blk.get("track", ""), blk.get("start", ""), str(blk.get("hours", ""))]
		if not _running:
			for i in range(TRACKS.size()):
				if TRACKS[i] == str(blk.get("track", "")):
					track_pick.select(i)
	else:
		block_label.text = "Rest day"
	var tn: Dictionary = st.get("today_note", {})
	today_label.text = "Today: %sh logged · %s pages · track %s" % [str(tn.get("hours", "0")), str(tn.get("pages", "0")), str(tn.get("track", "—"))]

	UI.clear(focus_box)
	var focus: Dictionary = s.get("current_focus", {})
	for k in ["reading", "course", "essay", "project"]:
		var row := UI.hbox(6)
		var lbl := UI.label(k.capitalize(), 13, UI.MUTED)
		lbl.custom_minimum_size = Vector2(70, 0)
		row.add_child(lbl)
		var val := str(focus.get(k, "—")) if focus.get(k) != null else "—"
		var b := UI.button(val.get_file().get_basename() if val.ends_with(".md") else val, _open_rel.bind(val))
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.disabled = not val.ends_with(".md")
		UI.expand(b, true, false)
		row.add_child(b)
		focus_box.add_child(row)

	UI.clear(week_box)
	var week: Dictionary = st.get("week_schedule", {})
	for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
		var blocks: Array = week.get(day, [])
		var parts := PackedStringArray()
		for b in blocks:
			parts.append("%s %s (%sh)" % [b.get("track", ""), b.get("start", ""), str(b.get("hours", ""))])
		var is_today := blk is Dictionary and str(blk.get("day", "")) == day
		week_box.add_child(UI.label("%s  %s" % [day.left(3).capitalize(), " · ".join(parts) if parts.size() > 0 else "—"], 13, UI.ACCENT if is_today else UI.TEXT))

	var sess: Dictionary = s.get("active_session", {})
	_running = bool(sess.get("running", false))
	_start_ts = str(sess.get("start_timestamp", "")) if sess.get("start_timestamp") != null else ""
	start_btn.disabled = _running
	stop_btn.disabled = not _running
	track_pick.disabled = _running
	if _running:
		session_label.text = "%s session → %s" % [sess.get("track", ""), str(sess.get("target_file", ""))]
		for i in range(TRACKS.size()):
			if TRACKS[i] == str(sess.get("track", "")):
				track_pick.select(i)
	else:
		session_label.text = "Idle. Every deep-work minute earns XP and recharges the drone."
		clock_label.text = "00:00:00"
	card_meta.text = "%d card(s) due · %d reviewed this week" % [int(st.get("cards_due", 0)), int(s.get("weekly_stats", {}).get("cards_reviewed", 0))]


func _process(_delta: float) -> void:
	if _running and _start_ts != "":
		var secs := GameManager.seconds_since(_start_ts)
		clock_label.text = "%02d:%02d:%02d" % [secs / 3600, (secs / 60) % 60, secs % 60]


# ------------------------------------------------------------------ actions

func _start() -> void:
	GameManager.learn(["start", TRACKS[track_pick.selected]])


func _stop() -> void:
	GameManager.learn(["stop"])


func _open_target() -> void:
	var sess: Dictionary = GameManager.state.get("active_session", {})
	var target = sess.get("target_file", null)
	if target == null:
		target = GameManager.status.get("today_note", {}).get("path", "")
	GameManager.obsidian_open(str(target))


func _open_rel(rel: String) -> void:
	if rel.ends_with(".md"):
		GameManager.obsidian_open(rel)


func _highlight() -> void:
	var t := hl_edit.text.strip_edges()
	if t == "":
		return
	hl_edit.text = ""
	if t.contains("::"):
		GameManager.learn(["card", t])
	else:
		GameManager.learn(["highlight", t])


func _question() -> void:
	var t := q_edit.text.strip_edges()
	if t == "":
		return
	q_edit.text = ""
	GameManager.learn(["q", t])


func _pages() -> void:
	GameManager.learn(["pages", str(int(pages_spin.value))])


# ------------------------------------------------------------------ flashcards

func _load_quiz() -> void:
	recharge_btn.disabled = true
	GameManager.learn(["quiz", "--count", "5"], _on_quiz, false, true)


func _on_quiz(r: Dictionary) -> void:
	recharge_btn.disabled = false
	_quiz = r.get("questions", [])
	_qi = 0
	if _quiz.is_empty():
		card_front.text = "No flashcards yet. Capture a >> highlight first."
		card_back.text = ""
		_set_card_buttons(false, false)
		return
	_show_card()


func _show_card() -> void:
	if _qi >= _quiz.size():
		card_front.text = "Reactor charged. ⚡  Come back tomorrow for more due cards."
		card_back.text = ""
		_set_card_buttons(false, false)
		GameManager.refresh()
		return
	var q: Dictionary = _quiz[_qi]
	card_front.text = "Q%d/%d  %s" % [_qi + 1, _quiz.size(), str(q.get("front", ""))]
	card_back.text = ""
	_set_card_buttons(true, false)


func _reveal() -> void:
	if _qi < _quiz.size():
		card_back.text = str(_quiz[_qi].get("back", ""))
		_set_card_buttons(false, true)


func _answer(correct: bool) -> void:
	if _qi >= _quiz.size():
		return
	var q: Dictionary = _quiz[_qi]
	GameManager.learn(["quiz", "--answer", str(q.get("id", "")), "--correct" if correct else "--wrong"], Callable(), false)
	_qi += 1
	_show_card()


func _set_card_buttons(can_reveal: bool, can_grade: bool) -> void:
	reveal_btn.disabled = not can_reveal
	good_btn.disabled = not can_grade
	miss_btn.disabled = not can_grade
