import sys
import logging

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from database.db_manager import DatabaseManager
from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow
from ui.styles import DARK_STYLE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Exhibition CMS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ExhibitionCMS")
    app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app.setStyleSheet(DARK_STYLE)

    try:
        db = DatabaseManager()
    except Exception as e:
        QMessageBox.critical(None, "DB 오류", f"데이터베이스 초기화 실패:\n{e}")
        sys.exit(1)

    login = LoginDialog(db)
    if login.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    user = login.get_user()
    window = MainWindow(db, user)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
