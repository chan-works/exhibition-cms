from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QTimeEdit, QCheckBox, QComboBox, QScrollArea,
    QFrame, QGridLayout, QGroupBox, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTime, Signal

DAYS_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
DAYS_SHORT = ["월", "화", "수", "목", "금", "토", "일"]


class DayRow(QWidget):
    """Single row for one day of week."""

    def __init__(self, day_idx: int, data: dict = None, parent=None):
        super().__init__(parent)
        self.day_idx = day_idx
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        self.enabled_check = QCheckBox(DAYS_KO[day_idx])
        self.enabled_check.setFixedWidth(80)
        self.enabled_check.toggled.connect(self._on_toggle)
        layout.addWidget(self.enabled_check)

        on_lbl = QLabel("개관:")
        on_lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
        on_lbl.setFixedWidth(36)
        layout.addWidget(on_lbl)

        self.time_on = QTimeEdit()
        self.time_on.setDisplayFormat("HH:mm")
        self.time_on.setTime(QTime(9, 0))
        self.time_on.setFixedWidth(80)
        layout.addWidget(self.time_on)

        off_lbl = QLabel("폐관:")
        off_lbl.setStyleSheet("color: #F44336; font-weight: bold;")
        off_lbl.setFixedWidth(36)
        layout.addWidget(off_lbl)

        self.time_off = QTimeEdit()
        self.time_off.setDisplayFormat("HH:mm")
        self.time_off.setTime(QTime(18, 0))
        self.time_off.setFixedWidth(80)
        layout.addWidget(self.time_off)

        layout.addStretch()

        if data:
            self.enabled_check.setChecked(bool(data.get("is_enabled", 0)))
            if data.get("time_on"):
                h, m = map(int, data["time_on"].split(":"))
                self.time_on.setTime(QTime(h, m))
            if data.get("time_off"):
                h, m = map(int, data["time_off"].split(":"))
                self.time_off.setTime(QTime(h, m))
        else:
            self.enabled_check.setChecked(False)

        self._on_toggle(self.enabled_check.isChecked())

    def _on_toggle(self, checked):
        self.time_on.setEnabled(checked)
        self.time_off.setEnabled(checked)

    def get_data(self):
        return {
            "is_enabled": self.enabled_check.isChecked(),
            "time_on": self.time_on.time().toString("HH:mm") if self.enabled_check.isChecked() else None,
            "time_off": self.time_off.time().toString("HH:mm") if self.enabled_check.isChecked() else None,
        }

    def set_times(self, time_on_str, time_off_str, enabled=True):
        self.enabled_check.setChecked(enabled)
        if time_on_str:
            h, m = map(int, time_on_str.split(":"))
            self.time_on.setTime(QTime(h, m))
        if time_off_str:
            h, m = map(int, time_off_str.split(":"))
            self.time_off.setTime(QTime(h, m))


