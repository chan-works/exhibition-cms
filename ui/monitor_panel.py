import urllib.request
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QPixmap, QImage

SCREENSHOT_PORT = 19999
REFRESH_INTERVAL_MS = 3000  # 3 seconds


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
