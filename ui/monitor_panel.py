import urllib.request
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QMessageBox,
    QDialog, QTextEdit
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QPixmap, QImage

SCREENSHOT_PORT = 19999
REFRESH_INTERVAL_MS = 3000  # 3 seconds

# screenshot_server.py path — works both as script and PyInstaller exe
def _find_screenshot_server() -> Path:
    import sys
    candidates = []
    # PyInstaller bundled exe: files are extracted to sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "screenshot_server.py")
    # Next to the exe / script entry point
    candidates.append(Path(sys.executable).parent / "screenshot_server.py")
    # Project root when running as .py script
    candidates.append(Path(__file__).resolve().parent.parent / "screenshot_server.py")
    for p in candidates:
        if p.exists():
            return p
    return candidates[-1]  # return last candidate for error message

SCREENSHOT_SERVER_PATH = _find_screenshot_server()


class ServerLaunchWorker(QObject):
    """SSH into each computer device and start screenshot_server.py."""
    log = Signal(str)        # progress messages
    finished = Signal()

    def __init__(self, devices):
        super().__init__()
        # Only computer devices with SSH credentials
        self._devices = [
            d for d in devices
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("ssh_user")
            and d.get("config", {}).get("host")
        ]

    def run(self):
        try:
            import paramiko
        except ImportError:
            self.log.emit("❌ paramiko 미설치 — pip install paramiko 실행 후 재시도하세요.")
            self.finished.emit()
            return

        if not SCREENSHOT_SERVER_PATH.exists():
            self.log.emit(f"❌ screenshot_server.py 파일을 찾을 수 없습니다:\n   {SCREENSHOT_SERVER_PATH}")
            self.finished.emit()
            return

        server_code = SCREENSHOT_SERVER_PATH.read_text(encoding="utf-8")

        for dev in self._devices:
            cfg = dev.get("config", {})
            host = cfg.get("host", "")
            user = cfg.get("ssh_user", "")
            password = cfg.get("ssh_password", "")
            name = dev.get("name", host)
            self.log.emit(f"\n▶ [{name}] {host} 연결 중...")

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, username=user, password=password, timeout=10)

                # Upload screenshot_server.py via SFTP
                sftp = ssh.open_sftp()
                remote_path = "/tmp/screenshot_server.py"
                try:
                    # Try Windows home dir first
                    _, out, _ = ssh.exec_command("echo %USERPROFILE%", timeout=3)
                    win_home = out.read().decode(errors="ignore").strip()
                    if win_home and "%" not in win_home:
                        remote_path = win_home.replace("\\", "/") + "/screenshot_server.py"
                except Exception:
                    pass

                with sftp.open(remote_path, "w") as f:
                    f.write(server_code)
                sftp.close()
                self.log.emit(f"   ✓ screenshot_server.py 업로드 완료 → {remote_path}")

                # Install dependencies (non-blocking)
                ssh.exec_command(
                    "pip install mss pillow --quiet 2>&1 || python -m pip install mss pillow --quiet 2>&1",
                    timeout=5
                )

                # Kill any existing server process on port 19999
                ssh.exec_command(
                    f"pkill -f screenshot_server.py 2>/dev/null; "
                    f"taskkill /F /FI \"IMAGENAME eq python.exe\" /FI \"WINDOWTITLE eq screenshot_server\" 2>nul; "
                    f"sleep 1",
                    timeout=5
                )

                # Start server in background
                bg_cmd = (
                    f"nohup python {remote_path} > /tmp/screenshot_server.log 2>&1 & "
                    f"|| start /B pythonw {remote_path}"
                )
                ssh.exec_command(bg_cmd, timeout=3)
                ssh.close()
                self.log.emit(f"   ✓ 서버 시작 명령 전송 완료")

            except Exception as e:
                self.log.emit(f"   ❌ 실패: {e}")

        self.log.emit("\n완료.")
        self.finished.emit()


class ScreenFetcher(QObject):
    fetched = Signal(str, bytes)   # device_id, jpeg_bytes
    failed = Signal(str, str)      # device_id, error

    def __init__(self, device_id: str, url: str):
        super().__init__()
        self.device_id = device_id
        self.url = url

    def fetch(self):
        try:
            req = urllib.request.urlopen(self.url, timeout=2)
            data = req.read()
            self.fetched.emit(self.device_id, data)
        except Exception as e:
            self.failed.emit(self.device_id, str(e))


