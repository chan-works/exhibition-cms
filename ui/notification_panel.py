from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


TYPE_COLORS = {
    "info":    "#2196F3",
    "success": "#4CAF50",
    "warning": "#FF9800",
    "error":   "#F44336",
}
TYPE_ICONS = {
    "info":    "ℹ",
    "success": "✓",
    "warning": "⚠",
    "error":   "✗",
}


class NotificationItem(QFrame):
    def __init__(self, notif: dict, parent=None):
        super().__init__(parent)
        self.notif = notif
        ntype = notif.get("notification_type", "info")
        color = TYPE_COLORS.get(ntype, "#2196F3")
        icon = TYPE_ICONS.get(ntype, "ℹ")

        bg = "rgba(255,255,255,0.03)" if notif.get("is_read") else "rgba(14,52,96,0.4)"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-left: 3px solid {color};
                border-radius: 4px;
                margin-bottom: 4px;
                padding: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        icon_lbl.setFixedWidth(24)
        layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_lbl = QLabel(notif.get("title", ""))
        title_lbl.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        title_lbl.setWordWrap(True)
        text_layout.addWidget(title_lbl)

        if notif.get("message"):
            msg_lbl = QLabel(notif["message"])
            msg_lbl.setStyleSheet("color: #a0b0c0; font-size: 12px;")
            msg_lbl.setWordWrap(True)
            text_layout.addWidget(msg_lbl)

        time_lbl = QLabel(notif.get("created_at", "")[:16])
        time_lbl.setStyleSheet("color: #606070; font-size: 11px;")
        text_layout.addWidget(time_lbl)

        layout.addLayout(text_layout, 1)


class NotificationPanel(QWidget):
    unread_count_changed = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("알림")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()

        mark_all_btn = QPushButton("모두 읽음")
        mark_all_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0b0c0;
                border: 1px solid #0f3460;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover { color: #e0e0e0; border-color: #e94560; }
        """)
        mark_all_btn.clicked.connect(self._mark_all_read)
        header.addWidget(mark_all_btn)

        clear_btn = QPushButton("30일 이상 삭제")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0b0c0;
                border: 1px solid #0f3460;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover { color: #e0e0e0; border-color: #e94560; }
        """)
        clear_btn.clicked.connect(self._clear_old)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_widget)
        layout.addWidget(scroll)

    def refresh(self):
        # Clear existing items (keep stretch at end)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        notifications = self.db.get_notifications(100)
        for notif in notifications:
            item_widget = NotificationItem(notif)
            self.list_layout.insertWidget(self.list_layout.count() - 1, item_widget)

        if not notifications:
            empty_lbl = QLabel("알림이 없습니다")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #606070; font-size: 14px; padding: 40px;")
            self.list_layout.insertWidget(0, empty_lbl)

        count = self.db.get_unread_count()
        self.unread_count_changed.emit(count)

    def _mark_all_read(self):
        self.db.mark_all_notifications_read()
        self.refresh()

    def _clear_old(self):
        self.db.clear_old_notifications(30)
        self.refresh()
