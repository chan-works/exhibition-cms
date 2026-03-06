"""
PC 화면 모니터링 패널 — 완전 재작성
- ScreenRefresher: 단일 워커가 모든 타일을 ThreadPoolExecutor로 병렬 fetch
- ServerLaunchWorker: WinRM(C:\\ProgramData) → SSH 순서로 시도
- 스레드 참조를 self에 보관해 GC 방지
"""

import io
import base64
import subprocess
import platform
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QMessageBox,
    QDialog, QTextEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QPixmap, QImage

# ── 상수 ──────────────────────────────────────────────────────────────────────
SCREENSHOT_PORT = 19999
REFRESH_MS      = 3000
FETCH_TIMEOUT   = 2          # 타일당 HTTP 타임아웃(초)

# 원격 PC 고정 경로 — $env:USERPROFILE 는 Copy-Item 시 로컬에서 먼저 확장되므로 사용 금지
REMOTE_DIR = r"C:\ProgramData\ExhibitionCMS"
REMOTE_PY  = r"C:\ProgramData\ExhibitionCMS\screenshot_server.py"


def _find_screenshot_server() -> Path:
    import sys
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "screenshot_server.py")
    candidates.append(Path(sys.executable).parent / "screenshot_server.py")
    candidates.append(Path(__file__).resolve().parent.parent / "screenshot_server.py")
    for p in candidates:
        if p.exists():
            return p
    return candidates[-1]


SCREENSHOT_SERVER_PATH = _find_screenshot_server()


# ── 화면 새로고침 워커 ────────────────────────────────────────────────────────
class ScreenRefresher(QObject):
    """모든 타일 URL을 ThreadPoolExecutor로 병렬 fetch → 결과를 Signal로 emit."""
    result   = Signal(str, bytes)  # dev_id, jpeg_bytes
    error    = Signal(str, str)    # dev_id, error_msg
    finished = Signal()

    def __init__(self, tiles: dict):
        super().__init__()
        self._tiles = dict(tiles)  # {dev_id: url}

    def run(self):
        def fetch(dev_id, url):
            try:
                with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:
                    return dev_id, r.read(), None
            except Exception as e:
                return dev_id, None, str(e)

        n = max(1, min(10, len(self._tiles)))
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(fetch, did, url): did
                    for did, url in self._tiles.items()}
            for f in as_completed(futs):
                dev_id, data, err = f.result()
                if data:
                    self.result.emit(dev_id, data)
                else:
                    self.error.emit(dev_id, err or "알 수 없는 오류")
        self.finished.emit()


