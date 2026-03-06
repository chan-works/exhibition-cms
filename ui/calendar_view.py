import calendar
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QScrollArea, QFrame, QComboBox, QSizePolicy,
    QToolButton, QDialog
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush

from ui.schedule_editor import ScheduleEditorDialog


WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


class DayCell(QFrame):
    """A single day cell in the calendar grid."""
    clicked = Signal(int, int, int)  # year, month, day

    def __init__(self, year, month, day, schedules=None, is_today=False, is_other_month=False, parent=None):
        super().__init__(parent)
        self.year = year
        self.month = month
        self.day = day
        self.schedules = schedules or []
        self.is_today = is_today
        self.is_other_month = is_other_month
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Day number
        day_lbl = QLabel(str(self.day))
        font = QFont()
        font.setBold(self.is_today)
        font.setPointSize(12 if self.is_today else 11)
        day_lbl.setFont(font)

        if self.is_other_month:
            day_color = "#404050"
        elif self.is_today:
            day_color = "#e94560"
        else:
            day_color = "#e0e0e0"

        day_lbl.setStyleSheet(f"color: {day_color};")
        layout.addWidget(day_lbl)

        # Schedule indicators
        for sched in self.schedules[:4]:  # max 4 visible
            indicator = self._make_indicator(sched)
            layout.addWidget(indicator)

        if len(self.schedules) > 4:
            more = QLabel(f"  +{len(self.schedules)-4}개 더")
            more.setStyleSheet("color: #808090; font-size: 10px;")
            layout.addWidget(more)

        layout.addStretch()
        self._update_border()

    def _make_indicator(self, sched):
        label = QLabel()
        label.setFixedHeight(16)

        if sched.get("is_holiday"):
            text = f"  휴관: {sched.get('holiday_name','') or ''}"
            bg = "#8b2222"
        elif not sched.get("is_enabled"):
            text = f"  {sched.get('zone_name','')}: 비활성"
            bg = "#404050"
        else:
            on_t = sched.get("time_on") or "--:--"
            off_t = sched.get("time_off") or "--:--"
            text = f"  {sched.get('zone_name','')}: {on_t}~{off_t}"
            bg = sched.get("zone_color", "#2196F3")

        label.setText(text)
        label.setStyleSheet(f"""
            background-color: {bg};
            color: white;
            border-radius: 3px;
            padding: 0 4px;
            font-size: 10px;
        """)
        return label

    def _update_border(self):
        if self.is_today:
            border = "2px solid #e94560"
        else:
            border = "1px solid #0f3460"
        bg = "#1e2a45" if not self.is_other_month else "#16213e"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: {border};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background-color: #243060;
                border-color: #e94560;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.year, self.month, self.day)
        super().mousePressEvent(event)


