def _css_font(font_tuple: tuple) -> str:
    family, size, *_ = font_tuple
    weight = "bold" if len(font_tuple) > 2 and font_tuple[2] == "bold" else "normal"
    return f"{weight} {size}px '{family}'"
