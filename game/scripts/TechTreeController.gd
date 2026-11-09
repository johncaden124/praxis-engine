extends HSplitContainer
## Room [3] Tech Tree & Curriculum Benchmarks.
## Everything here is read from 01 Plan/ (benchmarks.md, Gather List.md,
## curriculum_manifest.yaml) via `learn status`, so swapping the curriculum
## re-skins the tree automatically.

const UI = preload("res://scripts/UI.gd")

var tabs: TabContainer
var tree_box: HBoxContainer
var bench_box: VBoxContainer
var gather_box: VBoxContainer
var detail: VBoxContainer
var summary_label: Label

var _tech: Array = []
var _selected := ""
var _items: Dictionary = {}


func _ready() -> void:
	split_offset = 260
	var left := UI.vbox(8)
	UI.expand(left)
	summary_label = UI.label("", 14, UI.MUTED, true)
	left.add_child(summary_label)
	tabs = TabContainer.new()
	UI.expand(tabs)
	left.add_child(tabs)

	var tree_scroll := ScrollContainer.new()
	tree_scroll.name = "Tech Tree"
	tree_box = UI.hbox(16)
	UI.expand(tree_box)
	tree_scroll.add_child(tree_box)
	tabs.add_child(tree_scroll)

	var bscroll := ScrollContainer.new()
	bscroll.name = "Benchmarks & Credentials"
	bench_box = UI.vbox(4)
	UI.expand(bench_box, true, false)
	bscroll.add_child(bench_box)
	tabs.add_child(bscroll)

	var gscroll := ScrollContainer.new()
	gscroll.name = "Gather List"
	gather_box = UI.vbox(4)
	UI.expand(gather_box, true, false)
	gscroll.add_child(gather_box)
	tabs.add_child(gscroll)
	add_child(left)

	detail = UI.vbox(10)
	detail.custom_minimum_size = Vector2(380, 0)
	var dp := UI.panel(detail)
	dp.custom_minimum_size = Vector2(400, 0)
	add_child(dp)
	_show_detail("")

	GameManager.status_changed.connect(_on_status)
	if not GameManager.status.is_empty():
		_on_status(GameManager.status)


func _on_status(st: Dictionary) -> void:
	_tech = st.get("tech_tree", [])
	_items.clear()
	for i in st.get("benchmarks", []):
		_items[i["id"]] = i
	for i in st.get("gather", []):
		_items[i["id"]] = i
	var s: Dictionary = st.get("state", {})
	var unlocked := 0
	for t in _tech:
		if t.get("unlocked", false):
			unlocked += 1
	var done_b := 0
	for i in st.get("benchmarks", []):
		if i.get("done", false):
			done_b += 1
	summary_label.text = "%s · Stage %d · %d/%d tech nodes online · %d/%d benchmarks & credentials" % [
		str(s.get("curriculum_name", "")), int(s.get("stage", 1)), unlocked, _tech.size(), done_b, st.get("benchmarks", []).size()]
	_build_tree(int(s.get("stage", 1)))
	_build_checklist(bench_box, st.get("benchmarks", []))
	_build_checklist(gather_box, st.get("gather", []))
	_show_detail(_selected)


func _build_tree(current_stage: int) -> void:
	UI.clear(tree_box)
	var stages := {}
	for t in _tech:
		var n := int(t.get("stage", 1))
		if not stages.has(n):
			stages[n] = []
		stages[n].append(t)
	var keys := stages.keys()
	keys.sort()
	for n in keys:
		var col := UI.vbox(8)
		col.custom_minimum_size = Vector2(230, 0)
		col.add_child(UI.header("Stage %d%s" % [n, "  ◀ you are here" if n == current_stage else ""], UI.ACCENT if n == current_stage else UI.MUTED))
		for t in stages[n]:
			col.add_child(_tech_button(t))
		tree_box.add_child(col)


