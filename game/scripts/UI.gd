extends RefCounted
## Procedural theme + small widget factory. No external art assets needed.

const BG := Color("0b0f14")
const PANEL := Color("121923")
const PANEL_2 := Color("17212e")
const LINE := Color("223040")
const TEXT := Color("e6edf3")
const MUTED := Color("8b98a7")
const ACCENT := Color("39d98a")
const ACCENT_2 := Color("4fc3f7")
const WARN := Color("ffb74d")
const DANGER := Color("ff5c7a")
const VIOLET := Color("ba68c8")


static func box(bg: Color, border: Color = LINE, radius: int = 8, pad: int = 10, border_w: int = 1) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border
	sb.set_border_width_all(border_w)
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = pad
	sb.content_margin_right = pad
	sb.content_margin_top = pad * 0.6
	sb.content_margin_bottom = pad * 0.6
	return sb


static func make_theme() -> Theme:
	var t := Theme.new()
	t.default_font_size = 15
	var mono := SystemFont.new()
	mono.font_names = PackedStringArray(["SF Mono", "Menlo", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", "monospace"])
	var sans := SystemFont.new()
	sans.font_names = PackedStringArray(["SF Pro Text", "Helvetica Neue", "Inter", "Segoe UI", "Roboto", "DejaVu Sans", "sans-serif"])
	t.default_font = sans

	for cls in ["Label", "Button", "LineEdit", "TextEdit", "CodeEdit", "OptionButton", "CheckBox", "ItemList", "RichTextLabel", "SpinBox", "TabContainer", "TabBar"]:
		t.set_color("font_color", cls, TEXT)
	t.set_color("font_color", "Label", TEXT)
	t.set_color("default_color", "RichTextLabel", TEXT)

	# Buttons
	t.set_stylebox("normal", "Button", box(PANEL_2, LINE, 6, 12))
	t.set_stylebox("hover", "Button", box(Color("1d2a3a"), ACCENT_2, 6, 12))
	t.set_stylebox("pressed", "Button", box(Color("0f2a1f"), ACCENT, 6, 12))
	t.set_stylebox("disabled", "Button", box(Color("10161e"), LINE, 6, 12))
	t.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), ACCENT_2, 6, 12))
	t.set_color("font_hover_color", "Button", Color.WHITE)
	t.set_color("font_pressed_color", "Button", ACCENT)
	t.set_color("font_disabled_color", "Button", MUTED)
	for cls in ["OptionButton"]:
		t.set_stylebox("normal", cls, box(PANEL_2, LINE, 6, 10))
		t.set_stylebox("hover", cls, box(Color("1d2a3a"), ACCENT_2, 6, 10))
		t.set_stylebox("pressed", cls, box(Color("0f2a1f"), ACCENT, 6, 10))
		t.set_stylebox("focus", cls, box(Color(0, 0, 0, 0), ACCENT_2, 6, 10))

	# Inputs
	for cls in ["LineEdit", "TextEdit", "CodeEdit"]:
		t.set_stylebox("normal", cls, box(Color("0d131b"), LINE, 6, 10))
		t.set_stylebox("focus", cls, box(Color("0d131b"), ACCENT_2, 6, 10))
		t.set_color("caret_color", cls, ACCENT)
		t.set_color("selection_color", cls, Color(0.31, 0.76, 0.97, 0.25))
	t.set_color("font_placeholder_color", "LineEdit", MUTED)
	t.set_font("font", "CodeEdit", mono)
	t.set_font_size("font_size", "CodeEdit", 14)
	t.set_color("background_color", "CodeEdit", Color("0d131b"))
	t.set_color("current_line_color", "CodeEdit", Color("141d29"))
	t.set_color("line_number_color", "CodeEdit", Color("4a5868"))

	# Panels / containers
	t.set_stylebox("panel", "PanelContainer", box(PANEL, LINE, 10, 14))
	t.set_stylebox("panel", "Panel", box(PANEL, LINE, 10, 14))
	t.set_stylebox("panel", "ItemList", box(Color("0d131b"), LINE, 6, 6))
	t.set_stylebox("panel", "TabContainer", box(PANEL, LINE, 8, 10))
	t.set_stylebox("tab_selected", "TabContainer", box(PANEL, ACCENT, 6, 12))
	t.set_stylebox("tab_unselected", "TabContainer", box(Color("0d131b"), LINE, 6, 12))
	t.set_stylebox("tab_hovered", "TabContainer", box(PANEL_2, ACCENT_2, 6, 12))
	t.set_color("font_selected_color", "TabContainer", ACCENT)
	t.set_color("font_unselected_color", "TabContainer", MUTED)
	t.set_stylebox("normal", "RichTextLabel", box(Color("070a0e"), LINE, 6, 10))
	t.set_font("normal_font", "RichTextLabel", mono)
	t.set_font_size("normal_font_size", "RichTextLabel", 13)

	# Progress bars
	t.set_stylebox("background", "ProgressBar", box(Color("0d131b"), LINE, 6, 0))
	t.set_stylebox("fill", "ProgressBar", box(ACCENT, ACCENT, 6, 0))
	t.set_color("font_color", "ProgressBar", TEXT)

	t.set_color("font_color", "ItemList", TEXT)
	t.set_color("font_selected_color", "ItemList", ACCENT)
	t.set_stylebox("selected", "ItemList", box(Color("0f2a1f"), ACCENT, 4, 4))
	t.set_stylebox("selected_focus", "ItemList", box(Color("0f2a1f"), ACCENT, 4, 4))
	t.set_constant("separation", "HBoxContainer", 10)
	t.set_constant("separation", "VBoxContainer", 10)
	return t