class CalendarView(QWidget):
    def __init__(self, db, current_user, scheduler=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self.scheduler = scheduler
        today = date.today()
        self.current_year = today.year
        self.current_month = today.month
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Top bar
        top_bar = QHBoxLayout()

        title_lbl = QLabel("스케줄 캘린더")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        # Zone filter
        filter_lbl = QLabel("구역:")
        filter_lbl.setStyleSheet("color: #a0b0c0;")
        top_bar.addWidget(filter_lbl)
        self.zone_filter = QComboBox()
        self.zone_filter.addItem("전체 구역", None)
        for z in self.db.get_all_zones():
            self.zone_filter.addItem(z["name"], z["id"])
        self.zone_filter.currentIndexChanged.connect(self.refresh)
        top_bar.addWidget(self.zone_filter)

        # Today button
        today_btn = QPushButton("오늘")
        today_btn.setFixedHeight(32)
        today_btn.clicked.connect(self._go_today)
        top_bar.addWidget(today_btn)

        layout.addLayout(top_bar)

        # Month navigation
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.clicked.connect(self._prev_month)

        self.month_lbl = QLabel()
        self.month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0; min-width: 200px;")

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.clicked.connect(self._next_month)

        nav.addStretch()
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.month_lbl)
        nav.addWidget(self.next_btn)
        nav.addStretch()
        layout.addLayout(nav)

        # Weekday headers
        header_grid = QGridLayout()
        header_grid.setSpacing(4)
        for col, name in enumerate(WEEKDAY_NAMES):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color = "#e94560" if col >= 5 else "#a0b0c0"
            lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px; padding: 4px;")
            header_grid.addWidget(lbl, 0, col)
        layout.addLayout(header_grid)

        # Calendar grid (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(4)
        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll, 1)

        # Legend
        legend = QHBoxLayout()
        legend.addStretch()
        for text, color in [("활성 스케줄", "#2196F3"), ("공휴일/휴관", "#8b2222"),
                             ("비활성", "#404050"), ("오늘", "#e94560")]:
            dot = QLabel(f"■ {text}")
            dot.setStyleSheet(f"color: {color}; font-size: 11px; margin-right: 12px;")
            legend.addWidget(dot)
        layout.addLayout(legend)

    def refresh(self):
        self.month_lbl.setText(f"{self.current_year}년 {self.current_month}월")
        self._populate_grid()

    def _populate_grid(self):
        # Clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = date.today()
        selected_zone_id = self.zone_filter.currentData()

        # Get all schedules for this month
        schedules = self.db.get_schedules_for_month(self.current_year, self.current_month)
        sched_by_date = {}
        for s in schedules:
            d = s["schedule_date"]
            if selected_zone_id is None or s.get("zone_id") == selected_zone_id:
                sched_by_date.setdefault(d, []).append(s)

        # Build calendar
        cal = calendar.Calendar(firstweekday=0)  # Monday first
        month_days = cal.monthdatescalendar(self.current_year, self.current_month)

        for row, week in enumerate(month_days):
            for col, day_date in enumerate(week):
                date_str = day_date.isoformat()
                is_other = day_date.month != self.current_month
                is_today = day_date == today
                day_schedules = sched_by_date.get(date_str, [])

                cell = DayCell(
                    day_date.year, day_date.month, day_date.day,
                    schedules=day_schedules,
                    is_today=is_today,
                    is_other_month=is_other
                )
                cell.clicked.connect(self._on_day_clicked)
                self.grid_layout.addWidget(cell, row, col)

    def _on_day_clicked(self, year, month, day):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        zones = self.db.get_all_zones()
        if not zones:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "안내", "먼저 전시 구역을 추가하세요.")
            return

        selected_zone_id = self.zone_filter.currentData()
        if selected_zone_id:
            # Edit specific zone
            zone = next((z for z in zones if z["id"] == selected_zone_id), None)
            if zone:
                self._open_editor(zone, date_str)
        else:
            # Multiple zones: show zone picker if >1 zone
            if len(zones) == 1:
                self._open_editor(zones[0], date_str)
            else:
                self._show_zone_picker(zones, date_str)

    def _show_zone_picker(self, zones, date_str):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{date_str} - 구역 선택")
        dlg.setFixedSize(300, 60 + len(zones) * 44)
        dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        lbl = QLabel("편집할 구역을 선택하세요:")
        lbl.setStyleSheet("color: #a0b0c0; margin-bottom: 4px;")
        layout.addWidget(lbl)

        for zone in zones:
            btn = QPushButton(zone["name"])
            btn.setFixedHeight(36)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {zone.get('color','#2196F3')};
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 12px;
                }}
                QPushButton:hover {{ opacity: 0.9; }}
            """)
            btn.clicked.connect(lambda checked, z=zone, d=date_str: (dlg.accept(), self._open_editor(z, d)))
            layout.addWidget(btn)

        dlg.exec()

    def _open_editor(self, zone, date_str):
        dlg = ScheduleEditorDialog(self.db, zone, date_str, self.current_user, self)
        dlg.schedule_saved.connect(self._on_schedule_saved)
        dlg.exec()

    def _on_schedule_saved(self):
        if self.scheduler:
            self.scheduler.reload()
        self.refresh()

    def _prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.refresh()

    def _next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.refresh()

    def _go_today(self):
        today = date.today()
        self.current_year = today.year
        self.current_month = today.month
        self.refresh()