func _tech_button(t: Dictionary) -> Button:
	var unlocked: bool = t.get("unlocked", false)
	var sources: Array = t.get("sources", [])
	var done := 0
	for src in sources:
		if src.get("done", false):
			done += 1
	var label := "%s %s" % ["◆" if unlocked else "◇", str(t.get("name", t.get("id", "")))]
	if not unlocked and sources.size() > 0:
		label += "\n   %d/%d sources · any one unlocks" % [done, sources.size()]
	var b := UI.button(label, _select.bind(str(t.get("id", ""))), str(t.get("description", "")))
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.custom_minimum_size = Vector2(220, 52)
	var color := UI.ACCENT if unlocked else UI.LINE
	var bg := Color(0.22, 0.85, 0.54, 0.12) if unlocked else UI.PANEL_2
	if str(t.get("id", "")) == _selected:
		color = UI.ACCENT_2
	b.add_theme_stylebox_override("normal", UI.box(bg, color, 8, 12, 2 if unlocked else 1))
	b.add_theme_color_override("font_color", UI.TEXT if unlocked else UI.MUTED)
	return b


func _select(id: String) -> void:
	_selected = id
	_show_detail(id)
	_build_tree(int(GameManager.state.get("stage", 1)))


func _show_detail(id: String) -> void:
	UI.clear(detail)
	var t := {}
	for x in _tech:
		if str(x.get("id", "")) == id:
			t = x
	if t.is_empty():
		detail.add_child(UI.header("Tech node"))
		detail.add_child(UI.label("Select a node to see what it does in-game and which real-world achievements unlock it.", 15, UI.MUTED, true))
		detail.add_child(UI.label("Checking a benchmark here runs `learn benchmark <id>`: it ticks the box in 01 Plan/benchmarks.md, unlocks tech, and recompiles your résumé.", 13, UI.MUTED, true))
		return
	var unlocked: bool = t.get("unlocked", false)
	detail.add_child(UI.header("Stage %s · %s" % [str(t.get("stage", "")), str(t.get("track", ""))], UI.ACCENT if unlocked else UI.MUTED))
	detail.add_child(UI.title(str(t.get("name", id)), 24))
	detail.add_child(UI.label("ONLINE" if unlocked else "OFFLINE", 13, UI.ACCENT if unlocked else UI.WARN))
	detail.add_child(UI.label(str(t.get("description", "")), 15, UI.TEXT, true))
	var eff: Dictionary = t.get("effect", {})
	var parts := PackedStringArray()
	for k in eff.keys():
		parts.append("%s: %s" % [k, str(eff[k])])
	detail.add_child(UI.label("Effect — " + ", ".join(parts), 13, UI.ACCENT_2, true))
	detail.add_child(HSeparator.new())
	var sources: Array = t.get("sources", [])
	if sources.is_empty():
		detail.add_child(UI.label("Starting equipment.", 14, UI.MUTED))
		return
	detail.add_child(UI.header("Unlocked by any of"))
	for src in sources:
		var sid := str(src.get("id", ""))
		if _items.has(sid):
			detail.add_child(_check_row(_items[sid]))
		else:
			var l := UI.label("%s %s" % ["✅" if src.get("done", false) else "🛰", str(src.get("text", sid))], 14, UI.TEXT, true)
			detail.add_child(l)


func _build_checklist(box: VBoxContainer, items: Array) -> void:
	UI.clear(box)
	var section := ""
	var sub := ""
	for i in items:
		if str(i.get("section", "")) != section:
			section = str(i.get("section", ""))
			sub = ""
			var h := UI.header(section, UI.ACCENT)
			box.add_child(h)
		if str(i.get("subsection", "")) != sub and str(i.get("subsection", "")) != "":
			sub = str(i.get("subsection", ""))
			box.add_child(UI.label("  " + sub, 13, UI.MUTED))
		box.add_child(_check_row(i))


func _check_row(i: Dictionary) -> Control:
	var row := UI.hbox(6)
	var cb := CheckBox.new()
	cb.button_pressed = i.get("done", false)
	cb.focus_mode = Control.FOCUS_NONE
	cb.toggled.connect(_on_toggle.bind(str(i.get("id", ""))))
	row.add_child(cb)
	var l := UI.label("%s   (%s)" % [str(i.get("text", "")), str(i.get("id", ""))], 14, UI.ACCENT if i.get("done", false) else UI.TEXT, true)
	row.add_child(l)
	return row


func _on_toggle(pressed: bool, id: String) -> void:
	var args := ["benchmark", id]
	if not pressed:
		args.append("--undo")
	GameManager.learn(args)
