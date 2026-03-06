import urllib.request
import os
import base64
import subprocess
import platform
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
    """
    Start screenshot_server.py on remote PCs.
    Tries WinRM (port 5985, no SSH needed) first, then falls back to SSH (port 22).
    """
    log = Signal(str)
    finished = Signal()

    def __init__(self, devices):
        super().__init__()
        self._devices = [
            d for d in devices
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]

    def run(self):
        if not SCREENSHOT_SERVER_PATH.exists():
            self.log.emit(f"❌ screenshot_server.py 파일을 찾을 수 없습니다:\n   {SCREENSHOT_SERVER_PATH}")
            self.finished.emit()
            return

        for dev in self._devices:
            cfg = dev.get("config", {})
            host = cfg.get("host", "")
            user = cfg.get("ssh_user", "")
            password = cfg.get("ssh_password", "")
            name = dev.get("name", host)
            self.log.emit(f"\n▶ [{name}]  {host}")

            # 1st: Try WinRM (port 5985) — works without SSH
            if platform.system() == "Windows":
                ok, msg = self._try_winrm(host, user, password)
                if ok:
                    self.log.emit(f"   ✓ WinRM 연결 성공\n   ✓ {msg}")
                    continue
                self.log.emit(f"   ✗ WinRM 실패: {msg}")

            # 2nd: Try SSH (port 22)
            if user:
                ok, msg = self._try_ssh(host, user, password)
                if ok:
                    self.log.emit(f"   ✓ SSH 연결 성공\n   ✓ {msg}")
                    continue
                self.log.emit(f"   ✗ SSH 실패: {msg}")
            else:
                self.log.emit("   ✗ SSH 사용자 미설정 — 디바이스 편집에서 SSH 사용자/비밀번호 입력 필요")

            self.log.emit(
                "   ℹ  자동 시작 불가 → '설치파일 생성' 버튼으로 .bat 파일을 만들어\n"
                "      대상 PC에서 한 번 실행하면 이후 자동으로 작동합니다."
            )

        self.log.emit("\n완료.")
        self.finished.emit()

    def _try_winrm(self, host: str, user: str, password: str):
        """Use PowerShell remoting (WinRM port 5985) to deploy and start the server."""
        try:
            b64 = base64.b64encode(SCREENSHOT_SERVER_PATH.read_bytes()).decode("ascii")

            # Build credential block if credentials provided
            if user and password:
                cred_block = (
                    f"$pw=ConvertTo-SecureString '{password}' -AsPlainText -Force;"
                    f"$cred=New-Object PSCredential('{user}',$pw);"
                )
                session_args = f"-ComputerName {host} -Credential $cred"
            else:
                cred_block = ""
                session_args = f"-ComputerName {host}"

            # Add to TrustedHosts first
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 f"Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '{host}' -Force -Concatenate"],
                capture_output=True, timeout=10
            )

            # Remote script: decode b64 → write file → install packages → start server
            remote_script = (
                f"$b='{b64}';"
                "$p=\"$env:USERPROFILE\\ExhibitionCMS\\screenshot_server.py\";"
                "[IO.Directory]::CreateDirectory(\"$env:USERPROFILE\\ExhibitionCMS\")|Out-Null;"
                "[IO.File]::WriteAllBytes($p,[Convert]::FromBase64String($b));"
                "python -m pip install mss pillow --quiet 2>$null;"
                "$s=\"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\";"
                "\"@echo off`nstart `\"`\" /B pythonw `\"$p`\"\"|Set-Content \"$s\\ExhibitionCMS-ScreenServer.bat\";"
                "taskkill /F /IM pythonw.exe 2>$null;"
                "Start-Process pythonw -ArgumentList $p -WindowStyle Hidden;"
                "\"서버 시작 완료: $p\""
            )

            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                f"{cred_block}Invoke-Command {session_args} -ScriptBlock {{{remote_script}}}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return True, result.stdout.strip() or "서버 시작 완료"
            return False, result.stderr.strip() or "알 수 없는 오류"
        except Exception as e:
            return False, str(e)

    def _try_ssh(self, host: str, user: str, password: str):
        """Use SSH (port 22) to deploy and start the server."""
        try:
            import paramiko
        except ImportError:
            return False, "paramiko 미설치 (pip install paramiko)"

        try:
            server_code = SCREENSHOT_SERVER_PATH.read_text(encoding="utf-8")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=user, password=password, timeout=10)

            sftp = ssh.open_sftp()
            remote_path = "/tmp/screenshot_server.py"
            try:
                _, out, _ = ssh.exec_command("echo %USERPROFILE%", timeout=3)
                win_home = out.read().decode(errors="ignore").strip()
                if win_home and "%" not in win_home:
                    remote_path = win_home.replace("\\", "/") + "/ExhibitionCMS/screenshot_server.py"
                    ssh.exec_command(f"mkdir -p \"{win_home}/ExhibitionCMS\"", timeout=3)
            except Exception:
                pass

            with sftp.open(remote_path, "w") as f:
                f.write(server_code)
            sftp.close()

            ssh.exec_command("python -m pip install mss pillow --quiet", timeout=10)
            ssh.exec_command(
                f"nohup python {remote_path} > /tmp/screenshot_server.log 2>&1 & "
                f"|| (taskkill /F /IM pythonw.exe >nul 2>&1 & start /B pythonw {remote_path})",
                timeout=5
            )
            ssh.close()
            return True, "서버 시작 완료"
        except Exception as e:
            return False, str(e)