class ScreenTile(QFrame):
    """Single PC screen monitoring tile."""

    clicked = Signal(str)  # device_id

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self.device = device
        self.device_id = str(device["id"])
        host = device.get("config", {}).get("host", "")
        self.url = f"http://{host}:{SCREENSHOT_PORT}/screenshot"
        self._online = False
        self.setObjectName("card")
        self.setMinimumSize(280, 200)
        self.setMaximumWidth(400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#card {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
            }
            QFrame#card:hover {
                border-color: #e94560;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #606070; font-size: 10px;")
        self.status_dot.setFixedWidth(14)
        hdr.addWidget(self.status_dot)

        name_lbl = QLabel(self.device["name"])
        name_lbl.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 13px;")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        host = self.device.get("config", {}).get("host", "")
        ip_lbl = QLabel(host)
        ip_lbl.setStyleSheet("color: #606070; font-size: 11px;")
        hdr.addWidget(ip_lbl)
        layout.addLayout(hdr)

        # Screen area
        self.screen_lbl = QLabel()
        self.screen_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_lbl.setMinimumHeight(150)
        self.screen_lbl.setStyleSheet("""
            background-color: #0a0a15;
            border-radius: 4px;
            color: #404050;
            font-size: 12px;
        """)
        self.screen_lbl.setText("연결 대기 중...")
        layout.addWidget(self.screen_lbl)

        # Footer
        self.time_lbl = QLabel("")
        self.time_lbl.setStyleSheet("color: #404050; font-size: 10px;")
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.time_lbl)

    def update_screen(self, jpeg_bytes: bytes):
        img = QImage()
        img.loadFromData(jpeg_bytes, "JPEG")
        if not img.isNull():
            pixmap = QPixmap.fromImage(img)
            pixmap = pixmap.scaledToWidth(
                self.screen_lbl.width() - 4,
                Qt.TransformationMode.SmoothTransformation
            )
            self.screen_lbl.setPixmap(pixmap)
            self.screen_lbl.setText("")
        self._set_online(True)
        self.time_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def set_error(self, msg: str):
        self.screen_lbl.setPixmap(QPixmap())
        if "refused" in msg.lower() or "10061" in msg:
            self.screen_lbl.setText("오프라인\n(PC 꺼짐 또는 서버 미실행)")
        elif "timed out" in msg.lower() or "timeout" in msg.lower():
            self.screen_lbl.setText("응답 없음\n(네트워크 확인)")
        else:
            self.screen_lbl.setText(f"연결 실패\n{msg[:40]}")
        self._set_online(False)
        self.time_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def _set_online(self, online: bool):
        self._online = online
        color = "#4CAF50" if online else "#606070"
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.device_id)
        super().mousePressEvent(event)


