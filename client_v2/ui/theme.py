from __future__ import annotations

# THEMES and COLORS are defined as before.
THEMES = {
    "obsidian": {
        "name": "黑曜石旗舰",
        "bg": "#01060f",        # 更深的背景色
        "surface": "#050d18",   # 面板背景色，对应web的panel
        "surface2": "#0D1A2B",  # 保持原有的深色表面变体
        "line": "#102a49",      # 边框线色
        "text": "#e0e8f3",      # 主要文字颜色
        "muted": "#6e849e",     # 次要文字颜色
        "blue": "#3d8bff",      # 蓝色调
        "cyan": "#40d0e6",      # 青色调
        "gold": "#f2c77d",      # 金色调
        "pass": "#48d18b",      # 成功色，对应web的green
        "warning": "#F2B45F",   # 保持原有的警告色
        "fail": "#FF6075",      # 保持原有的失败色
        "unknown": "#8798AE",   # 保持原有的未知色
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
    "bg": "#01060f", "surface": "#050d18", "surface2": "#0D1A2B", "line": "#102a49",
    "text": "#e0e8f3", "muted": "#6e849e", "blue": "#3d8bff", "cyan": "#40d0e6",
    "gold": "#f2c77d", "pass": "#48d18b", "warning": "#F2B45F", "fail": "#FF6075", "unknown": "#8798AE",
}

# Helper function to convert hex to RGB for use in QSS rgba
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return ','.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

BASE_STYLESHEET = r"""
/* Global Styles */
* {
    font-family: "Noto Sans SC", "Microsoft YaHei UI";
    font-size: 13px;
    color: ${text};
    outline: none;
}

QMainWindow {
    background: transparent;
}

QWidget#windowChrome {
    background: ${bg};
    border: 1px solid ${line};
    border-radius: 18px;
}

QFrame#titleBar {
    min-height: 46px;
    max-height: 46px;
    background: ${surface};
    border-bottom: 1px solid ${line};
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
}

QLabel#brandMark {
    color: ${blue};
    font-size: 20px;
    font-weight: 900;
    padding: 0 2px;
}

QLabel#windowTitle {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: ${text};
}

QLabel#versionPill {
    color: ${muted};
    background: transparent;
    border: 0;
    padding: 0 4px;
    font-size: 10px;
    letter-spacing: 0.8px;
}

QPushButton#windowControl {
    min-width: 36px;
    max-width: 36px;
    min-height: 30px;
    border: 0;
    background: transparent;
    color: ${muted};
    font-size: 16px;
    padding: 0;
}

QPushButton#windowControl:hover {
    color: ${text};
    background: rgba(${blue_rgb}, 0.16);
    border-radius: 6px;
}

QFrame#sidebar {
    background: ${surface};
    border-right: 1px solid ${line};
}

QLabel#sideBrand {
    color: ${text};
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 2px;
    padding: 22px 0 26px;
}

QPushButton[nav="true"] {
    min-height: 48px;
    text-align: left;
    padding: 8px 16px;
    border: 1px solid transparent;
    border-radius: 12px;
    background: transparent;
    color: ${muted};
    font-weight: 600;
}

QPushButton[nav="true"]:hover {
    color: ${text};
    background: rgba(${blue_rgb}, 0.12);
    border-color: rgba(${blue_rgb}, 0.3);
}

QPushButton[nav="true"]:checked {
    color: ${text};
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(${blue_rgb}, 0.3),stop:1 rgba(${surface_rgb}, 0.2));
    border-color: ${blue};
}

QLabel#pageEyebrow {
    color: ${blue};
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
}

QLabel#pageTitle {
    color: ${text};
    font-size: 27px;
    font-weight: 800;
}

QLabel#pageSubtitle {
    color: ${muted};
    font-size: 13px;
}

QFrame[card="true"], QFrame[metricCard="true"], QFrame[moduleTile="true"] {
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 15px;
}
QFrame[card="true"]:hover, QFrame[metricCard="true"]:hover, QFrame[moduleTile="true"]:hover {
}

QFrame[modeCard="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(${surface_rgb}, 0.96),stop:.65 rgba(${bg_rgb}, 0.96),stop:1 rgba(${bg_rgb}, 0.98));
    border: 1px solid rgba(${blue_rgb}, 0.28);
    border-radius: 20px;
}
QFrame[modeCard="true"]:hover {
    border: 1px solid rgba(${blue_rgb}, 0.70);
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(${surface_rgb}, 0.98),stop:.65 rgba(${bg_rgb}, 0.98),stop:1 rgba(${bg_rgb}, 0.98));
}

QLabel#modeIcon {
    font-size: 32px;
    font-weight: 900;
    color: ${blue};
}

QLabel#eyebrow {
    border: 1px solid ${line};
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 10px;
    font-weight: 800;
    color: ${cyan};
}

QLabel#modeTitle {
    color: ${text};
    font-size: 22px;
    font-weight: 800;
    padding-top: 5px;
}

QLabel#modeDescription {
    color: ${muted};
    font-size: 13px;
    line-height: 1.6;
}

QPushButton#modeButton {
    min-height: 46px;
    border: 0;
    border-radius: 11px;
    color: ${bg};
    font-size: 14px;
    font-weight: 900;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${blue},stop:1 ${cyan});
}
QPushButton#modeButton:hover {
}

QLabel#metricLabel {
    color: ${muted};
    font-size: 11px;
}

QLabel#metricValue {
    color: ${text};
    font-size: 24px;
    font-weight: 800;
}

QLabel#metricUnit {
    color: ${muted};
    padding-top: 8px;
}

QFrame[moduleTile="true"] {
    min-height: 46px;
}

QFrame[moduleTile="true"][state="running"] {
    background: rgba(${blue_rgb}, 0.15);
    border-color: ${blue};
}

QFrame[moduleTile="true"][state="success"] {
    border-color: ${pass};
    background: rgba(${pass_rgb}, 0.15);
}

QFrame[moduleTile="true"][state="warning"] {
    border-color: ${warning};
    background: rgba(${warning_rgb}, 0.15);
}

QFrame[moduleTile="true"][state="fail"] {
    border-color: ${fail};
    background: rgba(${fail_rgb}, 0.15);
}

QLabel#moduleGlyph {
    color: ${blue};
    font-size: 11px;
    font-weight: 900;
    min-width: 34px;
}

QLabel#moduleState {
    color: ${muted};
    font-size: 11px;
}

QTextEdit#terminal {
    background: rgba(${bg_rgb}, 0.84);
    border: 1px solid rgba(${line_rgb}, 0.24);
    border-radius: 13px;
    padding: 13px;
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 12px;
    color: ${text};
}

QPushButton {
    color: ${text};
    background: rgba(${surface_rgb}, 0.85);
    border: 1px solid rgba(${line_rgb}, 0.3);
    border-radius: 10px;
    padding: 9px 14px;
    font-weight: 600;
}

QPushButton:hover {
    color: white;
    background: rgba(${surface_rgb}, 0.95);
    border-color: rgba(${blue_rgb}, 0.62);
}

QPushButton:disabled {
    color: rgba(${muted_rgb}, 0.6);
    background: rgba(${surface_rgb}, 0.65);
    border-color: rgba(${line_rgb}, 0.18);
}

QPushButton[primary="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${blue},stop:1 ${cyan});
    border: 0;
    color: ${bg};
    font-weight: 900;
}
QPushButton[primary="true"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${blue},stop:1 ${cyan});
}

QPushButton[gold="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${gold},stop:1 rgba(244, 202, 113, 1));
    border: 0;
    color: #171005;
    font-weight: 900;
}
QPushButton[gold="true"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${gold},stop:1 rgba(244, 202, 113, 1));
}

QPushButton[danger="true"] {
    background: rgba(${fail_rgb}, 0.2);
    border-color: rgba(${fail_rgb}, 0.55);
    color: ${fail};
}
QPushButton[danger="true"]:hover {
    background: rgba(${fail_rgb}, 0.3);
}

QComboBox, QLineEdit, QTextEdit, QSpinBox {
    background: rgba(${surface_rgb}, 0.88);
    color: ${text};
    border: 1px solid ${line};
    border-radius: 10px;
    padding: 9px 12px;
    selection-background-color: ${blue};
}

QComboBox:focus, QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {
    border-color: ${blue};
}

QComboBox::drop-down {
    border: 0;
    width: 30px;
}

QComboBox QAbstractItemView {
    background: ${surface2};
    border: 1px solid ${line};
    selection-background-color: rgba(${blue_rgb}, 0.4);
}

QTabWidget#settingsTabs {
    background: transparent;
}

QTabWidget#settingsTabs::pane {
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 14px;
    top: -1px;
}

QWidget#settingsPage {
    background: transparent;
}

QTabBar::tab {
    color: ${muted};
    background: rgba(${surface_rgb}, 0.82);
    border: 1px solid rgba(${line_rgb}, 0.2);
    border-bottom: 0;
    padding: 11px 20px;
    min-width: 110px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}

QTabBar::tab:first {
    border-top-left-radius: 10px;
}

QTabBar::tab:last {
    border-top-right-radius: 10px;
}

QTabBar::tab:selected {
    color: ${text};
    background: ${surface2};
    border-color: rgba(${blue_rgb}, 0.46);
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    color: ${text};
    background: rgba(${surface_rgb}, 0.88);
}

QProgressBar {
    background: rgba(${surface_rgb}, 0.86);
    border: 0;
    border-radius: 5px;
    height: 8px;
    color: transparent;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 ${blue},stop:1 ${cyan});
    border-radius: 5px;
}

QScrollArea {
    background: transparent;
    border: 0;
}

QScrollBar:vertical {
    width: 8px;
    background: ${bg};
}

QScrollBar::handle:vertical {
    background: rgba(${line_rgb}, 0.6);
    border-radius: 4px;
    min-height: 32px;
}

QDialog {
    background: ${surface};
    color: ${text};
    border-radius: 18px;
}

QFrame[problemCard="true"] {
    background: rgba(${surface_rgb}, 0.94);
    border: 1px solid rgba(${line_rgb}, 0.23);
    border-radius: 15px;
}

QFrame[problemCard="true"][severity="FAIL"] {
    border-left: 4px solid ${fail};
}

QFrame[problemCard="true"][severity="WARNING"] {
    border-left: 4px solid ${warning};
}

QFrame[problemCard="true"][severity="UNKNOWN"] {
    border-left: 4px solid ${unknown};
}

QLabel[heading="true"] {
    font-size: 21px;
    font-weight: 800;
    color: ${text};
}

QLabel[subheading="true"] {
    font-size: 15px;
    font-weight: 750;
    color: ${text};
}

QLabel[muted="true"] {
    color: ${muted};
}

QLabel[caption="true"] {
    color: ${muted};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding-top: 2px;
}

QLabel[impact="true"] {
    color: ${gold};
    background: rgba(${gold_rgb}, 0.1);
    border-radius: 8px;
    padding: 8px;
}

QFrame[card="true"][hero="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(${surface2_rgb}, 0.96),stop:1 rgba(${surface_rgb}, 0.98));
    border: 1px solid rgba(${blue_rgb}, 0.35);
    border-radius: 18px;
}

QLabel#profileHero {
    color: ${text};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.4px;
}

QPushButton[link="true"] {
    background: transparent;
    border: 0;
    color: ${blue};
    font-weight: 700;
    padding: 4px 6px;
    text-align: right;
}

QPushButton[link="true"]:hover {
    color: ${cyan};
    background: transparent;
    border: 0;
}

QCheckBox {
    color: ${text};
    spacing: 8px;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid ${line};
    border-radius: 4px;
    background: ${bg};
}

QCheckBox::indicator:checked {
    background: ${blue};
    border-color: ${blue};
}

QTableWidget {
    background: rgba(${surface_rgb}, 0.68);
    alternate-background-color: rgba(${surface2_rgb}, 0.6);
    color: ${text};
    border: 1px solid ${line};
    border-radius: 14px;
    gridline-color: transparent;
    selection-background-color: rgba(${blue_rgb}, 0.28);
}

QTableWidget QTableCornerButton::section {
    background: rgba(${surface2_rgb}, 0.9);
    border: 0;
    border-top-left-radius: 14px;
}

QHeaderView {
    background: transparent;
    border: 0;
}

QHeaderView::section {
    background: rgba(${surface2_rgb}, 0.9);
    color: ${muted};
    border: 0;
    padding: 10px;
    font-weight: 700;
}

QHeaderView::section:vertical {
    background: rgba(${surface2_rgb}, 0.9);
    color: ${muted};
    padding: 4px 8px;
}

QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid rgba(${line_rgb}, 0.12);
}

QTableWidget::item:selected {
    background: rgba(${blue_rgb}, 0.3);
}

QScrollBar:horizontal {
    height: 8px;
    background: transparent;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: rgba(${line_rgb}, 0.6);
    border-radius: 4px;
    min-width: 32px;
}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: 0;
    width: 0;
    height: 0;
}
"""

LIGHT_OVERRIDE = r"""
QWidget#windowChrome { background: #EAF1F8; border-color: #AFC3D7; }
QFrame#titleBar, QFrame#sidebar { background: #F7FAFD; border-color: #C8D6E4; }
QFrame[card="true"], QFrame[metricCard="true"], QFrame[moduleTile="true"], QFrame[modeCard="true"], QFrame[problemCard="true"] { background: #FFFFFF; border-color: #C5D5E4; }
QTextEdit#terminal, QComboBox, QLineEdit, QTextEdit, QSpinBox { background: #F7FAFD; color: #183047; border-color: #B9CBDB; }
QComboBox QAbstractItemView, QDialog { background: #FFFFFF; color: #183047; }
QTabWidget#settingsTabs::pane, QTabBar::tab { background: #F7FAFD; color: #526C83; border-color: #C1D2E1; }
QTabBar::tab:selected { background: #DCEBFA; color: #173550; }
QTabBar::tab:hover:!selected { color: #C9DDF4; background: rgba(18,43,72,.88); } /* Needs to be updated to new color system */
QTableWidget { background: #FFFFFF; alternate-background-color: #F5F8FB; color: #1E3449; border-color: #C2D2E1; }
QHeaderView::section { background: #E5EEF6; color: #526C83; }
QPushButton { color: #23415D; background: #E7F0F8; border-color: #B7CADB; }
QLabel#modeTitle, QLabel#pageTitle, QLabel[heading="true"], QLabel[subheading="true"], QLabel#metricValue, QLabel#windowTitle { color: #142A40; }
QCheckBox { color: #263E55; }
QScrollBar:vertical { background: #E7EEF5; } QScrollBar::handle:vertical { background: #A8BED1; }
"""


def apply_theme(theme_id: str = "obsidian", font_scale: str = "standard") -> str:
    selected = THEMES.get(theme_id, THEMES["obsidian"])

    # Define a helper to convert hex to rgb string for QSS
    def get_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return ','.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

    replacements = {
        "${bg}": selected["bg"],
        "${surface}": selected["surface"],
        "${surface2}": selected["surface2"],
        "${line}": selected["line"],
        "${text}": selected["text"],
        "${muted}": selected["muted"],
        "${blue}": selected["blue"],
        "${cyan}": selected["cyan"],
        "${gold}": selected["gold"],
        "${pass}": selected["pass"],
        "${warning}": selected["warning"],
        "${fail}": selected["fail"],
        "${unknown}": selected["unknown"],

        # RGBA dynamic replacements
        "${cyan_rgb}": get_rgb(selected["cyan"]),
        "${blue_rgb}": get_rgb(selected["blue"]),
        "${surface_rgb}": get_rgb(selected["surface"]),
        "${bg_rgb}": get_rgb(selected["bg"]),
        "${line_rgb}": get_rgb(selected["line"]),
        "${gold_rgb}": get_rgb(selected["gold"]),
        "${pass_rgb}": get_rgb(selected["pass"]),
        "${warning_rgb}": get_rgb(selected["warning"]),
        "${fail_rgb}": get_rgb(selected["fail"]),
        "${muted_rgb}": get_rgb(selected["muted"]),
        "${surface2_rgb}": get_rgb(selected["surface2"]),
        "${unknown_rgb}": get_rgb(selected["unknown"]),

    }

    style = BASE_STYLESHEET
    for placeholder, value in replacements.items():
        style = style.replace(placeholder, value)

    if theme_id == "daylight":
        # Need to re-evaluate LIGHT_OVERRIDE with new color system
        style += LIGHT_OVERRIDE
    style += f"\n/* active-theme:{theme_id} */ QWidget#windowChrome {{ background-color: {selected['bg']}; }} QLabel#pageEyebrow {{ color: {selected['blue']}; }}"
    if font_scale == "large":
        style += "\n* { font-size: 14px; } QLabel#pageTitle { font-size: 29px; } QLabel#metricValue { font-size: 26px; }"
    return style

STYLESHEET = apply_theme()
