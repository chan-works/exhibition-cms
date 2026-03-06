from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.styles import DARK_STYLE


class LoginDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._user = None
        self.setWindowTitle("Exhibition CMS - 로그인")
        self.setFixedSize(400, 320)
        self.setStyleSheet(DARK_STYLE)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        # Title
        title = QLabel("Exhibition CMS")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("color: #e94560; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("전시장 통합 제어 시스템")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #a0b0c0; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep)

        # Username
        lbl_user = QLabel("사용자 이름")
        lbl_user.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(lbl_user)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("username")
        self.username_input.setFixedHeight(38)
        layout.addWidget(self.username_input)

        # Password
        lbl_pw = QLabel("비밀번호")
        lbl_pw.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(lbl_pw)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("password")
        self.password_input.setFixedHeight(38)
        self.password_input.returnPressed.connect(self._do_login)
        layout.addWidget(self.password_input)

        # Login button
        self.login_btn = QPushButton("로그인")
        self.login_btn.setObjectName("primary")
        self.login_btn.setFixedHeight(40)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self._do_login)
        layout.addWidget(self.login_btn)

        hint = QLabel("기본 계정: admin / admin123")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #606070; font-size: 11px;")
        layout.addWidget(hint)

    def _do_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "오류", "사용자 이름과 비밀번호를 입력하세요.")
            return
        user = self.db.authenticate_user(username, password)
        if user:
            self._user = user
            self.accept()
        else:
            QMessageBox.critical(self, "로그인 실패", "사용자 이름 또는 비밀번호가 올바르지 않습니다.")
            self.password_input.clear()
            self.password_input.setFocus()

    def get_user(self):
        return self._user
