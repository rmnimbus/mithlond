"""Dark theme with a gold accent."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

GOLD = "#c9a45c"

STYLE = f"""
QMainWindow, QWidget {{ font-size: 10.5pt; }}
QTabWidget::pane {{ border: 1px solid #3a352c; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ padding: 8px 16px; border: 1px solid transparent; border-bottom: none;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: #b8b0a0; }}
QTabBar::tab:selected {{ background: #2a2620; color: {GOLD}; border-color: #3a352c; }}
QTabBar::tab:hover {{ color: #e8dcc0; }}
QPushButton {{ padding: 6px 14px; border: 1px solid #4a4336; border-radius: 5px; background: #2d2922; }}
QPushButton:hover {{ border-color: {GOLD}; }}
QPushButton:disabled {{ color: #6b6558; border-color: #35312a; }}
QPushButton#play {{ font-size: 16pt; font-weight: 600; padding: 12px 40px; color: #1b1814;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e0bd72, stop:1 #b08a45);
                    border: 1px solid #f0d090; }}
QPushButton#play:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ecca80, stop:1 #c09a55); }}
QPushButton#play:disabled {{ background: #4a4336; color: #8a8270; border-color: #4a4336; }}
QPushButton#stop {{ font-size: 16pt; font-weight: 600; padding: 12px 22px; color: #f2d0c8;
                    background: #5a2a22; border: 1px solid #8a4436; }}
QPushButton#stop:hover {{ background: #6e3328; border-color: #c06050; }}
QPushButton#stop:disabled {{ background: #3a2a26; color: #8a7a74; border-color: #4a3a36; }}
QLabel#banner {{ font-size: 26pt; font-weight: 300; color: {GOLD}; letter-spacing: 4px; }}
QLabel#subtle, QLabel[subtle="true"] {{ color: #9a9282; }}
QLabel#ok {{ color: #8fc77f; }}
QLabel#bad {{ color: #e07a6a; }}
QGroupBox {{ border: 1px solid #3a352c; border-radius: 6px; margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {GOLD}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser, QTreeWidget, QTableWidget {{
    border: 1px solid #3f392f; border-radius: 4px; padding: 3px; background: #1f1c18; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {GOLD}; }}
QHeaderView::section {{ background: #2a2620; padding: 4px; border: none; border-right: 1px solid #3a352c; }}
QProgressBar {{ border: 1px solid #3f392f; border-radius: 4px; text-align: center; background: #1f1c18; }}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 3px; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    bg, base, text = QColor("#24211c"), QColor("#1b1915"), QColor("#e6dfd0")
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, QColor("#25221d"))
    p.setColor(QPalette.ToolTipBase, QColor("#2d2922"))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, QColor("#2d2922"))
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.Highlight, QColor("#8a6d36"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.Link, QColor(GOLD))
    p.setColor(QPalette.PlaceholderText, QColor("#7a7364"))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, QColor("#6b6558"))
    app.setPalette(p)
    app.setStyleSheet(STYLE)