# ── 서버 실행 워커 ────────────────────────────────────────────────────────────
class ServerLaunchWorker(QObject):
    """WinRM → SSH 순서로 원격 PC에 screenshot_server.py 배포·실행."""
    log            = Signal(str)
    need_installer = Signal(dict)
    finished       = Signal()

    def __init__(self, devices: list):
        super().__init__()
        self._devices = [
            d for d in devices
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]

    def run(self):
        if not SCREENSHOT_SERVER_PATH.exists():
            self.log.emit(f"[오류] screenshot_server.py 없음:\n  {SCREENSHOT_SERVER_PATH}")
            self.finished.emit()
            return

        for dev in self._devices:
            cfg  = dev.get("config", {})
            host = cfg.get("host", "")
            user = cfg.get("ssh_user", "")
            pw   = cfg.get("ssh_password", "")
            name = dev.get("name", host)
            self.log.emit(f"\n[{name}]  {host}")

            # 1순위: WinRM (Windows CMS에서만)
            if platform.system() == "Windows":
                ok, msg = self._winrm(host, user, pw)
                if ok:
                    self.log.emit(f"  WinRM 성공: {msg}")
                    continue
                self.log.emit(f"  WinRM 실패: {msg}")

            # 2순위: SSH
            if user:
                ok, msg = self._ssh(host, user, pw)
                if ok:
                    self.log.emit(f"  SSH 성공: {msg}")
                    continue
                self.log.emit(f"  SSH 실패: {msg}")
            else:
                self.log.emit("  SSH: 사용자명 미설정")

            self.log.emit("  → '설치파일 생성' 버튼으로 .bat 파일을 만들어 대상 PC에서 실행하세요.")
            self.need_installer.emit(dev)

        self.log.emit("\n완료.")
        self.finished.emit()

    # ── WinRM ────────────────────────────────────────────────────────────────
    def _winrm(self, host: str, user: str, pw: str):
        try:
            # TrustedHosts 등록
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 f"Set-Item WSMan:\\localhost\\Client\\TrustedHosts"
                 f" -Value '{host}' -Force -Concatenate"],
                capture_output=True, timeout=10,
            )

            local   = str(SCREENSHOT_SERVER_PATH).replace("'", "''")
            rdir_ps = REMOTE_DIR.replace("\\", "\\\\")
            rpy_ps  = REMOTE_PY.replace("\\", "\\\\")

            if user and pw:
                pw_s  = pw.replace("'", "''")
                cred  = (f"$pw=ConvertTo-SecureString '{pw_s}' -AsPlainText -Force;"
                         f"$cr=New-Object PSCredential('{user}',$pw);")
                sess  = f"New-PSSession -ComputerName {host} -Credential $cr"
            else:
                cred  = ""
                sess  = f"New-PSSession -ComputerName {host}"

            cmd = (
                f"{cred}"
                f"$s={sess};"
                # 원격 디렉터리 생성 (고정 경로)
                f"Invoke-Command -Session $s -ScriptBlock {{"
                f"New-Item -ItemType Directory -Force -Path '{rdir_ps}'|Out-Null}};"
                # 파일 전송 (고정 경로 — $env:USERPROFILE 사용하지 않음)
                f"Copy-Item -Path '{local}' -Destination '{rpy_ps}' -ToSession $s;"
                # pip 설치 + 자동시작 등록 + 즉시 실행
                f"Invoke-Command -Session $s -ScriptBlock {{"
                f"python -m pip install mss pillow --quiet 2>$null;"
                f"$st=[Environment]::GetFolderPath('Startup');"
                f"\\\"@echo off`nstart `\\\"`\\\" /B pythonw '{rpy_ps}'\\\"\\\" | "
                f"Set-Content \\\"$st\\\\ExhibitionCMS-ScreenServer.bat\\\";"
                f"taskkill /F /IM pythonw.exe 2>$null;"
                f"Start-Process pythonw -ArgumentList '{rpy_ps}' -WindowStyle Hidden;"
                f"'OK'"
                f"}};"
                f"Remove-PSSession $s"
            )

            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True, text=True, timeout=90,
            )
            if r.returncode == 0:
                return True, "서버 시작 완료"
            return False, (r.stderr.strip() or r.stdout.strip())[:300] or "오류"
        except Exception as e:
            return False, str(e)

    # ── SSH ──────────────────────────────────────────────────────────────────
    def _ssh(self, host: str, user: str, pw: str):
        try:
            import paramiko
        except ImportError:
            return False, "paramiko 미설치 (pip install paramiko)"

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=user, password=pw, timeout=10)

            rdir = "C:/ProgramData/ExhibitionCMS"
            rpy  = f"{rdir}/screenshot_server.py"

            # 원격 디렉터리 생성
            _, out, _ = ssh.exec_command(
                f'powershell -NoProfile -ExecutionPolicy Bypass -Command '
                f'"New-Item -ItemType Directory -Force -Path \'{rdir}\' | Out-Null"',
                timeout=10,
            )
            out.read()  # 완료 대기

            # 파일 업로드 (바이너리)
            sftp = ssh.open_sftp()
            sftp.putfo(io.BytesIO(SCREENSHOT_SERVER_PATH.read_bytes()), rpy)
            sftp.close()

            # pip + 즉시 실행
            _, out, _ = ssh.exec_command(
                f'powershell -NoProfile -ExecutionPolicy Bypass -Command '
                f'"python -m pip install mss pillow --quiet 2>$null; '
                f'taskkill /F /IM pythonw.exe 2>$null; '
                f'Start-Process pythonw -ArgumentList \'{rpy}\' -WindowStyle Hidden"',
                timeout=20,
            )
            out.read()  # 완료 대기

            # 자동시작 등록 (별도 명령)
            _, out, _ = ssh.exec_command(
                f'powershell -NoProfile -ExecutionPolicy Bypass -Command '
                f'"$st=[Environment]::GetFolderPath(\'Startup\'); '
                f'Set-Content -Path \\"$st\\\\ExhibitionCMS-ScreenServer.bat\\" '
                f'-Value \'@echo off`nstart `"`" /B pythonw {rpy}\'"',
                timeout=10,
            )
            out.read()

            ssh.close()
            return True, "서버 시작 완료"
        except Exception as e:
            return False, str(e)