class RecurringScheduleDialog(QDialog):
    """Dialog to configure weekly recurring schedule for a zone."""

    saved = Signal()

    def __init__(self, db, zone, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.zone = zone
        self.current_user = current_user
        self.readonly = current_user["role"] == "viewer"
        self.setWindowTitle(f"{zone['name']} - 정기 스케줄 (요일별)")
        self.setMinimumSize(520, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header_lbl = QLabel(f"{self.zone['name']} - 정기 스케줄")
        header_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {self.zone.get('color', '#e94560')};"
        )
        layout.addWidget(header_lbl)

        hint = QLabel("특정 날짜 스케줄이 있으면 그것이 우선 적용됩니다.")
        hint.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(hint)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep)

        # Quick-set buttons
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(8)
        quick_lbl = QLabel("일괄 설정:")
        quick_lbl.setStyleSheet("color: #a0b0c0;")
        quick_layout.addWidget(quick_lbl)

        for label, days, style in [
            ("평일 (월~금)", list(range(5)), "background-color: #1a4a80;"),
            ("주말 (토~일)", [5, 6], "background-color: #6b2020;"),
            ("전체 (월~일)", list(range(7)), "background-color: #1a6b3c;"),
            ("전체 해제", list(range(7)), "background-color: #404050;"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setStyleSheet(f"""
                QPushButton {{
                    {style}
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 0 10px;
                    font-size: 12px;
                }}
                QPushButton:hover {{ opacity: 0.9; }}
            """)
            is_clear = label == "전체 해제"
            btn.clicked.connect(lambda checked, d=days, c=is_clear: self._quick_set(d, c))
            quick_layout.addWidget(btn)

        quick_layout.addStretch()
        layout.addLayout(quick_layout)

        # Time input for bulk set
        bulk_layout = QHBoxLayout()
        bulk_layout.setSpacing(8)
        bulk_lbl = QLabel("일괄 시간:")
        bulk_lbl.setStyleSheet("color: #a0b0c0;")
        bulk_layout.addWidget(bulk_lbl)

        on_lbl = QLabel("개관")
        on_lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
        bulk_layout.addWidget(on_lbl)
        self.bulk_time_on = QTimeEdit()
        self.bulk_time_on.setDisplayFormat("HH:mm")
        self.bulk_time_on.setTime(QTime(9, 0))
        self.bulk_time_on.setFixedWidth(80)
        bulk_layout.addWidget(self.bulk_time_on)

        off_lbl = QLabel("폐관")
        off_lbl.setStyleSheet("color: #F44336; font-weight: bold;")
        bulk_layout.addWidget(off_lbl)
        self.bulk_time_off = QTimeEdit()
        self.bulk_time_off.setDisplayFormat("HH:mm")
        self.bulk_time_off.setTime(QTime(18, 0))
        self.bulk_time_off.setFixedWidth(80)
        bulk_layout.addWidget(self.bulk_time_off)
        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep2)

        # Day rows
        self.day_rows = []
        for i in range(7):
            row = DayRow(i)
            # Weekend days get slightly different background
            if i >= 5:
                row.setStyleSheet("background-color: rgba(107,32,32,0.15); border-radius: 4px;")
            self.day_rows.append(row)
            layout.addWidget(row)

            if i == 4:  # Separator between weekday and weekend
                sep3 = QFrame()
                sep3.setFrameShape(QFrame.Shape.HLine)
                sep3.setStyleSheet("color: #0f3460;")
                layout.addWidget(sep3)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("닫기" if self.readonly else "취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        if not self.readonly:
            save_btn = QPushButton("저장")
            save_btn.setObjectName("primary")
            save_btn.clicked.connect(self._save)
            btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        if self.readonly:
            for row in self.day_rows:
                row.setEnabled(False)

    def _load(self):
        schedules = self.db.get_recurring_schedules(self.zone["id"])
        sched_by_day = {s["day_of_week"]: s for s in schedules}
        for i, row in enumerate(self.day_rows):
            if i in sched_by_day:
                data = sched_by_day[i]
                row.enabled_check.setChecked(bool(data.get("is_enabled", 0)))
                if data.get("time_on"):
                    h, m = map(int, data["time_on"].split(":"))
                    row.time_on.setTime(QTime(h, m))
                if data.get("time_off"):
                    h, m = map(int, data["time_off"].split(":"))
                    row.time_off.setTime(QTime(h, m))
                row._on_toggle(row.enabled_check.isChecked())

    def _quick_set(self, days: list, clear: bool = False):
        time_on = self.bulk_time_on.time().toString("HH:mm")
        time_off = self.bulk_time_off.time().toString("HH:mm")
        for i in days:
            row = self.day_rows[i]
            if clear:
                row.enabled_check.setChecked(False)
            else:
                row.set_times(time_on, time_off, enabled=True)

    def _save(self):
        for i, row in enumerate(self.day_rows):
            data = row.get_data()
            self.db.save_recurring_schedule(
                self.zone["id"], i,
                data["time_on"], data["time_off"],
                1 if data["is_enabled"] else 0
            )
        self.db.add_notification(
            "info",
            f"정기 스케줄 업데이트: {self.zone['name']}",
            "요일별 정기 스케줄이 저장됐습니다."
        )
        self.saved.emit()
        self.accept()


class RecurringSchedulePanel(QWidget):
    """Overview panel showing all zones' recurring schedules."""

    changed = Signal()

    def __init__(self, db, current_user, scheduler=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self.scheduler = scheduler
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("정기 스케줄 (요일별)")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        hint = QLabel("매주 반복되는 개관/폐관 시간을 요일별로 설정합니다. 특정 날짜 스케줄이 있으면 그것이 우선 적용됩니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a0b0c0; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSpacing(12)
        self.content_layout.addStretch()

        scroll.setWidget(self.content)
        layout.addWidget(scroll)

    def refresh(self):
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        zones = self.db.get_all_zones()
        if not zones:
            lbl = QLabel("구역을 먼저 추가하세요.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #606070; font-size: 14px; padding: 40px;")
            self.content_layout.insertWidget(0, lbl)
            return

        for zone in zones:
            card = self._make_zone_card(zone)
            self.content_layout.insertWidget(self.content_layout.count() - 1, card)

    def _make_zone_card(self, zone):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Zone header
        hdr = QHBoxLayout()
        zone_lbl = QLabel(zone["name"])
        zone_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {zone.get('color', '#e94560')};"
        )
        hdr.addWidget(zone_lbl)
        hdr.addStretch()

        if self.current_user["role"] in ("admin", "operator"):
            edit_btn = QPushButton("요일별 설정")
            edit_btn.setFixedHeight(28)
            edit_btn.setObjectName("primary")
            edit_btn.clicked.connect(lambda checked, z=zone: self._open_editor(z))
            hdr.addWidget(edit_btn)

        layout.addLayout(hdr)

        # Weekly grid
        grid = QGridLayout()
        grid.setSpacing(4)
        schedules = self.db.get_recurring_schedules(zone["id"])
        sched_by_day = {s["day_of_week"]: s for s in schedules}

        for col, (short, full) in enumerate(zip(DAYS_SHORT, DAYS_KO)):
            day_lbl = QLabel(short)
            day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color = "#e94560" if col >= 5 else "#a0b0c0"
            day_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
            grid.addWidget(day_lbl, 0, col)

            s = sched_by_day.get(col)
            if s and s.get("is_enabled"):
                on_t = s.get("time_on") or "--:--"
                off_t = s.get("time_off") or "--:--"
                cell_text = f"{on_t}\n{off_t}"
                cell_bg = zone.get("color", "#2196F3")
                cell_color = "white"
            else:
                cell_text = "휴관"
                cell_bg = "#2a2a3a"
                cell_color = "#606070"

            cell = QLabel(cell_text)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setStyleSheet(f"""
                background-color: {cell_bg};
                color: {cell_color};
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            """)
            cell.setFixedHeight(44)
            grid.addWidget(cell, 1, col)

        layout.addLayout(grid)
        return card

    def _open_editor(self, zone):
        dlg = RecurringScheduleDialog(self.db, zone, self.current_user, self)
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _on_saved(self):
        if self.scheduler:
            self.scheduler.reload()
        self.refresh()
        self.changed.emit()
