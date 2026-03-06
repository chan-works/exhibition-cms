import urllib.request
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSizePolicy, QFrame, QWidget
)
from PySide6.QtCore import Qt, QTimer, QThread, QObject, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut

SCREENSHOT_PORT = 19999


class ScreenFetchWorker(QObject):
    fetched = Signal(bytes)
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def fetch(self):
        try:
            req = urllib.request.urlopen(self.url, timeout=2)
            self.fetched.emit(req.read())
        except Exception as e:
            self.failed.emit(str(e))


class ScreenViewerDialog(QDialog):
    """Real-time screen viewer for a single computer device."""

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        cfg = device.get("config", {})
        self.device = device
        self.host = cfg.get("host", "")
        self.url = f"http://{self.host}:{SCREENSHOT_PORT}/screenshot"
        self._thread = None
        self._worker = None
        self._fetching = False
        self._last_pixmap = None
        self._refresh_ms = 1000

        self.setWindowTitle(f"화면 모니터 — {device['name']} ({self.host})")
        self.resize(1024, 640)
        self.setMinimumSize(640, 400)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

        # ESC shortcut to close
        QShortcut(QKeySequence("Escape"), self, self.close)
        # F11 fullscreen
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._do_fetch)
        self._start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet("background-color: #0f3460; border-bottom: 1px solid #1a3a60;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 4, 12, 4)
        tb_layout.setSpacing(10)

        name_lbl = QLabel(f"🖥  {self.device['name']}  |  {self.host}")
        name_lbl.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        tb_layout.addWidget(name_lbl)
        tb_layout.addStretch()

        # Refresh interval
        interval_lbl = QLabel("갱신 주기:")
        interval_lbl.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        tb_layout.addWidget(interval_lbl)

        for label, ms in [("0.5초", 500), ("1초", 1000), ("2초", 2000), ("5초", 5000)]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(ms == 1000)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #16213e;
                    color: #a0b0c0;
                    border: 1px solid #1a3a60;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #e94560;
                    color: white;
                    border-color: #e94560;
                }
                QPushButton:hover:!checked { background-color: #1a3060; }
            """)
            btn.clicked.connect(lambda checked, m=ms, b=btn: self._set_interval(m, b))
            tb_layout.addWidget(btn)
            setattr(self, f"_btn_{ms}", btn)

        # Fullscreen
        fs_btn = QPushButton("⛶ 전체화면  F11")
        fs_btn.setFixedHeight(28)
        fs_btn.setStyleSheet("""
            QPushButton {
                background-color: #16213e;
                color: #a0b0c0;
                border: 1px solid #1a3a60;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1a3060; color: white; }
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        tb_layout.addWidget(fs_btn)

        layout.addWidget(toolbar)

        # Screen display
        self.screen_lbl = QLabel()
        self.screen_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.screen_lbl.setStyleSheet("background-color: #050510;")
        self.screen_lbl.setText("연결 중...")
        self.screen_lbl.setStyleSheet("""
            background-color: #050510;
            color: #404060;
            font-size: 14px;
        """)
        layout.addWidget(self.screen_lbl, 1)

        # Status bar
        self.status_bar = QWidget()
        self.status_bar.setFixedHeight(26)
        self.status_bar.setStyleSheet("background-color: #0a0a20; border-top: 1px solid #0f3460;")
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(12, 0, 12, 0)

        self.status_lbl = QLabel("연결 대기 중...")
        self.status_lbl.setStyleSheet("color: #606070; font-size: 11px;")
        sb_layout.addWidget(self.status_lbl)
        sb_layout.addStretch()

        self.res_lbl = QLabel("")
        self.res_lbl.setStyleSheet("color: #606070; font-size: 11px;")
        sb_layout.addWidget(self.res_lbl)

        layout.addWidget(self.status_bar)

    def _set_interval(self, ms: int, clicked_btn: QPushButton):
        self._refresh_ms = ms
        for m in [500, 1000, 2000, 5000]:
            btn = getattr(self, f"_btn_{m}", None)
            if btn:
                btn.setChecked(m == ms)
        if self._timer.isActive():
            self._timer.setInterval(ms)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _start(self):
        self._timer.start(self._refresh_ms)
        self._do_fetch()

    def _do_fetch(self):
        if self._fetching:
            return
        self._fetching = True
        self._thread = QThread()
        self._worker = ScreenFetchWorker(self.url)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.fetch)
        self._worker.fetched.connect(self._on_fetched)
        self._worker.failed.connect(self._on_failed)
        self._worker.fetched.connect(lambda _: self._cleanup_thread())
        self._worker.failed.connect(lambda _: self._cleanup_thread())
        self._thread.start()

    def _cleanup_thread(self):
        self._fetching = False
        if self._thread:
            self._thread.quit()

    def _on_fetched(self, data: bytes):
        img = QImage()
        img.loadFromData(data, "JPEG")
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        self._last_pixmap = pm
        self._update_display()
        now = datetime.now().strftime("%H:%M:%S")
        self.status_lbl.setText(f"● 연결됨  |  마지막 갱신: {now}")
        self.status_lbl.setStyleSheet("color: #4CAF50; font-size: 11px;")
        self.res_lbl.setText(f"{img.width()} × {img.height()}")

    def _on_failed(self, msg: str):
        self.screen_lbl.setPixmap(QPixmap())
        if "10061" in msg or "refused" in msg.lower():
            text = f"⚠  연결 거부됨\n\n{self.host} 에서 screenshot_server.py 가 실행 중인지 확인하세요."
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            text = f"⚠  응답 없음\n\n{self.host} 네트워크 연결을 확인하세요."
        else:
            text = f"⚠  연결 실패\n\n{msg}"
        self.screen_lbl.setText(text)
        self.screen_lbl.setStyleSheet("""
            background-color: #050510;
            color: #e05060;
            font-size: 14px;
        """)
        self.status_lbl.setText(f"● 오프라인  |  {msg[:60]}")
        self.status_lbl.setStyleSheet("color: #e05060; font-size: 11px;")

    def _update_display(self):
        if not self._last_pixmap:
            return
        w = self.screen_lbl.width()
        h = self.screen_lbl.height()
        scaled = self._last_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.screen_lbl.setPixmap(scaled)
        self.screen_lbl.setStyleSheet("background-color: #050510;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def closeEvent(self, event):
        self._timer.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        super().closeEvent(event)
