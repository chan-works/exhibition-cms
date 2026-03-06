DARK_STYLE = """
QMainWindow, QDialog, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

QPushButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1a4a80;
}
QPushButton:pressed {
    background-color: #0a2040;
}
QPushButton#primary {
    background-color: #e94560;
}
QPushButton#primary:hover {
    background-color: #ff5577;
}
QPushButton#danger {
    background-color: #8b2222;
}
QPushButton#danger:hover {
    background-color: #aa2222;
}
QPushButton#success {
    background-color: #1a6b3c;
}
QPushButton#success:hover {
    background-color: #1f8048;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QTimeEdit, QComboBox {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 6px 10px;
    selection-background-color: #e94560;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QTimeEdit:focus {
    border: 1px solid #e94560;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    selection-background-color: #0f3460;
}

QTableWidget {
    background-color: #16213e;
    color: #e0e0e0;
    gridline-color: #0f3460;
    border: 1px solid #0f3460;
    border-radius: 4px;
    alternate-background-color: #1a2550;
}
QTableWidget::item:selected {
    background-color: #0f3460;
}
QTableWidget::item:hover {
    background-color: #1f3a60;
}
QHeaderView::section {
    background-color: #0f3460;
    color: #e0e0e0;
    padding: 8px;
    border: none;
    border-right: 1px solid #1a1a2e;
    font-weight: bold;
}

QScrollBar:vertical {
    background-color: #16213e;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #e94560;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #16213e;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background-color: #0f3460;
    border-radius: 4px;
    min-width: 20px;
}

QLabel {
    color: #e0e0e0;
}
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #e94560;
}
QLabel#subtitle {
    font-size: 14px;
    color: #a0b0c0;
}
QLabel#section {
    font-size: 15px;
    font-weight: bold;
    color: #c0d0e0;
}

QGroupBox {
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    color: #e94560;
    font-weight: bold;
}

QCheckBox {
    color: #e0e0e0;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #0f3460;
    border-radius: 3px;
    background-color: #16213e;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QCheckBox::indicator:hover {
    border-color: #e94560;
}

QTabWidget::pane {
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 4px;
}
QTabBar::tab {
    background-color: #16213e;
    color: #a0a0a0;
    padding: 8px 16px;
    margin-right: 2px;
    border-radius: 4px 4px 0 0;
}
QTabBar::tab:selected {
    background-color: #0f3460;
    color: #e0e0e0;
}
QTabBar::tab:hover {
    background-color: #1f3a60;
    color: #e0e0e0;
}

QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 3px;
}
QMenu::item:selected {
    background-color: #0f3460;
}

QMessageBox {
    background-color: #1a1a2e;
    color: #e0e0e0;
}

QStatusBar {
    background-color: #0f3460;
    color: #e0e0e0;
    font-size: 12px;
}

QSplitter::handle {
    background-color: #0f3460;
}

QFrame#sidebar {
    background-color: #16213e;
    border-right: 2px solid #0f3460;
}

QFrame#card {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    padding: 8px;
}

QListWidget {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
}
QListWidget::item {
    padding: 6px;
    border-radius: 3px;
}
QListWidget::item:selected {
    background-color: #0f3460;
}
QListWidget::item:hover {
    background-color: #1f3a60;
}

QProgressBar {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #e94560;
    border-radius: 3px;
}

QToolTip {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #e94560;
    border-radius: 4px;
    padding: 4px;
}

QCalendarWidget QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    selection-background-color: #e94560;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #0f3460;
}
QCalendarWidget QToolButton {
    color: #e0e0e0;
    background-color: transparent;
    border: none;
    padding: 4px 8px;
}
QCalendarWidget QToolButton:hover {
    background-color: #e94560;
    border-radius: 4px;
}
QCalendarWidget QMenu {
    background-color: #16213e;
    color: #e0e0e0;
}
QCalendarWidget QSpinBox {
    background-color: #16213e;
    color: #e0e0e0;
    border: none;
}
"""

SIDEBAR_BTN_STYLE = """
QPushButton {
    background-color: transparent;
    color: #a0b0c0;
    border: none;
    border-radius: 6px;
    padding: 12px 16px;
    text-align: left;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #0f3460;
    color: #e0e0e0;
}
QPushButton:checked {
    background-color: #e94560;
    color: #ffffff;
    font-weight: bold;
}
"""
