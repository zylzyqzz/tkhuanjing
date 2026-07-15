THEMES = {
    "obsidian": {
        "name": "黑曜石旗舰", "bg": "#050A12", "surface": "#091321", "surface2": "#0D1A2B", "line": "#1C3554",
        "text": "#EAF3FF", "muted": "#7E93AF", "blue": "#4DAAFF", "cyan": "#4FE6D2", "gold": "#E9A84B",
        "pass": "#4EE0A1", "warning": "#F2B45F", "fail": "#FF6075", "unknown": "#8798AE",
    },
    "cyber": {
        "name": "赛博蓝", "bg": "#070615", "surface": "#11102A", "surface2": "#17143A", "line": "#3B3478",
        "text": "#F4F0FF", "muted": "#9A91BD", "blue": "#7A74FF", "cyan": "#38D9FF", "gold": "#F4A65D",
        "pass": "#42E7B0", "warning": "#FFC266", "fail": "#FF5F8F", "unknown": "#938DA8",
    },
    "daylight": {
        "name": "极昼浅色", "bg": "#EAF1F8", "surface": "#FFFFFF", "surface2": "#F4F8FC", "line": "#B8C9DA",
        "text": "#15263A", "muted": "#60758B", "blue": "#1677D2", "cyan": "#159EAD", "gold": "#B97416",
        "pass": "#178A61", "warning": "#A9670B", "fail": "#C93652", "unknown": "#6C7C8F",
    },
}

COLORS = {
    "bg": "#050A12", "surface": "#091321", "surface2": "#0D1A2B", "line": "#1C3554",
    "text": "#EAF3FF", "muted": "#7E93AF", "blue": "#4DAAFF", "cyan": "#4FE6D2",
    "gold": "#E9A84B", "pass": "#4EE0A1", "warning": "#F2B45F", "fail": "#FF6075", "unknown": "#8798AE",
}

