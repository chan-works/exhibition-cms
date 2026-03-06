from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt

ROLES = {"admin": "관리자", "operator": "운영자", "viewer": "열람자"}


class UserDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("사용자 편집" if user else "새 사용자 추가")
        self.setFixedSize(400, 340)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("영문/숫자/_ 조합")
        if self.user:
            self.username_input.setText(self.user["username"])
            self.username_input.setReadOnly(True)
        form.addRow("사용자 이름 *", self.username_input)

        self.fullname_input = QLineEdit()
        self.fullname_input.setPlaceholderText("표시 이름")
        if self.user:
            self.fullname_input.setText(self.user.get("full_name") or "")
        form.addRow("성명", self.fullname_input)

        self.role_combo = QComboBox()
        for key, label in ROLES.items():
            self.role_combo.addItem(label, key)
        if self.user:
            idx = self.role_combo.findData(self.user["role"])
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        form.addRow("권한", self.role_combo)

        pw_label = "새 비밀번호 (변경시만)" if self.user else "비밀번호 *"
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("6자 이상" if not self.user else "비워두면 변경 안함")
        form.addRow(pw_label, self.password_input)

        self.password2_input = QLineEdit()
        self.password2_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password2_input.setPlaceholderText("비밀번호 확인")
        form.addRow("비밀번호 확인", self.password2_input)

        if self.user:
            self.active_check = QCheckBox("활성 계정")
            self.active_check.setChecked(bool(self.user.get("is_active", 1)))
            form.addRow("상태", self.active_check)

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

    def _save(self):
        if not self.user and not self.username_input.text().strip():
            QMessageBox.warning(self, "오류", "사용자 이름을 입력하세요.")
            return
        pw = self.password_input.text()
        pw2 = self.password2_input.text()
        if pw or not self.user:
            if len(pw) < 6:
                QMessageBox.warning(self, "오류", "비밀번호는 6자 이상이어야 합니다.")
                return
            if pw != pw2:
                QMessageBox.warning(self, "오류", "비밀번호가 일치하지 않습니다.")
                return
        self.accept()

    def get_data(self):
        data = {
            "username": self.username_input.text().strip(),
            "full_name": self.fullname_input.text().strip(),
            "role": self.role_combo.currentData(),
            "password": self.password_input.text(),
        }
        if self.user:
            data["is_active"] = 1 if self.active_check.isChecked() else 0
        return data


class UserManager(QWidget):
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

        header = QHBoxLayout()
        title = QLabel("사용자 관리")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()
        add_btn = QPushButton("+ 사용자 추가")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_user)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["사용자 이름", "성명", "권한", "상태", "작업"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def refresh(self):
        users = self.db.get_all_users()
        self.table.setRowCount(len(users))
        for i, user in enumerate(users):
            self.table.setItem(i, 0, QTableWidgetItem(user["username"]))
            self.table.setItem(i, 1, QTableWidgetItem(user.get("full_name") or ""))
            self.table.setItem(i, 2, QTableWidgetItem(ROLES.get(user["role"], user["role"])))
            status = "활성" if user.get("is_active", 1) else "비활성"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(
                Qt.GlobalColor.green if user.get("is_active", 1) else Qt.GlobalColor.red
            )
            self.table.setItem(i, 3, status_item)

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            edit_btn = QPushButton("편집")
            edit_btn.setFixedHeight(26)
            edit_btn.clicked.connect(lambda checked, u=user: self._edit_user(u))
            btn_layout.addWidget(edit_btn)

            if user["username"] != self.current_user["username"]:
                del_btn = QPushButton("삭제")
                del_btn.setObjectName("danger")
                del_btn.setFixedHeight(26)
                del_btn.clicked.connect(lambda checked, u=user: self._delete_user(u))
                btn_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 4, btn_widget)
            self.table.setRowHeight(i, 40)

    def _add_user(self):
        dlg = UserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.db.create_user(data["username"], data["password"], data["full_name"], data["role"])
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"사용자 추가 실패:\n{e}")

    def _edit_user(self, user):
        dlg = UserDialog(self, user=user)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.db.update_user(user["id"], data["full_name"], data["role"], data.get("is_active", 1))
            if data["password"]:
                self.db.update_user_password(user["id"], data["password"])
            self.refresh()

    def _delete_user(self, user):
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"'{user['username']}' 사용자를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_user(user["id"])
            self.refresh()
