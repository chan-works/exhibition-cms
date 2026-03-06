from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
    QLineEdit, QTextEdit, QMessageBox, QHeaderView, QColorDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class ZoneDialog(QDialog):
    def __init__(self, parent=None, zone=None):
        super().__init__(parent)
        self.zone = zone
        self.selected_color = zone["color"] if zone else "#2196F3"
        self.setWindowTitle("구역 편집" if zone else "새 구역 추가")
        self.setFixedSize(420, 280)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: 1전시실")
        if self.zone:
            self.name_input.setText(self.zone["name"])
        form.addRow("구역 이름 *", self.name_input)

        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(70)
        self.desc_input.setPlaceholderText("구역 설명 (선택)")
        if self.zone:
            self.desc_input.setPlainText(self.zone.get("description", "") or "")
        form.addRow("설명", self.desc_input)

        # Color picker
        color_layout = QHBoxLayout()
        self.color_preview = QLabel("   ")
        self.color_preview.setFixedSize(36, 28)
        self.color_preview.setStyleSheet(
            f"background-color: {self.selected_color}; border-radius: 4px; border: 1px solid #0f3460;"
        )
        color_btn = QPushButton("색상 선택")
        color_btn.setFixedHeight(28)
        color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(color_btn)
        color_layout.addStretch()
        form.addRow("구역 색상", color_layout)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("저장")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self, "색상 선택")
        if color.isValid():
            self.selected_color = color.name()
            self.color_preview.setStyleSheet(
                f"background-color: {self.selected_color}; border-radius: 4px; border: 1px solid #0f3460;"
            )

    def _save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "오류", "구역 이름을 입력하세요.")
            return
        self.accept()

    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "description": self.desc_input.toPlainText().strip(),
            "color": self.selected_color,
        }


class ZoneManager(QWidget):
    zones_changed = Signal()

    def __init__(self, db, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("전시 구역 관리")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()

        if self.current_user["role"] in ("admin", "operator"):
            add_btn = QPushButton("+ 구역 추가")
            add_btn.setObjectName("primary")
            add_btn.clicked.connect(self._add_zone)
            header.addWidget(add_btn)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["구역 이름", "설명", "색상", "작업"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def refresh(self):
        zones = self.db.get_all_zones()
        self.table.setRowCount(len(zones))
        for i, zone in enumerate(zones):
            self.table.setItem(i, 0, QTableWidgetItem(zone["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(zone.get("description") or ""))

            color_lbl = QLabel("  " + zone.get("color", "#2196F3") + "  ")
            color_lbl.setStyleSheet(
                f"background-color: {zone.get('color', '#2196F3')}; "
                f"color: white; border-radius: 4px; padding: 2px 8px; font-size: 11px;"
            )
            color_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(i, 2, color_lbl)

            # Action buttons
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            if self.current_user["role"] in ("admin", "operator"):
                edit_btn = QPushButton("편집")
                edit_btn.setFixedHeight(26)
                edit_btn.clicked.connect(lambda checked, z=zone: self._edit_zone(z))
                btn_layout.addWidget(edit_btn)

            if self.current_user["role"] == "admin":
                del_btn = QPushButton("삭제")
                del_btn.setObjectName("danger")
                del_btn.setFixedHeight(26)
                del_btn.clicked.connect(lambda checked, z=zone: self._delete_zone(z))
                btn_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 3, btn_widget)
            self.table.setRowHeight(i, 40)

    def _add_zone(self):
        dlg = ZoneDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.db.create_zone(data["name"], data["description"], data["color"])
            self.refresh()
            self.zones_changed.emit()

    def _edit_zone(self, zone):
        dlg = ZoneDialog(self, zone=zone)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.db.update_zone(zone["id"], data["name"], data["description"], data["color"])
            self.refresh()
            self.zones_changed.emit()

    def _delete_zone(self, zone):
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"'{zone['name']}' 구역을 삭제하시겠습니까?\n"
            "이 구역의 모든 스케줄도 함께 삭제됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_zone(zone["id"])
            self.refresh()
            self.zones_changed.emit()
