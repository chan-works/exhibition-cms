from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTimeEdit, QCheckBox, QComboBox, QTextEdit, QLineEdit,
    QGroupBox, QScrollArea, QWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtGui import QFont


class ScheduleEditorDialog(QDialog):
    """Dialog to view/edit the schedule for a specific zone on a specific date."""

    schedule_saved = Signal()

    def __init__(self, db, zone, date_str, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.zone = zone
        self.date_str = date_str
        self.current_user = current_user
        self.readonly = current_user["role"] == "viewer"
        self.setWindowTitle(f"{zone['name']} - {date_str} 스케줄")
        self.setMinimumSize(440, 400)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header_lbl = QLabel(f"{self.zone['name']}")
        header_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; "
            f"color: {self.zone.get('color', '#e94560')};"
        )
        layout.addWidget(header_lbl)

        date_lbl = QLabel(self.date_str)
        date_lbl.setStyleSheet("color: #a0b0c0; font-size: 13px;")
        layout.addWidget(date_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep)

        # Enable toggle
        self.enabled_check = QCheckBox("이 날 스케줄 활성화")
        self.enabled_check.setChecked(True)
        self.enabled_check.toggled.connect(self._on_enabled_toggle)
        layout.addWidget(self.enabled_check)

        # Holiday
        self.holiday_check = QCheckBox("공휴일 / 휴관일로 지정")
        self.holiday_check.toggled.connect(self._on_holiday_toggle)
        layout.addWidget(self.holiday_check)

        self.holiday_name_input = QLineEdit()
        self.holiday_name_input.setPlaceholderText("예: 설날, 광복절 ...")
        self.holiday_name_input.setVisible(False)
        layout.addWidget(self.holiday_name_input)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep2)

        # Time settings
        self.time_group = QGroupBox("운영 시간")
        time_layout = QVBoxLayout(self.time_group)

        on_row = QHBoxLayout()
        on_lbl = QLabel("개관 (ON):")
        on_lbl.setFixedWidth(100)
        on_lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.time_on = QTimeEdit()
        self.time_on.setDisplayFormat("HH:mm")
        self.time_on.setTime(QTime(9, 0))
        self.time_on.setFixedHeight(34)
        self.use_on_check = QCheckBox("사용")
        self.use_on_check.setChecked(True)
        on_row.addWidget(on_lbl)
        on_row.addWidget(self.time_on)
        on_row.addWidget(self.use_on_check)
        time_layout.addLayout(on_row)

        off_row = QHBoxLayout()
        off_lbl = QLabel("폐관 (OFF):")
        off_lbl.setFixedWidth(100)
        off_lbl.setStyleSheet("color: #F44336; font-weight: bold;")
        self.time_off = QTimeEdit()
        self.time_off.setDisplayFormat("HH:mm")
        self.time_off.setTime(QTime(18, 0))
        self.time_off.setFixedHeight(34)
        self.use_off_check = QCheckBox("사용")
        self.use_off_check.setChecked(True)
        off_row.addWidget(off_lbl)
        off_row.addWidget(self.time_off)
        off_row.addWidget(self.use_off_check)
        time_layout.addLayout(off_row)

        layout.addWidget(self.time_group)

        # Notes
        notes_lbl = QLabel("메모")
        notes_lbl.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(notes_lbl)
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(60)
        self.notes_input.setPlaceholderText("이 날에 대한 메모 (선택)")
        layout.addWidget(self.notes_input)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if not self.readonly:
            delete_btn = QPushButton("스케줄 삭제")
            delete_btn.setObjectName("danger")
            delete_btn.clicked.connect(self._delete)
            btn_layout.addWidget(delete_btn)

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
            self.enabled_check.setEnabled(False)
            self.holiday_check.setEnabled(False)
            self.holiday_name_input.setEnabled(False)
            self.time_on.setEnabled(False)
            self.time_off.setEnabled(False)
            self.use_on_check.setEnabled(False)
            self.use_off_check.setEnabled(False)
            self.notes_input.setReadOnly(True)

    def _load(self):
        sched = self.db.get_schedule(self.zone["id"], self.date_str)
        if sched:
            self.enabled_check.setChecked(bool(sched.get("is_enabled", 1)))
            is_holiday = bool(sched.get("is_holiday", 0))
            self.holiday_check.setChecked(is_holiday)
            self.holiday_name_input.setVisible(is_holiday)
            self.holiday_name_input.setText(sched.get("holiday_name", "") or "")

            if sched.get("time_on"):
                h, m = map(int, sched["time_on"].split(":"))
                self.time_on.setTime(QTime(h, m))
                self.use_on_check.setChecked(True)
            else:
                self.use_on_check.setChecked(False)

            if sched.get("time_off"):
                h, m = map(int, sched["time_off"].split(":"))
                self.time_off.setTime(QTime(h, m))
                self.use_off_check.setChecked(True)
            else:
                self.use_off_check.setChecked(False)

            self.notes_input.setPlainText(sched.get("notes", "") or "")
        self._on_enabled_toggle(self.enabled_check.isChecked())

    def _on_enabled_toggle(self, checked):
        self.time_group.setEnabled(checked and not self.holiday_check.isChecked())

    def _on_holiday_toggle(self, checked):
        self.holiday_name_input.setVisible(checked)
        self.time_group.setEnabled(self.enabled_check.isChecked() and not checked)

    def _save(self):
        is_enabled = self.enabled_check.isChecked()
        is_holiday = self.holiday_check.isChecked()
        holiday_name = self.holiday_name_input.text().strip() if is_holiday else ""
        time_on = self.time_on.time().toString("HH:mm") if self.use_on_check.isChecked() and not is_holiday else None
        time_off = self.time_off.time().toString("HH:mm") if self.use_off_check.isChecked() and not is_holiday else None
        notes = self.notes_input.toPlainText().strip()

        self.db.save_schedule(
            self.zone["id"], self.date_str,
            time_on, time_off, is_enabled, is_holiday, holiday_name, notes
        )
        self.db.add_notification(
            "info",
            f"스케줄 업데이트: {self.zone['name']} {self.date_str}",
            f"ON={time_on or '-'}, OFF={time_off or '-'}, 공휴일={is_holiday}"
        )
        self.schedule_saved.emit()
        self.accept()

    def _delete(self):
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"{self.zone['name']}의 {self.date_str} 스케줄을 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_schedule(self.zone["id"], self.date_str)
            self.schedule_saved.emit()
            self.accept()
