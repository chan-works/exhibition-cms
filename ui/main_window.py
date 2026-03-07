from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QSizePolicy,
    QMessageBox, QStatusBar
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from ui.styles import DARK_STYLE, SIDEBAR_BTN_STYLE
from ui.calendar_view import CalendarView
from ui.device_manager import DeviceManager
from ui.zone_manager import ZoneManager
from ui.user_manager import UserManager
from ui.notification_panel import NotificationPanel
from ui.recurring_schedule import RecurringSchedulePanel
from controllers.scheduler import ExhibitionScheduler


NAV_ITEMS = [
    ("calendar",   "📅  캘린더"),
    ("recurring",  "🔁  정기 스케줄"),
    ("devices",    "⚙  디바이스"),
    ("zones",      "🏛  구역 관리"),
    ("users",      "👤  사용자"),
    ("notif",      "🔔  알림"),
]


class MainWindow(QMainWindow):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = user
        self.setWindowTitle("Exhibition CMS - 전시장 통합 제어 시스템")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(DARK_STYLE)

        self._init_scheduler()
        self._build_ui()
        self._start_timers()
        self._nav_to("calendar")

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def _init_scheduler(self):
        self.scheduler = ExhibitionScheduler(
            self.db,
            notification_callback=self._on_scheduler_notify
        )

    def _on_scheduler_notify(self, title, message, ntype="info"):
        self.db.add_notification(ntype, title, message)
        # Update badge on next timer tick
        self._update_notif_badge()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = self._build_sidebar()
        root.addWidget(sidebar)

        # Main content
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Create pages
        self.calendar_page = CalendarView(self.db, self.current_user, self.scheduler)
        self.recurring_page = RecurringSchedulePanel(self.db, self.current_user, self.scheduler)
        self.device_page = DeviceManager(self.db, self.current_user, self.scheduler)
        self.zone_page = ZoneManager(self.db, self.current_user)
        self.notif_page = NotificationPanel(self.db)
        self.notif_page.unread_count_changed.connect(self._update_badge_label)

        if self.current_user["role"] == "admin":
            self.user_page = UserManager(self.db, self.current_user)
        else:
            self.user_page = self._access_denied_page()

        self.stack.addWidget(self.calendar_page)    # 0
        self.stack.addWidget(self.recurring_page)   # 1
        self.stack.addWidget(self.device_page)      # 2
        self.stack.addWidget(self.zone_page)        # 3
        self.stack.addWidget(self.user_page)        # 4
        self.stack.addWidget(self.notif_page)       # 5

        # Cross-wire signals
        self.zone_page.zones_changed.connect(self._on_zones_changed)
        self.device_page.devices_changed.connect(self._on_devices_changed)
        self.recurring_page.changed.connect(self.calendar_page.refresh)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_time_lbl = QLabel()
        self.status.addPermanentWidget(self.status_time_lbl)
        user_lbl = QLabel(f"  사용자: {user_display(self.current_user)}  ")
        self.status.addWidget(user_lbl)

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("""
            QFrame#sidebar {
                background-color: #16213e;
                border-right: 2px solid #0f3460;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        # App name
        app_lbl = QLabel("Exhibition\nCMS")
        app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_lbl.setStyleSheet("""
            color: #e94560;
            font-size: 16px;
            font-weight: bold;
            padding: 8px 0 16px 0;
            border-bottom: 1px solid #0f3460;
        """)
        layout.addWidget(app_lbl)
        layout.addSpacing(8)

        # Nav buttons
        self.nav_buttons = {}
        page_keys = ["calendar", "devices", "zones", "users", "notif"]
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(44)
            btn.setStyleSheet(SIDEBAR_BTN_STYLE)
            btn.clicked.connect(lambda checked, k=key: self._nav_to(k))
            self.nav_buttons[key] = btn
            layout.addWidget(btn)

        # Notification badge button
        self.badge_label = QPushButton("")
        self.badge_label.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #e94560;
                border: none;
                border-radius: 8px;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #ff5577;
            }
        """)
        self.badge_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge_label.setFixedHeight(28)
        self.badge_label.clicked.connect(lambda: self._nav_to("notif"))
        self.badge_label.hide()

        layout.addStretch()
        layout.addWidget(self.badge_label)

        # Logout
        logout_btn = QPushButton("⏻  로그아웃")
        logout_btn.setFixedHeight(40)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #808090;
                border: 1px solid #303050;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #8b2222;
                color: white;
                border-color: #8b2222;
            }
        """)
        logout_btn.clicked.connect(self._logout)
        layout.addWidget(logout_btn)

        return sidebar

    def _access_denied_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        lbl = QLabel("접근 권한이 없습니다\n(관리자 전용)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #808090; font-size: 16px;")
        layout.addWidget(lbl)
        return page

    # ── Navigation ────────────────────────────────────────────────────────────

    def _nav_to(self, key):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        page_map = {
            "calendar":  0,
            "recurring": 1,
            "devices":   2,
            "zones":     3,
            "users":     4,
            "notif":     5,
        }
        self.stack.setCurrentIndex(page_map.get(key, 0))

        if key == "notif":
            self.notif_page.refresh()
            self._update_badge_label(self.db.get_unread_count())
        if key == "recurring":
            self.recurring_page.refresh()

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_zones_changed(self):
        self.calendar_page.refresh()
        self.device_page.refresh()

    def _on_devices_changed(self):
        pass  # scheduler auto-reloads on demand

    def _update_notif_badge(self):
        count = self.db.get_unread_count()
        self._update_badge_label(count)

    def _update_badge_label(self, count):
        if count > 0:
            self.badge_label.setText(f"  알림 {count}개 미확인  ")
            self.badge_label.show()
        else:
            self.badge_label.hide()

    # ── Timers ────────────────────────────────────────────────────────────────

    def _start_timers(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._badge_timer = QTimer(self)
        self._badge_timer.timeout.connect(self._update_notif_badge)
        self._badge_timer.start(30000)  # every 30 seconds
        self._update_notif_badge()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status_time_lbl.setText(f"  {now}  ")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _logout(self):
        reply = QMessageBox.question(
            self, "로그아웃", "로그아웃 하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.scheduler.stop()
            self.close()
            # Re-launch login
            from ui.login_dialog import LoginDialog
            login = LoginDialog(self.db)
            if login.exec() == LoginDialog.DialogCode.Accepted:
                user = login.get_user()
                new_win = MainWindow(self.db, user)
                new_win.show()
                self._replacement = new_win

    def closeEvent(self, event):
        self.scheduler.stop()
        super().closeEvent(event)


def user_display(user):
    name = user.get("full_name") or user.get("username", "")
    role_map = {"admin": "관리자", "operator": "운영자", "viewer": "열람자"}
    role = role_map.get(user.get("role", ""), user.get("role", ""))
    return f"{name} ({role})"