# ── 설치파일(.bat) 생성 ────────────────────────────────────────────────────────
def generate_setup_bat(device: dict) -> str:
    """
    대상 PC에서 한 번만 실행하면 되는 자동 설치 .bat 파일 생성.
    - 관리자 권한 자동 요청 (UAC)
    - Python 자동 설치
    - mss/pillow 설치
    - 방화벽 포트 19999 / 5985 / 22 개방
    - WinRM + OpenSSH 활성화
    - 시작프로그램 등록 + 즉시 실행
    """
    if not SCREENSHOT_SERVER_PATH.exists():
        raise FileNotFoundError(f"screenshot_server.py 없음: {SCREENSHOT_SERVER_PATH}")

    b64 = base64.b64encode(SCREENSHOT_SERVER_PATH.read_bytes()).decode("ascii")
    b64_lines = "\n".join(
        f"echo {b64[i:i+76]}>>\"%%TMPB64%%\""
        for i in range(0, len(b64), 76)
    )
    name = device.get("name", "PC")
    host = device.get("config", {}).get("host", "")

    return (
        "@echo off\n"
        "chcp 65001 >nul\n"
        f"title Exhibition CMS 설치 [{name}]\n"
        "\n"
        "REM ── 관리자 권한 자동 요청 ──\n"
        "net session >nul 2>&1\n"
        "if errorlevel 1 (\n"
        "  echo 관리자 권한이 필요합니다. UAC 창을 승인해 주세요...\n"
        "  powershell -NoProfile -Command \"Start-Process '%~f0' -Verb RunAs\"\n"
        "  exit /b\n"
        ")\n"
        "\n"
        "echo.\n"
        "echo  =============================================\n"
        f"echo   Exhibition CMS 설치  [{name}  {host}]\n"
        "echo  =============================================\n"
        "echo.\n"
        "\n"
        "set IDIR=C:\\ProgramData\\ExhibitionCMS\n"
        "set TMPB64=%TEMP%\\cms_b64.tmp\n"
        "mkdir \"%IDIR%\" 2>nul\n"
        "\n"
        "echo [1/5] 서버 파일 생성 중...\n"
        "del \"%TMPB64%\" 2>nul\n"
        + b64_lines + "\n"
        "powershell -NoProfile -Command "
        "\"$b=[Convert]::FromBase64String((gc '%TMPB64%') -join '');"
        "[IO.File]::WriteAllBytes('%IDIR%\\screenshot_server.py',$b)\"\n"
        "del \"%TMPB64%\" 2>nul\n"
        "\n"
        "echo [2/5] Python 확인 중...\n"
        "python --version >nul 2>&1\n"
        "if errorlevel 1 (\n"
        "  echo   Python 없음 - 자동 다운로드 중... (인터넷 필요)\n"
        "  powershell -NoProfile -Command \"Invoke-WebRequest "
        "'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' "
        "-OutFile '%TEMP%\\py_setup.exe'\"\n"
        "  \"%TEMP%\\py_setup.exe\" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0\n"
        "  set \"PATH=C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;%PATH%\"\n"
        "  echo   Python 설치 완료\n"
        ")\n"
        "\n"
        "echo [3/5] 패키지 설치 중... (mss, pillow)\n"
        "python -m pip install mss pillow --quiet --disable-pip-version-check\n"
        "\n"
        "echo [4/5] 방화벽 및 자동시작 설정 중...\n"
        "netsh advfirewall firewall delete rule name=\"ExhibitionCMS-Screen\" >nul 2>&1\n"
        "netsh advfirewall firewall add rule name=\"ExhibitionCMS-Screen\" "
        "protocol=TCP dir=in localport=19999 action=allow >nul 2>&1\n"
        "set \"STARTUP=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\"\n"
        "(echo @echo off& echo start \"\" /B pythonw \"%IDIR%\\screenshot_server.py\")"
        "> \"%STARTUP%\\ExhibitionCMS-ScreenServer.bat\"\n"
        "taskkill /F /IM pythonw.exe >nul 2>&1\n"
        "start \"\" /B pythonw \"%IDIR%\\screenshot_server.py\"\n"
        "\n"
        "echo [5/5] WinRM / SSH 원격 관리 활성화 중...\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \""
        "Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null; "
        "Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force\" >nul 2>&1\n"
        "netsh advfirewall firewall delete rule name=\"WinRM-HTTP\" >nul 2>&1\n"
        "netsh advfirewall firewall add rule name=\"WinRM-HTTP\" "
        "protocol=TCP dir=in localport=5985 action=allow >nul 2>&1\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \""
        "$cap=Get-WindowsCapability -Online|Where-Object Name -like 'OpenSSH.Server*';"
        "if($cap -and $cap.State -ne 'Installed'){"
        "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0|Out-Null};"
        "Start-Service sshd -ErrorAction SilentlyContinue;"
        "Set-Service -Name sshd -StartupType Automatic\" >nul 2>&1\n"
        "netsh advfirewall firewall delete rule name=\"OpenSSH-Server-In-TCP\" >nul 2>&1\n"
        "netsh advfirewall firewall add rule name=\"OpenSSH-Server-In-TCP\" "
        "protocol=TCP dir=in localport=22 action=allow >nul 2>&1\n"
        "\n"
        "echo.\n"
        "echo  =============================================\n"
        "echo   설치 완료!\n"
        "echo   포트: 19999(화면)  5985(WinRM)  22(SSH)\n"
        "echo   이후 PC를 켤 때마다 자동으로 실행됩니다.\n"
        "echo  =============================================\n"
        "echo.\n"
        "pause\n"
    )