BASE_STYLESHEET = r"""
* { font-family: "Noto Sans SC", "Microsoft YaHei UI"; font-size: 13px; color: #DDE9F8; }
QMainWindow { background: transparent; }
QWidget#windowChrome { background: #050A12; border: 1px solid rgba(94,153,222,.34); border-radius: 18px; }
QFrame#titleBar { min-height: 46px; max-height: 46px; background: rgba(5,12,22,.94); border-bottom: 1px solid rgba(84,140,207,.20); border-top-left-radius: 18px; border-top-right-radius: 18px; }
QLabel#brandMark { color: #55C8FF; font-size: 22px; font-weight: 900; }
QLabel#windowTitle { font-size: 14px; font-weight: 700; letter-spacing: .5px; }
QLabel#versionPill { color: #55DDBD; background: rgba(41,139,119,.16); border: 1px solid rgba(76,222,188,.28); border-radius: 9px; padding: 3px 8px; font-size: 11px; }
QPushButton#windowControl { min-width: 36px; max-width: 36px; min-height: 30px; border: 0; background: transparent; color: #7F94AE; font-size: 16px; padding: 0; }
QPushButton#windowControl:hover { color: white; background: rgba(94,148,214,.16); }
QFrame#sidebar { background: rgba(6,14,25,.94); border-right: 1px solid rgba(77,135,201,.18); }
QLabel#sideBrand { color: #EAF4FF; font-size: 15px; font-weight: 900; letter-spacing: 1px; padding: 16px 0 24px; }
QPushButton[nav="true"] { min-height: 48px; text-align: left; padding: 8px 16px; border: 1px solid transparent; border-radius: 12px; background: transparent; color: #7188A5; font-weight: 600; }
QPushButton[nav="true"]:hover { color: #DCEBFF; background: rgba(41,94,154,.16); border-color: rgba(80,146,220,.20); }
QPushButton[nav="true"]:checked { color: white; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(40,119,204,.38),stop:1 rgba(25,68,119,.13)); border-color: rgba(81,169,255,.42); }
QLabel#pageEyebrow { color: #4DB7FF; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
QLabel#pageTitle { color: #F4F8FF; font-size: 27px; font-weight: 800; }
QLabel#pageSubtitle { color: #8296B1; font-size: 13px; }
QFrame[card="true"], QFrame[metricCard="true"], QFrame[moduleTile="true"] { background: rgba(10,23,39,.88); border: 1px solid rgba(83,145,213,.22); border-radius: 15px; }
QFrame[modeCard="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(15,37,63,.96),stop:.65 rgba(8,21,37,.96),stop:1 rgba(12,16,27,.98)); border: 1px solid rgba(83,155,232,.28); border-radius: 20px; }
QFrame[modeCard="true"]:hover { border: 1px solid rgba(99,184,255,.70); background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(20,51,86,.98),stop:.65 rgba(9,27,47,.98),stop:1 rgba(14,20,34,.98)); }
QLabel#modeIcon { font-size: 32px; font-weight: 900; }
QLabel#eyebrow { border: 1px solid; border-radius: 9px; padding: 4px 9px; font-size: 10px; font-weight: 800; }
QLabel#modeTitle { color: #F5F9FF; font-size: 22px; font-weight: 800; padding-top: 5px; }
QLabel#modeDescription { color: #8EA4BF; font-size: 13px; line-height: 1.6; }
QPushButton#modeButton { min-height: 46px; border: 0; border-radius: 11px; color: #05101E; font-size: 14px; font-weight: 900; }
QLabel#metricLabel { color: #7188A5; font-size: 11px; }
QLabel#metricValue { color: #F4F8FF; font-size: 24px; font-weight: 800; }
QLabel#metricUnit { color: #7289A5; padding-top: 8px; }
QFrame[moduleTile="true"] { min-height: 46px; }
QFrame[moduleTile="true"][state="running"] { background: rgba(29,83,137,.30); border-color: #42A9FF; }
QFrame[moduleTile="true"][state="success"] { border-color: rgba(68,220,159,.48); }
QFrame[moduleTile="true"][state="warning"] { border-color: rgba(242,180,95,.55); }
QFrame[moduleTile="true"][state="fail"] { border-color: rgba(255,96,117,.60); }
QLabel#moduleGlyph { color: #55BFFF; font-size: 11px; font-weight: 900; min-width: 34px; }
QLabel#moduleState { color: #7489A3; font-size: 11px; }
QTextEdit#terminal { background: rgba(2,8,15,.84); border: 1px solid rgba(74,139,207,.24); border-radius: 13px; padding: 13px; font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px; }
QPushButton { color: #DCE9FA; background: rgba(19,43,72,.85); border: 1px solid rgba(91,151,218,.30); border-radius: 10px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { color: white; background: rgba(27,65,108,.95); border-color: rgba(101,178,255,.62); }
QPushButton:disabled { color: #53677F; background: rgba(12,25,42,.65); border-color: rgba(60,92,128,.18); }
QPushButton[primary="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2C8DFF,stop:1 #4BD9E7); border: 0; color: #04101D; font-weight: 900; }
QPushButton[gold="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #E7A648,stop:1 #F4CA71); border: 0; color: #171005; font-weight: 900; }
QPushButton[danger="true"] { background: rgba(140,38,58,.34); border-color: rgba(255,91,116,.55); color: #FF9EAA; }
QComboBox, QLineEdit, QTextEdit, QSpinBox { background: rgba(4,13,23,.88); color: #E7F0FC; border: 1px solid rgba(83,143,207,.31); border-radius: 10px; padding: 9px 12px; selection-background-color: #2D8DFF; }
QComboBox:focus, QLineEdit:focus { border-color: #4CAEFF; }
QComboBox::drop-down { border: 0; width: 30px; }
QComboBox QAbstractItemView { background: #0A1728; border: 1px solid #244A73; selection-background-color: #1F568D; }
QTabWidget#settingsTabs { background: transparent; }
QTabWidget#settingsTabs::pane { background: rgba(6,17,30,.72); border: 1px solid rgba(83,145,213,.22); border-radius: 14px; top: -1px; }
QWidget#settingsPage { background: transparent; }
QTabBar::tab { color: #7990AC; background: rgba(8,20,34,.82); border: 1px solid rgba(75,128,188,.20); border-bottom: 0; padding: 11px 20px; min-width: 110px; }
QTabBar::tab:first { border-top-left-radius: 10px; }
QTabBar::tab:last { border-top-right-radius: 10px; }
QTabBar::tab:selected { color: #F2F8FF; background: rgba(25,64,105,.92); border-color: rgba(80,162,246,.46); }
QTabBar::tab:hover:!selected { color: #C9DDF4; background: rgba(18,43,72,.88); }
QProgressBar { background: rgba(13,30,50,.86); border: 0; border-radius: 5px; height: 8px; color: transparent; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2B8CFF,stop:1 #52E2D1); border-radius: 5px; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { width: 8px; background: #07111D; }
QScrollBar::handle:vertical { background: #244564; border-radius: 4px; min-height: 32px; }
QDialog { background: #07111E; color: #EAF2FC; }
QFrame[problemCard="true"] { background: rgba(10,24,41,.94); border: 1px solid rgba(79,137,204,.23); border-radius: 15px; }
QFrame[problemCard="true"][severity="FAIL"] { border-left: 4px solid #FF6075; }
QFrame[problemCard="true"][severity="WARNING"] { border-left: 4px solid #F2B45F; }
QFrame[problemCard="true"][severity="UNKNOWN"] { border-left: 4px solid #8798AE; }
QLabel[heading="true"] { font-size: 21px; font-weight: 800; color: #F1F7FF; }
QLabel[subheading="true"] { font-size: 15px; font-weight: 750; color: #E9F2FE; }
QLabel[muted="true"] { color: #7E93AF; }
QLabel[impact="true"] { color: #F0BF78; background: rgba(92,62,19,.20); border-radius: 8px; padding: 8px; }
QCheckBox { color: #C8D7E9; spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #315B84; border-radius: 4px; background: #07111F; }
QCheckBox::indicator:checked { background: #3B9FFF; border-color: #70BEFF; }
QTableWidget { background: rgba(5,15,27,.78); alternate-background-color: rgba(10,26,45,.78); color: #DCE8F7; border: 1px solid rgba(79,137,204,.22); border-radius: 12px; gridline-color: transparent; }
QHeaderView::section { background: #10243B; color: #8299B6; border: 0; padding: 10px; font-weight: 700; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid rgba(71,121,180,.12); }
QTableWidget::item:selected { background: #1E5A91; }
"""

