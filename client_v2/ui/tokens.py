BG_APP = "#F0F2F7"
BG_CARD = "#FFFFFF"
BG_ROW_HOVER = "#F5F7FF"
SIDEBAR_BG = "#1E3A8A"
SIDEBAR_ACTIVE = "#2563EB"
SIDEBAR_TEXT = "#93C5FD"
SIDEBAR_TEXT_ON = "#FFFFFF"
SIDEBAR_HOVER = "#1E40AF"
TITLEBAR_BG = "#FFFFFF"
TITLEBAR_BORDER = "#E5E7EB"
TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#6B7280"
TEXT_MUTED = "#9CA3AF"
TEXT_LINK = "#2563EB"
BORDER_DEFAULT = "#E5E7EB"
BORDER_FOCUS = "#2563EB"
STATUS_OK = "#10B981"
STATUS_WARN = "#F59E0B"
STATUS_FAIL = "#EF4444"
STATUS_UNKNOWN = "#9CA3AF"
STATUS_OK_BG = "#D1FAE5"
STATUS_WARN_BG = "#FEF3C7"
STATUS_FAIL_BG = "#FEE2E2"
STATUS_UNKNOWN_BG = "#F3F4F6"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_LIGHT = "#EFF6FF"
BTN_CLOSE_HOVER = "#EF4444"
WINDOW_W, WINDOW_H, WINDOW_RADIUS = 900, 580, 10
TITLEBAR_H, SIDEBAR_W = 44, 176
RING_OUTER_D, RING_STROKE, RING_INNER_D = 180, 8, 156
ROW_H, ROW_DOT_D, ROW_PADDING_X = 44, 10, 24
BTN_H_PRIMARY, BTN_W_PRIMARY, BTN_RADIUS = 44, 180, 8
SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL = 4, 8, 16, 24, 40
FONT_UI_FAMILY, FONT_MONO_FAMILY = "Microsoft YaHei UI", "Consolas"
FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD = 10, 11, 13
FONT_SIZE_LG, FONT_SIZE_XL, FONT_SIZE_XXL, FONT_SIZE_HERO = 15, 20, 28, 40
ANIM_FAST, ANIM_NORMAL, ANIM_SLOW, ANIM_BREATH = 120, 240, 400, 2600


def status_color(status: str) -> str:
    return {"PASS": STATUS_OK, "WARNING": STATUS_WARN, "FAIL": STATUS_FAIL, "UNKNOWN": STATUS_UNKNOWN}.get(status.upper(), STATUS_UNKNOWN)


def status_bg(status: str) -> str:
    return {"PASS": STATUS_OK_BG, "WARNING": STATUS_WARN_BG, "FAIL": STATUS_FAIL_BG, "UNKNOWN": STATUS_UNKNOWN_BG}.get(status.upper(), STATUS_UNKNOWN_BG)


APP_STYLESHEET = f"""
* {{ font-family: '{FONT_UI_FAMILY}'; font-size: 13px; color: {TEXT_PRIMARY}; outline: none; }}
QWidget#chrome {{ background: {BG_APP}; border: 1px solid {BORDER_DEFAULT}; border-radius: {WINDOW_RADIUS}px; }}
QWidget#content {{ background: {BG_APP}; }}
QFrame[card='true'] {{ background: {BG_CARD}; border: 1px solid {BORDER_DEFAULT}; border-radius: 10px; }}
QLabel[muted='true'] {{ color: {TEXT_SECONDARY}; }}
QLabel[title='true'] {{ font-size: 26px; font-weight: 700; }}
QLabel[subhead='true'] {{ font-size: 15px; font-weight: 700; }}
QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {BORDER_DEFAULT}; border-radius: 7px; background: white; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton[primary='true'] {{ min-height: {BTN_H_PRIMARY}px; background: {ACCENT}; color: white; border: 0; border-radius: {BTN_RADIUS}px; font-weight: 700; }}
QPushButton[primary='true']:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton:disabled {{ background: #E5E7EB; color: {TEXT_MUTED}; border: 0; }}
QComboBox, QLineEdit {{ min-height: 38px; background: white; border: 1px solid {BORDER_DEFAULT}; border-radius: 7px; padding: 0 10px; }}
QScrollArea {{ border: 0; background: transparent; }}
"""