static func mono_font() -> Font:
	var mono := SystemFont.new()
	mono.font_names = PackedStringArray(["SF Mono", "Menlo", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", "monospace"])
	return mono


static func label(text: String, size: int = 15, color: Color = TEXT, wrap: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


static func header(text: String, color: Color = MUTED) -> Label:
	var l := label(text.to_upper(), 12, color)
	l.add_theme_font_override("font", mono_font())
	return l


static func title(text: String, size: int = 22) -> Label:
	return label(text, size, TEXT)


static func button(text: String, cb: Callable, tooltip: String = "") -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tooltip
	b.focus_mode = Control.FOCUS_NONE
	if cb.is_valid():
		b.pressed.connect(cb)
	return b


static func accent_button(text: String, cb: Callable, color: Color = ACCENT) -> Button:
	var b := button(text, cb)
	b.add_theme_stylebox_override("normal", box(Color(color.r, color.g, color.b, 0.16), color, 6, 14))
	b.add_theme_stylebox_override("hover", box(Color(color.r, color.g, color.b, 0.28), color, 6, 14))
	b.add_theme_color_override("font_color", color.lightened(0.2))
	return b


static func panel(child: Control = null, bg: Color = PANEL) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", box(bg, LINE, 10, 14))
	if child:
		p.add_child(child)
	return p


static func vbox(sep: int = 10) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func hbox(sep: int = 10) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", sep)
	return h


static func spacer() -> Control:
	var c := Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return c


static func expand(c: Control, h: bool = true, v: bool = true) -> Control:
	if h:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if v:
		c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return c


static func bar(color: Color, value: float, max_value: float = 100.0, height: int = 10) -> ProgressBar:
	var p := ProgressBar.new()
	p.min_value = 0
	p.max_value = max(max_value, 1.0)
	p.value = value
	p.show_percentage = false
	p.custom_minimum_size = Vector2(0, height)
	p.add_theme_stylebox_override("fill", box(color, color, 6, 0))
	return p


static func bb_escape(s: String) -> String:
	return s.replace("[", "[lb]")


static func status_color(status: String) -> Color:
	match status:
		"active":
			return ACCENT
		"cooling":
			return WARN
		_:
			return DANGER


static func clear(node: Node) -> void:
	for c in node.get_children():
		node.remove_child(c)
		c.queue_free()