LIGHT_OVERRIDE = r"""
QWidget#windowChrome { background: #EAF1F8; border-color: #AFC3D7; }
QFrame#titleBar, QFrame#sidebar { background: #F7FAFD; border-color: #C8D6E4; }
QFrame[card="true"], QFrame[metricCard="true"], QFrame[moduleTile="true"], QFrame[modeCard="true"], QFrame[problemCard="true"] { background: #FFFFFF; border-color: #C5D5E4; }
QTextEdit#terminal, QComboBox, QLineEdit, QTextEdit, QSpinBox { background: #F7FAFD; color: #183047; border-color: #B9CBDB; }
QComboBox QAbstractItemView, QDialog { background: #FFFFFF; color: #183047; }
QTabWidget#settingsTabs::pane, QTabBar::tab { background: #F7FAFD; color: #526C83; border-color: #C1D2E1; }
QTabBar::tab:selected { background: #DCEBFA; color: #173550; }
QTableWidget { background: #FFFFFF; alternate-background-color: #F5F8FB; color: #1E3449; border-color: #C2D2E1; }
QHeaderView::section { background: #E5EEF6; color: #526C83; }
QPushButton { color: #23415D; background: #E7F0F8; border-color: #B7CADB; }
QLabel#modeTitle, QLabel#pageTitle, QLabel[heading="true"], QLabel[subheading="true"], QLabel#metricValue, QLabel#windowTitle { color: #142A40; }
QCheckBox { color: #263E55; }
QScrollBar:vertical { background: #E7EEF5; } QScrollBar::handle:vertical { background: #A8BED1; }
"""


def apply_theme(theme_id: str = "obsidian", font_scale: str = "standard") -> str:
    selected = THEMES.get(theme_id, THEMES["obsidian"])
    defaults = THEMES["obsidian"]
    COLORS.clear(); COLORS.update({key: value for key, value in selected.items() if key != "name"})
    style = BASE_STYLESHEET
    for key in ("bg", "surface", "surface2", "line", "text", "muted", "blue", "cyan", "gold", "pass", "warning", "fail", "unknown"):
        style = style.replace(defaults[key], selected[key]).replace(defaults[key].lower(), selected[key])
    if theme_id == "daylight":
        style += LIGHT_OVERRIDE
    style += f"\n/* active-theme:{theme_id} */ QWidget#windowChrome {{ background-color: {selected['bg']}; }} QLabel#pageEyebrow {{ color: {selected['blue']}; }}"
    if font_scale == "large":
        style += "\n* { font-size: 14px; } QLabel#pageTitle { font-size: 29px; } QLabel#metricValue { font-size: 26px; }"
    return style


STYLESHEET = apply_theme()