def generate_setup_bat(device: dict) -> str:
    """
    Generate a fully self-contained Windows .bat installer for screenshot_server.py.
    The .bat file: writes the server script, installs Python if missing,
    installs mss/pillow, opens firewall port 19999, and registers auto-start.
    """
    if not SCREENSHOT_SERVER_PATH.exists():
        raise FileNotFoundError(f"screenshot_server.py 를 찾을 수 없습니다: {SCREENSHOT_SERVER_PATH}")

    b64 = base64.b64encode(SCREENSHOT_SERVER_PATH.read_bytes()).decode("ascii")
    # Split into 76-char lines safe for batch `echo`
    b64_lines = "\n".join(f"echo {b64[i:i+76]}>>\"%%TMPB64%%\"" for i in range(0, len(b64), 76))

    name = device.get("name", "PC")
    host = device.get("config", {}).get("host", "")

    return (
        "@echo off\n"
        "chcp 65001 >nul\n"
        f"title Exhibition CMS - 화면서버 설치 [{name}]\n"
        "echo.\n"
        "echo  ==============================================\n"
        f"echo    Exhibition CMS 화면 모니터링 서버 설치\n"
        f"echo    대상 PC : {name}  ({host})\n"
        "echo  ==============================================\n"
        "echo.\n"
        "\n"
        "set INSTALL_DIR=%USERPROFILE%\\ExhibitionCMS\n"
        "set TMPB64=%TEMP%\\cms_b64.tmp\n"
        "mkdir \"%INSTALL_DIR%\" 2>nul\n"
        "\n"
        "REM [1/4] screenshot_server.py 생성\n"
        "echo  [1/4] 서버 파일 생성 중...\n"
        "del \"%TMPB64%\" 2>nul\n"
        + b64_lines + "\n"
        "powershell -NoProfile -Command "
        "\"$b=[Convert]::FromBase64String((gc '%TMPB64%') -join '');"
        "[IO.File]::WriteAllBytes('%INSTALL_DIR%\\screenshot_server.py',$b)\"\n"
        "del \"%TMPB64%\" 2>nul\n"
        "\n"
        "REM [2/4] Python 확인 및 자동 설치\n"
        "echo  [2/4] Python 확인 중...\n"
        "python --version >nul 2>&1\n"
        "if errorlevel 1 (\n"
        "    echo      Python 없음 - 자동 다운로드 중... ^(인터넷 필요^)\n"
        "    powershell -NoProfile -Command \"Invoke-WebRequest "
        "'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' "
        "-OutFile '%TEMP%\\py_setup.exe'\"\n"
        "    \"%TEMP%\\py_setup.exe\" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0\n"
        "    set \"PATH=%LOCALAPPDATA%\\Programs\\Python\\Python311;"
        "%LOCALAPPDATA%\\Programs\\Python\\Python311\\Scripts;%PATH%\"\n"
        "    echo      Python 설치 완료\n"
        ")\n"
        "\n"
        "REM [3/4] 패키지 설치\n"
        "echo  [3/4] 패키지 설치 중... ^(mss, pillow^)\n"
        "python -m pip install mss pillow --quiet --disable-pip-version-check\n"
        "\n"
        "REM [4/4] 방화벽 + 자동시작 등록\n"
        "echo  [4/4] 방화벽 및 자동시작 설정 중...\n"
        "netsh advfirewall firewall delete rule name=\"ExhibitionCMS-Screen\" >nul 2>&1\n"
        "netsh advfirewall firewall add rule name=\"ExhibitionCMS-Screen\" "
        "protocol=TCP dir=in localport=19999 action=allow >nul 2>&1\n"
        "\n"
        "set \"STARTUP=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\"\n"
        "(echo @echo off & echo start \"\" /B pythonw \"%INSTALL_DIR%\\screenshot_server.py\")"
        " > \"%STARTUP%\\ExhibitionCMS-ScreenServer.bat\"\n"
        "\n"
        "REM 즉시 시작\n"
        "taskkill /F /IM pythonw.exe >nul 2>&1\n"
        "start \"\" /B pythonw \"%INSTALL_DIR%\\screenshot_server.py\"\n"
        "\n"
        "echo.\n"
        "echo  ==============================================\n"
        "echo    설치 완료!\n"
        "echo    - CMS에서 이 PC 화면이 즉시 표시됩니다\n"
        "echo    - Windows 시작 시 자동으로 실행됩니다\n"
        "echo    - 포트: 19999\n"
        "echo  ==============================================\n"
        "echo.\n"
        "pause\n"
    )


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

        self.gen_installer_btn = QPushButton("설치파일 생성")
        self.gen_installer_btn.setFixedHeight(30)
        self.gen_installer_btn.setToolTip("각 PC에서 한 번만 실행하면 되는 .bat 설치파일을 생성합니다")
        self.gen_installer_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32; color: white;
                border: none; border-radius: 4px;
                padding: 0 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #388e3c; }
        """)
        self.gen_installer_btn.clicked.connect(self._generate_installers)
        header.addWidget(self.gen_installer_btn)

        self.auto_start_btn = QPushButton("SSH 자동 시작")
        self.auto_start_btn.setFixedHeight(30)
        self.auto_start_btn.setToolTip("SSH가 설정된 PC에만 작동합니다")
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

    def _generate_installers(self):
        devices = self.db.get_all_devices()
        computer_devices = [
            d for d in devices
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]
        if not computer_devices:
            QMessageBox.warning(self, "PC 없음",
                "등록된 컴퓨터 디바이스가 없습니다.\n디바이스 관리에서 PC를 추가하세요.")
            return

        # Save to Desktop\ExhibitionCMS-설치파일
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        out_dir = desktop / "ExhibitionCMS-설치파일"
        out_dir.mkdir(exist_ok=True)

        saved = []
        errors = []
        for dev in computer_devices:
            safe_name = dev["name"].replace(" ", "_").replace("/", "-")
            bat_path = out_dir / f"설치_{safe_name}.bat"
            try:
                content = generate_setup_bat(dev)
                bat_path.write_text(content, encoding="utf-8-sig")  # BOM for Windows
                saved.append(dev["name"])
            except Exception as e:
                errors.append(f"{dev['name']}: {e}")

        # Open the output folder
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(out_dir)])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(out_dir)])
        else:
            subprocess.Popen(["xdg-open", str(out_dir)])

        msg = (
            f"설치파일 {len(saved)}개 생성 완료!\n\n"
            f"저장 위치:\n{out_dir}\n\n"
            "사용 방법:\n"
            "  1. 생성된 .bat 파일을 USB 또는 공유폴더로 대상 PC에 복사\n"
            "  2. 대상 PC에서 .bat 파일을 마우스 오른쪽 클릭\n"
            "     → '관리자 권한으로 실행'\n"
            "  3. 설치가 완료되면 CMS에서 바로 화면이 보입니다\n"
            "  4. 이후 PC를 켤 때마다 자동으로 실행됩니다"
        )
        if errors:
            msg += f"\n\n오류:\n" + "\n".join(errors)
        QMessageBox.information(self, "설치파일 생성 완료", msg)

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