# ── 타일 위젯 ─────────────────────────────────────────────────────────────────
class ScreenTile(QFrame):
    start_server = Signal(dict)   # 서버 시작 요청

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self.device    = device
        self.device_id = str(device["id"])
        host           = device.get("config", {}).get("host", "")
        self.url       = f"http://{host}:{SCREENSHOT_PORT}/screenshot"

        self.setObjectName("card")
        self.setMinimumSize(280, 210)
        self.setMaximumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("""
            QFrame#card {
                background:#16213e; border:1px solid #0f3460; border-radius:8px;
            }
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        # 헤더
        hdr = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet("color:#555; font-size:10px;")
        hdr.addWidget(self._dot)

        name_lbl = QLabel(self.device["name"])
        name_lbl.setStyleSheet("font-weight:bold; color:#e0e0e0; font-size:13px;")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        host = self.device.get("config", {}).get("host", "")
        ip_lbl = QLabel(host)
        ip_lbl.setStyleSheet("color:#555; font-size:11px;")
        hdr.addWidget(ip_lbl)
        layout.addLayout(hdr)

        # 화면 영역
        self._screen = QLabel("연결 대기 중...")
        self._screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen.setMinimumHeight(140)
        self._screen.setStyleSheet(
            "background:#0a0a15; border-radius:4px; color:#404050; font-size:12px;"
        )
        layout.addWidget(self._screen)

        # 푸터
        footer = QHBoxLayout()
        self._time = QLabel("")
        self._time.setStyleSheet("color:#404050; font-size:10px;")
        footer.addWidget(self._time)
        footer.addStretch()

        self._start_btn = QPushButton("서버 시작")
        self._start_btn.setFixedSize(72, 24)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background:#1a4a80; color:white; border:none;
                border-radius:3px; font-size:11px;
            }
            QPushButton:hover { background:#2a5a90; }
            QPushButton:disabled { background:#333; color:#666; }
        """)
        self._start_btn.setVisible(False)
        self._start_btn.clicked.connect(lambda: self.start_server.emit(self.device))
        footer.addWidget(self._start_btn)
        layout.addLayout(footer)

    # ── 상태 업데이트 ─────────────────────────────────────────────────────────
    def show_image(self, jpeg: bytes):
        img = QImage()
        img.loadFromData(jpeg, "JPEG")
        if not img.isNull():
            pm = QPixmap.fromImage(img).scaledToWidth(
                max(1, self._screen.width() - 4),
                Qt.TransformationMode.SmoothTransformation,
            )
            self._screen.setPixmap(pm)
            self._screen.setText("")
        self._dot.setStyleSheet("color:#4CAF50; font-size:10px;")
        self._start_btn.setVisible(False)
        self._time.setText(datetime.now().strftime("%H:%M:%S"))

    def show_error(self, msg: str):
        self._screen.setPixmap(QPixmap())
        ml = msg.lower()
        if "refused" in ml or "10061" in msg:
            self._screen.setText("서버 미실행\n아래 '서버 시작' 버튼을 누르세요")
            self._start_btn.setVisible(True)
        elif "timed out" in ml or "timeout" in ml:
            self._screen.setText("응답 없음\n(네트워크 또는 IP 확인)")
            self._start_btn.setVisible(False)
        else:
            self._screen.setText(f"연결 실패\n{msg[:60]}")
            self._start_btn.setVisible(True)
        self._dot.setStyleSheet("color:#555; font-size:10px;")
        self._time.setText(datetime.now().strftime("%H:%M:%S"))

    def show_starting(self):
        self._screen.setText("서버 시작 중...")
        self._start_btn.setEnabled(False)
        self._start_btn.setText("시작 중...")

    def reset_start_btn(self):
        self._start_btn.setEnabled(True)
        self._start_btn.setText("서버 시작")


