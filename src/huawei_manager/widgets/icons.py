"""Sprite SVG do MVP — mesmos símbolos de ``huawei-manager-mvp-main/index.html``.

Os paths foram extraídos do ``<svg><symbol>`` do MVP (viewBox 24×24, exceto
``i-logo`` que é 32×32). A renderização usa ``QSvgRenderer`` com os mesmos
atributos do CSS ``.icon`` do MVP: ``fill: none; stroke: currentColor;
stroke-width: 1.75; stroke-linecap/join: round``.

A cor é resolvida por parâmetro (o QSvg não herda ``currentColor`` do tema),
por isso cada chamada recebe a cor desejada e o ícone é regerado quando o
tema muda (o app já reconstrói a UI ao alternar tema).
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

# ─── Sprite (viewBox 0 0 24 24 salvo indicação) ─────────────────────
_SPRITE: dict[str, str] = {
    "i-activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "i-alert-triangle": (
        '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    "i-archive": (
        '<rect x="2" y="4" width="20" height="5" rx="1"/>'
        '<path d="M4 9v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9"/>'
        '<line x1="10" y1="14" x2="14" y2="14"/>'
    ),
    "i-arrow-left": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "i-arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "i-audit": (
        '<path d="M9 3h6l4 4v14H5V3Z"/><polyline points="9 12 11 14 15 10"/>'
        '<line x1="9" y1="18" x2="15" y2="18"/>'
    ),
    "i-ban": '<circle cx="12" cy="12" r="9"/><line x1="5.6" y1="5.6" x2="18.4" y2="18.4"/>',
    "i-calendar": (
        '<rect x="3" y="5" width="18" height="16" rx="2"/>'
        '<line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/>'
        '<line x1="3" y1="10" x2="21" y2="10"/>'
    ),
    "i-check": '<polyline points="20 6 9 17 4 12"/>',
    "i-chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "i-chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "i-circle-check": '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16.5 9"/>',
    "i-clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/>',
    "i-copy": (
        '<rect x="9" y="9" width="12" height="12" rx="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
    ),
    "i-cpu": (
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>'
    ),
    "i-database": (
        '<ellipse cx="12" cy="5" rx="8" ry="3"/>'
        '<path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
        '<path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'
    ),
    "i-download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    "i-eye": (
        '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "i-file-text": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'
        '<line x1="10" y1="9" x2="8" y2="9"/>'
    ),
    "i-filter": '<polygon points="22 3 2 3 10 12.5 10 19 14 21 14 12.5 22 3"/>',
    "i-gauge": (
        '<path d="M4.2 18a9 9 0 1 1 15.6 0"/>'
        '<line x1="12" y1="14" x2="16" y2="9"/><circle cx="12" cy="14" r="1.5"/>'
    ),
    "i-globe": (
        '<circle cx="12" cy="12" r="9"/>'
        '<ellipse cx="12" cy="12" rx="4" ry="9"/>'
        '<line x1="3" y1="12" x2="21" y2="12"/>'
    ),
    "i-grid": (
        '<rect x="3" y="3" width="7" height="7" rx="1"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1"/>'
    ),
    "i-home": (
        '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
    ),
    "i-info": (
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="11" x2="12" y2="16"/>'
        '<line x1="12" y1="8" x2="12.01" y2="8"/>'
    ),
    "i-key": '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m11 12 10-10M16 4l4 4M18 2l4 4"/>',
    "i-layers": (
        '<polygon points="12 2 22 7 12 12 2 7 12 2"/>'
        '<polyline points="2 12 12 17 22 12"/>'
        '<polyline points="2 17 12 22 22 17"/>'
    ),
    "i-link": (
        '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/>'
        '<path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>'
    ),
    "i-lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    # Logo é o único símbolo 32×32, com strokes próprios (1.45/1.55).
    "i-logo": (
        '<path d="M16 2.9 28 9.5v13L16 29.1 4 22.5v-13Z" stroke-width="1.55"/>'
        '<ellipse cx="16" cy="16" rx="9.4" ry="4.1" stroke-width="1.45" transform="rotate(36 16 16)"/>'
        '<ellipse cx="16" cy="16" rx="9.4" ry="4.1" stroke-width="1.45" transform="rotate(-36 16 16)"/>'
        '<circle cx="16" cy="16" r="2.15" fill="{color}" stroke="none"/>'
    ),
    "i-menu": (
        '<line x1="4" y1="7" x2="20" y2="7"/>'
        '<line x1="4" y1="12" x2="20" y2="12"/>'
        '<line x1="4" y1="17" x2="20" y2="17"/>'
    ),
    "i-minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "i-monitor": (
        '<rect x="2" y="3" width="20" height="14" rx="2"/>'
        '<line x1="8" y1="21" x2="16" y2="21"/>'
        '<line x1="12" y1="17" x2="12" y2="21"/>'
    ),
    "i-moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>',
    "i-panel-collapse": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<line x1="9" y1="4" x2="9" y2="20"/>'
        '<path d="m16.5 9-3 3 3 3"/>'
    ),
    "i-panel-expand": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<line x1="9" y1="4" x2="9" y2="20"/>'
        '<path d="m13.5 9 3 3-3 3"/>'
    ),
    "i-play": '<polygon points="7 4 21 12 7 20 7 4"/>',
    "i-plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "i-power": '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/><line x1="12" y1="2" x2="12" y2="10"/>',
    "i-radio": (
        '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/>'
        '<path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/>'
        '<circle cx="12" cy="12" r="2"/>'
        '<path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/>'
        '<path d="M19.1 4.9C23 8.8 23 15.2 19.1 19.1"/>'
    ),
    "i-refresh": '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>',
    "i-restore": (
        '<rect x="8" y="4" width="12" height="12" rx="1.5"/>'
        '<path d="M16 16v3a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h3"/>'
    ),
    "i-route": (
        '<circle cx="6" cy="19" r="3"/>'
        '<path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/>'
        '<circle cx="18" cy="5" r="3"/>'
    ),
    "i-search": '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.2" y2="16.2"/>',
    "i-server": (
        '<rect x="3" y="4" width="18" height="6" rx="2"/>'
        '<rect x="3" y="14" width="18" height="6" rx="2"/>'
        '<line x1="7" y1="7" x2="7.01" y2="7"/><line x1="7" y1="17" x2="7.01" y2="17"/>'
    ),
    "i-settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06'
        'a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09'
        'a1.7 1.7 0 0 0-1.1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06'
        'A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09'
        'A1.7 1.7 0 0 0 4.6 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06'
        'A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.6'
        'a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9'
        'c.14.4.5.7.95.8H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.2Z"/>'
    ),
    "i-shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
    "i-shield-check": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>'
        '<polyline points="8.5 12 11 14.5 15.5 10"/>'
    ),
    "i-shield-off": (
        '<path d="M19.7 14A10.7 10.7 0 0 1 20 12V5l-8-3-3.2 1.2"/>'
        '<path d="M4.7 4.7 4 5v7c0 6 8 10 8 10a15 15 0 0 0 4.2-3.1"/>'
        '<line x1="2" y1="2" x2="22" y2="22"/>'
    ),
    "i-sliders": (
        '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
        '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
        '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
        '<line x1="17" y1="16" x2="23" y2="16"/>'
    ),
    "i-square": '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
    "i-sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
        'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'
    ),
    "i-target": (
        '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/>'
        '<circle cx="12" cy="12" r="1" fill="{color}" stroke="none"/>'
    ),
    "i-terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "i-trash": (
        '<polyline points="3 6 5 6 21 6"/>'
        '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
        '<path d="M10 11v6M14 11v6"/>'
        '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
    ),
    "i-user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "i-volume": (
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
        '<path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>'
    ),
    "i-wifi": (
        '<path d="M5 12.6a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/>'
        '<path d="M2 9a15 15 0 0 1 20 0"/>'
        '<circle cx="12" cy="19.5" r="1" fill="{color}" stroke="none"/>'
    ),
    "i-wrench": (
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77'
        'a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91'
        'a6 6 0 0 1 7.94-7.94l-3.76 3.76Z"/>'
    ),
    "i-x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "i-zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
}

_LOGO_VIEWBOX = 32


def _svg_source(icon_id: str, color: str) -> str:
    """Monta o documento SVG completo do símbolo, já colorido."""
    body = _SPRITE.get(icon_id, _SPRITE["i-square"])
    body = body.replace("{color}", color)
    vb = _LOGO_VIEWBOX if icon_id == "i-logo" else 24
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" '
        f'fill="none" stroke="{color}" stroke-width="1.75" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def icon_pixmap(icon_id: str, color: str, size: int) -> QPixmap:
    """Renderiza o símbolo ``icon_id`` em um ``QPixmap`` de ``size`` px."""
    if icon_id not in _SPRITE:
        icon_id = "i-square"
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(_svg_source(icon_id, color).encode("utf-8")))
    # 2× + SmoothTransformation ≈ anti-aliasing nítido em telas 1×/2×.
    raw = QPixmap(size * 2, size * 2)
    raw.fill(Qt.GlobalColor.transparent)
    painter = QPainter(raw)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return raw.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def icon(icon_id: str, color: str, size: int = 19) -> QIcon:
    """``QIcon`` do símbolo — usado em botões da sidebar/topbar."""
    pm = icon_pixmap(icon_id, color, size)
    out = QIcon()
    out.addPixmap(pm)
    return out


def icon_label_markup(icon_id: str, color: str, size: int) -> str:
    """SVG inline para ``QLabel`` via ``setText`` (rich text do Qt)."""
    svg = _svg_source(icon_id, color)
    return (
        f'<div style="width:{size}px;height:{size}px;'
        f'vertical-align:middle;">{svg}</div>'
    )


def available_icons() -> list[str]:
    """IDs disponíveis no sprite (para testes/diagnóstico)."""
    return sorted(_SPRITE)
