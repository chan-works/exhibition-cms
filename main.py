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

WEB_PORT = 8080  # 웹 서버 포트 (브라우저 접속용)


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

    # ── 웹 서버 백그라운드 시작 (맥북 등 브라우저 접속용) ─────────────────
    try:
        from web_server import open_firewall
        open_firewall(WEB_PORT)
    except Exception:
        pass
    try:
        from web.server import start_background
        start_background(db, scheduler=None, port=WEB_PORT)
        log = logging.getLogger(__name__)
        log.info("웹 서버 실행 중 → http://0.0.0.0:%d (이 PC의 IP로 접속)", WEB_PORT)
        try:
            from web_server import get_tailscale_ip
            ts = get_tailscale_ip()
            if ts:
                log.info("Tailscale 접속 주소 → http://%s:%d", ts, WEB_PORT)
        except Exception:
            pass
    except Exception as e:
        logging.getLogger(__name__).warning("웹 서버 시작 실패 (무시): %s", e)

    login = LoginDialog(db)
    if login.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    user = login.get_user()
    window = MainWindow(db, user)
    window.show()

    # 스케줄러가 생성된 후 웹 서버에 주입
    try:
        from web.server import init_app
        init_app(db, window.scheduler)
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