class MonitorPanel(QWidget):
    """Real-time PC screen monitoring panel."""

    def __init__(self, db, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self._tiles = {}          # device_id → ScreenTile
        self._fetchers = {}       # device_id → (QThread, ScreenFetcher)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._build_ui()
        self._load_devices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("PC 화면 모니터링")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()

        self.auto_start_btn = QPushButton("서버 자동 시작 (SSH)")
        self.auto_start_btn.setFixedHeight(30)
        self.auto_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a4a80; color: white;
                border: none; border-radius: 4px;
                padding: 0 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2a5a90; }
        """)
        self.auto_start_btn.clicked.connect(self._auto_start_servers)
        header.addWidget(self.auto_start_btn)

        hint_btn = QPushButton("서버 설치 안내")
        hint_btn.setFixedHeight(30)
        hint_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0b0c0;
                border: 1px solid #0f3460;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 12px;
            }
            QPushButton:hover { color: white; border-color: #e94560; }
        """)
        hint_btn.clicked.connect(self._show_install_hint)
        header.addWidget(hint_btn)

        self.toggle_btn = QPushButton("모니터링 시작")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.setFixedHeight(30)
        self.toggle_btn.clicked.connect(self._toggle_monitoring)
        header.addWidget(self.toggle_btn)

        layout.addLayout(header)

        hint = QLabel(
            "PC 화면을 보려면 각 PC에서 screenshot_server.py를 실행하세요. "
            f"(포트: {SCREENSHOT_PORT})"
        )
        hint.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Scroll area for tiles
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

    def _load_devices(self):
        # Clear existing
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tiles.clear()

        devices = self.db.get_all_devices()
        computer_devices = [d for d in devices if d.get("device_type") == "computer"
                           and d.get("config", {}).get("host")]

        if not computer_devices:
            empty = QLabel("컴퓨터 타입 디바이스가 없습니다.\n디바이스 관리에서 PC를 추가하세요.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #606070; font-size: 14px; padding: 40px;")
            self.grid_layout.addWidget(empty, 0, 0)
            return

        cols = 3
        for i, dev in enumerate(computer_devices):
            tile = ScreenTile(dev)
            tile.clicked.connect(self._on_tile_click)
            self._tiles[str(dev["id"])] = tile
            self.grid_layout.addWidget(tile, i // cols, i % cols)

    def _toggle_monitoring(self):
        if self._timer.isActive():
            self._timer.stop()
            self.toggle_btn.setText("모니터링 시작")
            self.toggle_btn.setStyleSheet("")
        else:
            self._load_devices()
            self._refresh_all()
            self._timer.start(REFRESH_INTERVAL_MS)
            self.toggle_btn.setText("모니터링 중지")
            self.toggle_btn.setObjectName("danger")
            self.toggle_btn.setStyleSheet("background-color: #8b2222;")

    def _refresh_all(self):
        for dev_id, tile in self._tiles.items():
            thread = QThread()
            fetcher = ScreenFetcher(dev_id, tile.url)
            fetcher.moveToThread(thread)
            thread.started.connect(fetcher.fetch)
            fetcher.fetched.connect(self._on_fetched)
            fetcher.failed.connect(self._on_failed)
            fetcher.fetched.connect(lambda *_: thread.quit())
            fetcher.failed.connect(lambda *_: thread.quit())
            thread.start()
            self._fetchers[dev_id] = (thread, fetcher)

    def _on_fetched(self, dev_id, data):
        if dev_id in self._tiles:
            self._tiles[dev_id].update_screen(data)

    def _on_failed(self, dev_id, msg):
        if dev_id in self._tiles:
            self._tiles[dev_id].set_error(msg)

    def _on_tile_click(self, dev_id):
        if dev_id in self._tiles:
            tile = self._tiles[dev_id]
            pm = tile.screen_lbl.pixmap()
            if pm and not pm.isNull():
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
                dlg = QDialog(self)
                dlg.setWindowTitle(f"{tile.device['name']} - 화면 크게 보기")
                dlg.resize(960, 600)
                lyt = QVBoxLayout(dlg)
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setPixmap(pm.scaledToWidth(920, Qt.TransformationMode.SmoothTransformation))
                lyt.addWidget(lbl)
                dlg.exec()

    def _auto_start_servers(self):
        devices = self.db.get_all_devices()
        ssh_devices = [
            d for d in devices
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("ssh_user")
        ]
        if not ssh_devices:
            QMessageBox.warning(
                self, "SSH 미설정",
                "SSH 사용자명이 설정된 컴퓨터 디바이스가 없습니다.\n\n"
                "디바이스 관리 → 컴퓨터 편집 → SSH 사용자/비밀번호를 입력하세요."
            )
            return

        self.auto_start_btn.setEnabled(False)
        self.auto_start_btn.setText("시작 중...")

        # Log dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("서버 자동 시작")
        dlg.resize(520, 360)
        dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        layout = QVBoxLayout(dlg)
        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setStyleSheet("background:#0a0a15; color:#c0d0e0; font-family:monospace; font-size:12px;")
        layout.addWidget(log_box)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        def append_log(msg):
            log_box.append(msg)

        worker = ServerLaunchWorker(devices)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(append_log)

        def on_finished():
            thread.quit()
            self.auto_start_btn.setEnabled(True)
            self.auto_start_btn.setText("서버 자동 시작 (SSH)")

        worker.finished.connect(on_finished)
        thread.start()
        dlg.exec()

    def _show_install_hint(self):
        QMessageBox.information(
            self, "서버 설치 안내",
            "각 관리 PC에서 아래 명령어를 실행하세요:\n\n"
            "1. Python 설치 (python.org)\n"
            "2. pip install mss pillow\n"
            "3. screenshot_server.py 파일을 PC에 복사\n"
            "4. python screenshot_server.py 실행\n\n"
            f"포트 {SCREENSHOT_PORT}이 방화벽에서 허용되어야 합니다.\n\n"
            "또는 Windows 시작 시 자동 실행하려면:\n"
            "  시작 메뉴 → 시작프로그램 폴더에 바로가기 추가"
        )

    def refresh(self):
        """Called when switching to this panel."""
        self._load_devices()

    def stop(self):
        self._timer.stop()