# ── 메인 패널 ─────────────────────────────────────────────────────────────────
class MonitorPanel(QWidget):
    def __init__(self, db, current_user, parent=None):
        super().__init__(parent)
        self.db           = db
        self.current_user = current_user
        self._tiles       = {}     # dev_id → ScreenTile
        self._refresher   = None   # (QThread, ScreenRefresher)  — 한 번에 하나만
        self._launchers   = {}     # dev_id → (QThread, ServerLaunchWorker)
        self._auto_launch = None   # (QThread, ServerLaunchWorker) for 자동시작
        self._timer       = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._build_ui()
        self._load_devices()

    # ── UI 구성 ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 헤더
        hdr = QHBoxLayout()
        title = QLabel("PC 화면 모니터링")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#e94560;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._gen_btn = QPushButton("설치파일 생성")
        self._gen_btn.setFixedHeight(30)
        self._gen_btn.setToolTip("각 PC에서 한 번만 실행하면 되는 .bat 파일 생성")
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;border:none;"
            "border-radius:4px;padding:0 12px;font-size:12px;}"
            "QPushButton:hover{background:#388e3c;}"
        )
        self._gen_btn.clicked.connect(self._generate_installers)
        hdr.addWidget(self._gen_btn)

        self._auto_btn = QPushButton("서버 자동 시작")
        self._auto_btn.setFixedHeight(30)
        self._auto_btn.setToolTip("WinRM 또는 SSH가 설정된 PC에 서버 자동 배포")
        self._auto_btn.setStyleSheet(
            "QPushButton{background:#1a4a80;color:white;border:none;"
            "border-radius:4px;padding:0 12px;font-size:12px;}"
            "QPushButton:hover{background:#2a5a90;}"
            "QPushButton:disabled{background:#333;color:#666;}"
        )
        self._auto_btn.clicked.connect(self._auto_start_all)
        hdr.addWidget(self._auto_btn)

        self._toggle_btn = QPushButton("모니터링 시작")
        self._toggle_btn.setObjectName("primary")
        self._toggle_btn.setFixedHeight(30)
        self._toggle_btn.clicked.connect(self._toggle)
        hdr.addWidget(self._toggle_btn)

        root.addLayout(hdr)

        hint = QLabel(
            f"관리 PC에서 screenshot_server.py 를 실행하세요. (포트: {SCREENSHOT_PORT})"
        )
        hint.setStyleSheet("color:#a0b0c0; font-size:12px;")
        root.addWidget(hint)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_w = QWidget()
        self._grid   = QGridLayout(self._grid_w)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_w)
        root.addWidget(scroll)

    # ── 디바이스 로드 ─────────────────────────────────────────────────────────
    def _load_devices(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tiles.clear()

        devices = [
            d for d in self.db.get_all_devices()
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]

        if not devices:
            lbl = QLabel("컴퓨터 디바이스가 없습니다.\n디바이스 관리에서 PC를 추가하세요.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:#606070; font-size:14px; padding:40px;")
            self._grid.addWidget(lbl, 0, 0)
            return

        cols = 3
        for i, dev in enumerate(devices):
            tile = ScreenTile(dev)
            tile.start_server.connect(self._start_server_tile)
            self._tiles[str(dev["id"])] = tile
            self._grid.addWidget(tile, i // cols, i % cols)

    # ── 모니터링 토글 ─────────────────────────────────────────────────────────
    def _toggle(self):
        if self._timer.isActive():
            self._timer.stop()
            self._toggle_btn.setText("모니터링 시작")
            self._toggle_btn.setStyleSheet("")
        else:
            self._load_devices()
            self._refresh_all()
            self._timer.start(REFRESH_MS)
            self._toggle_btn.setText("모니터링 중지")
            self._toggle_btn.setStyleSheet("background-color:#8b2222;")

    # ── 화면 새로고침 ─────────────────────────────────────────────────────────
    def _refresh_all(self):
        # 이전 refresher가 아직 실행 중이면 건너뜀
        if self._refresher and self._refresher[0].isRunning():
            return
        if not self._tiles:
            return

        tiles = {did: tile.url for did, tile in self._tiles.items()}
        thread = QThread()
        worker = ScreenRefresher(tiles)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._on_image)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._refresher = (thread, worker)  # GC 방지
        thread.start()

    def _on_image(self, dev_id: str, data: bytes):
        if dev_id in self._tiles:
            self._tiles[dev_id].show_image(data)

    def _on_error(self, dev_id: str, msg: str):
        if dev_id in self._tiles:
            self._tiles[dev_id].show_error(msg)

    # ── 타일 서버 시작 ────────────────────────────────────────────────────────
    def _start_server_tile(self, device: dict):
        dev_id = str(device["id"])
        tile   = self._tiles.get(dev_id)
        if tile:
            tile.show_starting()

        _failed = []

        def on_log(msg):
            pass  # 개별 타일 시작은 로그 다이얼로그 없이 처리

        def on_need(dev):
            _failed.append(dev)

        def on_done():
            if tile:
                tile.reset_start_btn()
            if _failed:
                reply = QMessageBox.question(
                    self, "자동 시작 실패",
                    f"[{device['name']}] WinRM/SSH 연결 불가\n\n"
                    "설치파일(.bat)을 생성해 대상 PC에서 한 번 실행하면\n"
                    "이후 자동으로 동작합니다.\n\n지금 생성하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._save_installer(device)
            else:
                # 성공 — 2초 후 화면 갱신
                QTimer.singleShot(2000, self._refresh_all)

        worker = ServerLaunchWorker([device])
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(on_log)
        worker.need_installer.connect(on_need)
        worker.finished.connect(on_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._launchers[dev_id] = (thread, worker)  # GC 방지
        thread.start()

    # ── 전체 서버 자동 시작 ───────────────────────────────────────────────────
    def _auto_start_all(self):
        devices = [
            d for d in self.db.get_all_devices()
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]
        if not devices:
            QMessageBox.warning(self, "PC 없음", "등록된 컴퓨터 디바이스가 없습니다.")
            return

        self._auto_btn.setEnabled(False)
        self._auto_btn.setText("시작 중...")

        # 로그 다이얼로그
        dlg = QDialog(self)
        dlg.setWindowTitle("서버 자동 시작")
        dlg.resize(540, 380)
        dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        dlg_layout = QVBoxLayout(dlg)

        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setStyleSheet(
            "background:#0a0a15; color:#c0d0e0; font-family:monospace; font-size:12px;"
        )
        dlg_layout.addWidget(log_box)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dlg.accept)
        dlg_layout.addWidget(close_btn)

        def on_need(dev):
            btn = QPushButton(f"설치파일 생성: {dev['name']}")
            btn.setStyleSheet(
                "QPushButton{background:#2e7d32;color:white;border:none;"
                "border-radius:4px;padding:4px 10px;margin:2px;}"
                "QPushButton:hover{background:#388e3c;}"
            )
            btn.clicked.connect(lambda _, d=dev: self._save_installer(d))
            dlg_layout.insertWidget(dlg_layout.count() - 1, btn)

        def on_done():
            self._auto_btn.setEnabled(True)
            self._auto_btn.setText("서버 자동 시작")

        worker = ServerLaunchWorker(devices)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(log_box.append)
        worker.need_installer.connect(on_need)
        worker.finished.connect(on_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._auto_launch = (thread, worker)  # GC 방지
        thread.start()
        dlg.exec()

    # ── 설치파일 생성 (전체) ──────────────────────────────────────────────────
    def _generate_installers(self):
        devices = [
            d for d in self.db.get_all_devices()
            if d.get("device_type") == "computer"
            and d.get("config", {}).get("host")
        ]
        if not devices:
            QMessageBox.warning(self, "PC 없음", "등록된 컴퓨터 디바이스가 없습니다.")
            return

        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        out_dir = desktop / "ExhibitionCMS-설치파일"
        out_dir.mkdir(exist_ok=True)

        saved, errors = [], []
        for dev in devices:
            safe = dev["name"].replace(" ", "_").replace("/", "-")
            path = out_dir / f"설치_{safe}.bat"
            try:
                path.write_text(generate_setup_bat(dev), encoding="utf-8-sig")
                saved.append(dev["name"])
            except Exception as e:
                errors.append(f"{dev['name']}: {e}")

        self._open_folder(out_dir)
        msg = (
            f"설치파일 {len(saved)}개 생성!\n\n저장 위치:\n{out_dir}\n\n"
            "사용 방법:\n"
            "  1. .bat 파일을 USB로 대상 PC에 복사\n"
            "  2. 마우스 오른쪽 클릭 → '관리자 권한으로 실행'\n"
            "  3. 완료되면 CMS에서 화면이 보입니다"
        )
        if errors:
            msg += "\n\n오류:\n" + "\n".join(errors)
        QMessageBox.information(self, "완료", msg)

    # ── 설치파일 생성 (단일) ──────────────────────────────────────────────────
    def _save_installer(self, device: dict):
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        out_dir = desktop / "ExhibitionCMS-설치파일"
        out_dir.mkdir(exist_ok=True)
        safe = device["name"].replace(" ", "_").replace("/", "-")
        path = out_dir / f"설치_{safe}.bat"
        try:
            path.write_text(generate_setup_bat(device), encoding="utf-8-sig")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
            return
        self._open_folder(out_dir)
        QMessageBox.information(
            self, "설치파일 생성",
            f"저장: {path}\n\n"
            "대상 PC에서 마우스 오른쪽 클릭 → '관리자 권한으로 실행'"
        )

    @staticmethod
    def _open_folder(path: Path):
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(path)])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ── 패널 전환 시 호출 ─────────────────────────────────────────────────────
    def refresh(self):
        self._load_devices()

    def stop(self):
        self._timer.stop()
