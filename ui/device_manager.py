import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QMessageBox, QHeaderView, QTabWidget,
    QSpinBox, QTextEdit, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal

DEVICE_TYPES = {
    "pjlink":   "PJLink (프로젝터/디스플레이)",
    "computer": "컴퓨터 (WOL/원격종료)",
    "artnet":   "ArtNet (DMX 네트워크)",
    "usb_dmx":  "USB DMX (ENTTEC)",
    "osc":      "OSC 신호",
}


def _scene_to_str(scene: dict) -> str:
    if not scene:
        return ""
    return ", ".join(f"ch{k}={v}" for k, v in sorted(scene.items(), key=lambda x: int(x[0])))


def _str_to_scene(text: str) -> dict:
    scene = {}
    for part in text.split(","):
        part = part.strip()
        if "=" in part:
            left, right = part.split("=", 1)
            ch = left.strip().lower().replace("ch", "").replace("channel", "")
            try:
                scene[int(ch)] = max(0, min(255, int(right.strip())))
            except ValueError:
                pass
    return scene


class PJLinkConfigWidget(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setSpacing(8)
        self.host = QLineEdit(cfg.get("host", ""))
        self.host.setPlaceholderText("192.168.1.100")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(cfg.get("port", 4352)))
        self.password = QLineEdit(cfg.get("password", ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("비워두면 인증 없음")
        layout.addRow("IP 주소 *", self.host)
        layout.addRow("포트", self.port)
        layout.addRow("비밀번호", self.password)

    def get_config(self):
        return {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "password": self.password.text(),
        }

    def validate(self):
        return bool(self.host.text().strip()), "IP 주소를 입력하세요"


class ComputerConfigWidget(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setSpacing(8)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.host = QLineEdit(cfg.get("host", ""))
        self.host.setPlaceholderText("192.168.1.10 또는 HOSTNAME")
        self.host.editingFinished.connect(self._auto_fill_broadcast)
        layout.addRow("IP/호스트명 *", self.host)

        self.mac = QLineEdit(cfg.get("mac", ""))
        self.mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        layout.addRow("MAC 주소 (WOL용)", self.mac)

        # Broadcast row with auto-fill button
        bc_row = QHBoxLayout()
        bc_row.setSpacing(6)
        self.broadcast = QLineEdit(cfg.get("broadcast", "255.255.255.255"))
        bc_row.addWidget(self.broadcast)
        auto_bc_btn = QPushButton("자동")
        auto_bc_btn.setFixedWidth(50)
        auto_bc_btn.setFixedHeight(30)
        auto_bc_btn.setToolTip("IP에서 서브넷 브로드캐스트 자동 계산")
        auto_bc_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a4a80; color: white;
                border: none; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background-color: #2a5a90; }
        """)
        auto_bc_btn.clicked.connect(self._auto_fill_broadcast)
        bc_row.addWidget(auto_bc_btn)
        layout.addRow("브로드캐스트 IP", bc_row)

        self.wol_port = QSpinBox()
        self.wol_port.setRange(1, 65535)
        self.wol_port.setValue(int(cfg.get("wol_port", 9)))
        layout.addRow("WOL 포트", self.wol_port)

        self.shutdown_method = QComboBox()
        self.shutdown_method.addItem("Windows (net shutdown)", "wmi")
        self.shutdown_method.addItem("SSH", "ssh")
        self.shutdown_method.addItem("로컬 시스템", "local")
        idx = self.shutdown_method.findData(cfg.get("shutdown_method", "wmi"))
        if idx >= 0:
            self.shutdown_method.setCurrentIndex(idx)
        layout.addRow("종료 방식", self.shutdown_method)

        self.ssh_user = QLineEdit(cfg.get("ssh_user", ""))
        self.ssh_password = QLineEdit(cfg.get("ssh_password", ""))
        self.ssh_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("SSH 사용자", self.ssh_user)
        layout.addRow("SSH 비밀번호", self.ssh_password)

    def _auto_fill_broadcast(self):
        ip = self.host.text().strip()
        if not ip or not ip[0].isdigit():
            return
        try:
            import ipaddress
            # Try /24 first, then check if it changes
            net24 = ipaddress.IPv4Network(f"{ip}/24", strict=False)
            self.broadcast.setText(str(net24.broadcast_address))
        except Exception:
            pass

    def get_config(self):
        return {
            "host": self.host.text().strip(),
            "mac": self.mac.text().strip(),
            "broadcast": self.broadcast.text().strip() or "255.255.255.255",
            "wol_port": self.wol_port.value(),
            "shutdown_method": self.shutdown_method.currentData(),
            "ssh_user": self.ssh_user.text().strip(),
            "ssh_password": self.ssh_password.text(),
        }

    def validate(self):
        return bool(self.host.text().strip()), "IP/호스트명을 입력하세요"


class ArtNetConfigWidget(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setSpacing(8)
        self.host = QLineEdit(cfg.get("host", ""))
        self.host.setPlaceholderText("192.168.1.200 또는 255.255.255.255")
        self.universe = QSpinBox()
        self.universe.setRange(0, 15)
        self.universe.setValue(int(cfg.get("universe", 0)))
        self.subnet = QSpinBox()
        self.subnet.setRange(0, 15)
        self.subnet.setValue(int(cfg.get("subnet", 0)))
        self.net = QSpinBox()
        self.net.setRange(0, 127)
        self.net.setValue(int(cfg.get("net", 0)))

        scene_on_raw = cfg.get("scene_on", {})
        if isinstance(scene_on_raw, str):
            try:
                scene_on_raw = json.loads(scene_on_raw)
            except Exception:
                scene_on_raw = {}
        self.scene_on = QLineEdit(_scene_to_str(scene_on_raw))
        self.scene_on.setPlaceholderText("예: ch1=255, ch2=128, ch3=0")

        layout.addRow("IP/브로드캐스트 *", self.host)
        layout.addRow("Universe (0-15)", self.universe)
        layout.addRow("Subnet (0-15)", self.subnet)
        layout.addRow("Net (0-127)", self.net)
        layout.addRow("ON 씬 (채널=값)", self.scene_on)

        hint = QLabel("OFF는 자동으로 블랙아웃(모든 채널 0) 처리됩니다")
        hint.setStyleSheet("color: #606070; font-size: 11px;")
        layout.addRow("", hint)

    def get_config(self):
        return {
            "host": self.host.text().strip(),
            "universe": self.universe.value(),
            "subnet": self.subnet.value(),
            "net": self.net.value(),
            "scene_on": _str_to_scene(self.scene_on.text()),
        }

    def validate(self):
        return bool(self.host.text().strip()), "IP 주소를 입력하세요"


class UsbDmxConfigWidget(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self._populate_ports(cfg.get("port", ""))

        self.universe = QSpinBox()
        self.universe.setRange(0, 15)
        self.universe.setValue(int(cfg.get("universe", 0)))

        scene_on_raw = cfg.get("scene_on", {})
        if isinstance(scene_on_raw, str):
            try:
                scene_on_raw = json.loads(scene_on_raw)
            except Exception:
                scene_on_raw = {}
        self.scene_on = QLineEdit(_scene_to_str(scene_on_raw))
        self.scene_on.setPlaceholderText("예: ch1=255, ch2=128, ch3=0")

        layout.addRow("시리얼 포트 *", self.port_combo)
        layout.addRow("Universe", self.universe)
        layout.addRow("ON 씬 (채널=값)", self.scene_on)

        hint = QLabel("Windows: COM3, COM4 등 / Mac/Linux: /dev/ttyUSB0 등")
        hint.setStyleSheet("color: #606070; font-size: 11px;")
        layout.addRow("", hint)

    def _populate_ports(self, current):
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        self.port_combo.addItems(ports)
        if current:
            idx = self.port_combo.findText(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
            else:
                self.port_combo.setCurrentText(current)

    def get_config(self):
        return {
            "port": self.port_combo.currentText().strip(),
            "universe": self.universe.value(),
            "scene_on": _str_to_scene(self.scene_on.text()),
        }

    def validate(self):
        return bool(self.port_combo.currentText().strip()), "포트를 선택하세요"


class OscConfigWidget(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setSpacing(8)
        self.host = QLineEdit(cfg.get("host", ""))
        self.host.setPlaceholderText("192.168.1.50")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(cfg.get("port", 8000)))
        self.address = QLineEdit(cfg.get("address", "/exhibition"))
        self.address.setPlaceholderText("/exhibition/zone1")
        self.on_value = QLineEdit(str(cfg.get("on_value", "1")))
        self.off_value = QLineEdit(str(cfg.get("off_value", "0")))
        layout.addRow("IP 주소 *", self.host)
        layout.addRow("포트", self.port)
        layout.addRow("OSC 주소", self.address)
        layout.addRow("ON 값", self.on_value)
        layout.addRow("OFF 값", self.off_value)

    def get_config(self):
        def try_num(s):
            try:
                return int(s)
            except ValueError:
                try:
                    return float(s)
                except ValueError:
                    return s

        return {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "address": self.address.text().strip() or "/exhibition",
            "on_value": try_num(self.on_value.text().strip()),
            "off_value": try_num(self.off_value.text().strip()),
        }

    def validate(self):
        return bool(self.host.text().strip()), "IP 주소를 입력하세요"


CONFIG_WIDGETS = {
    "pjlink":   PJLinkConfigWidget,
    "computer": ComputerConfigWidget,
    "artnet":   ArtNetConfigWidget,
    "usb_dmx":  UsbDmxConfigWidget,
    "osc":      OscConfigWidget,
}


class DeviceDialog(QDialog):
    def __init__(self, db, parent=None, device=None):
        super().__init__(parent)
        self.db = db
        self.device = device
        self.config_widget = None
        self.setWindowTitle("디바이스 편집" if device else "새 디바이스 추가")
        self.setMinimumSize(560, 600)
        self.resize(580, 680)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()
        if device:
            self._populate(device)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable content area ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        # Basic info form
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("디바이스 이름")
        self.name_input.setFixedHeight(34)
        form.addRow("이름 *", self.name_input)

        self.zone_combo = QComboBox()
        self.zone_combo.setFixedHeight(34)
        zones = self.db.get_all_zones()
        self.zone_combo.addItem("(구역 없음)", None)
        for z in zones:
            self.zone_combo.addItem(z["name"], z["id"])
        form.addRow("구역", self.zone_combo)

        self.enabled_check = QCheckBox("활성화")
        self.enabled_check.setChecked(True)
        form.addRow("", self.enabled_check)

        layout.addLayout(form)

        # Type + scan button (separate row, not in form)
        type_sep = QFrame()
        type_sep.setFrameShape(QFrame.Shape.HLine)
        type_sep.setStyleSheet("color: #0f3460; margin: 4px 0;")
        layout.addWidget(type_sep)

        type_section = QVBoxLayout()
        type_section.setSpacing(6)

        type_lbl = QLabel("디바이스 타입 *")
        type_lbl.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        type_section.addWidget(type_lbl)

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self.type_combo = QComboBox()
        self.type_combo.setFixedHeight(34)
        for key, label in DEVICE_TYPES.items():
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._on_type_change)
        self.type_combo.currentIndexChanged.connect(self._update_wol_btn)
        type_row.addWidget(self.type_combo, 1)

        self.scan_net_btn = QPushButton("🔍 자동 감지")
        self.scan_net_btn.setFixedHeight(34)
        self.scan_net_btn.setFixedWidth(110)
        self.scan_net_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a4a80; color: white;
                border: none; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2a5a90; }
        """)
        self.scan_net_btn.clicked.connect(self._open_network_scan)
        type_row.addWidget(self.scan_net_btn)
        type_section.addLayout(type_row)
        layout.addLayout(type_section)

        # Device config section
        config_sep = QFrame()
        config_sep.setFrameShape(QFrame.Shape.HLine)
        config_sep.setStyleSheet("color: #0f3460; margin: 4px 0;")
        layout.addWidget(config_sep)

        self.config_label = QLabel("디바이스 설정")
        self.config_label.setStyleSheet("font-weight: bold; color: #c0d0e0; font-size: 13px;")
        layout.addWidget(self.config_label)

        self.config_container = QVBoxLayout()
        self.config_container.setSpacing(0)
        layout.addLayout(self.config_container)
        layout.addStretch()

        content.setLayout(layout)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── Fixed bottom button bar ──────────────────────────────────────────
        btn_bar = QFrame()
        btn_bar.setFixedHeight(56)
        btn_bar.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-top: 1px solid #0f3460;
            }
        """)
        btn_bar_layout = QVBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(16, 8, 16, 8)
        btn_bar_layout.setSpacing(0)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # WOL buttons (computer only)
        self.wol_diag_btn = QPushButton("WOL 진단")
        self.wol_diag_btn.setFixedHeight(36)
        self.wol_diag_btn.setToolTip("WOL 전송 방법 전체를 시도하고 결과를 확인합니다")
        self.wol_diag_btn.clicked.connect(self._wol_diagnose)
        self.wol_diag_btn.setVisible(False)
        btn_row.addWidget(self.wol_diag_btn)

        self.wol_enable_btn = QPushButton("WOL 원격 활성화")
        self.wol_enable_btn.setFixedHeight(36)
        self.wol_enable_btn.setObjectName("success")
        self.wol_enable_btn.setToolTip("PC가 켜진 상태에서 WOL 자동 활성화")
        self.wol_enable_btn.clicked.connect(self._wol_enable_remote)
        self.wol_enable_btn.setVisible(False)
        btn_row.addWidget(self.wol_enable_btn)

        self.test_btn = QPushButton("연결 테스트")
        self.test_btn.setFixedHeight(36)
        self.test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(self.test_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setFixedWidth(72)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("저장")
        save_btn.setObjectName("primary")
        save_btn.setFixedHeight(36)
        save_btn.setFixedWidth(72)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        btn_bar_layout.addLayout(btn_row)
        root.addWidget(btn_bar)

        self._on_type_change()

    def _populate(self, device):
        self.name_input.setText(device["name"])
        idx = self.type_combo.findData(device["device_type"])
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        zone_idx = self.zone_combo.findData(device.get("zone_id"))
        if zone_idx >= 0:
            self.zone_combo.setCurrentIndex(zone_idx)
        self.enabled_check.setChecked(bool(device.get("is_enabled", 1)))

    def _update_wol_btn(self):
        dtype = self.type_combo.currentData()
        is_computer = dtype == "computer"
        self.wol_diag_btn.setVisible(is_computer)
        self.wol_enable_btn.setVisible(is_computer)

    def _open_network_scan(self):
        from ui.network_scan_dialog import NetworkScanDialog
        dtype = self.type_combo.currentData()
        filter_map = {"pjlink": "pjlink", "computer": "computer"}
        dlg = NetworkScanDialog(self, device_type_filter=filter_map.get(dtype))
        dlg.device_selected.connect(self._on_device_selected)
        dlg.exec()

    def _on_device_selected(self, dtype, ip, mac):
        if self.config_widget:
            if hasattr(self.config_widget, "host"):
                self.config_widget.host.setText(ip)
            if hasattr(self.config_widget, "mac") and mac:
                self.config_widget.mac.setText(mac)
        # Switch type if needed
        idx = self.type_combo.findData(dtype)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

    def _on_type_change(self):
        dtype = self.type_combo.currentData()
        if self.config_widget:
            self.config_container.removeWidget(self.config_widget)
            self.config_widget.deleteLater()
            self.config_widget = None

        cfg = {}
        if self.device and self.device["device_type"] == dtype:
            cfg = self.device.get("config", {})
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}

        widget_cls = CONFIG_WIDGETS.get(dtype)
        if widget_cls:
            self.config_widget = widget_cls(cfg)
            self.config_container.addWidget(self.config_widget)

    def _test_connection(self):
        if not self.config_widget:
            return
        valid, msg = self.config_widget.validate()
        if not valid:
            QMessageBox.warning(self, "오류", msg)
            return
        cfg = self.config_widget.get_config()
        dtype = self.type_combo.currentData()

        try:
            if dtype == "pjlink":
                from controllers.pjlink_controller import PJLinkController
                ctrl = PJLinkController(cfg["host"], cfg["port"], cfg.get("password") or None)
                ok, msg = ctrl.test_connection()
            elif dtype == "computer":
                from controllers.computer_controller import ComputerController
                ctrl = ComputerController(cfg["host"])
                ok, msg = ctrl.test_ping()
            elif dtype == "artnet":
                from controllers.artnet_controller import ArtNetController
                ctrl = ArtNetController(cfg["host"], cfg["universe"], cfg["subnet"], cfg["net"])
                ok, msg = ctrl.test_connection()
            elif dtype == "usb_dmx":
                from controllers.usb_dmx_controller import UsbDmxController
                ctrl = UsbDmxController(cfg["port"])
                ok, msg = ctrl.test_connection()
            elif dtype == "osc":
                from controllers.osc_controller import OscController
                ctrl = OscController(cfg["host"], cfg["port"])
                ok, msg = ctrl.test_connection()
            else:
                ok, msg = False, "알 수 없는 타입"
        except Exception as e:
            ok, msg = False, str(e)

        if ok:
            QMessageBox.information(self, "연결 성공", msg)
        else:
            QMessageBox.critical(self, "연결 실패", msg)

    def _wol_diagnose(self):
        if not self.config_widget:
            return
        cfg = self.config_widget.get_config()
        from controllers.computer_controller import ComputerController
        ctrl = ComputerController(
            host=cfg.get("host", ""),
            mac=cfg.get("mac", ""),
            broadcast=cfg.get("broadcast", "255.255.255.255"),
            wol_port=int(cfg.get("wol_port", 9)),
        )
        result = ctrl.wol_diagnose()
        QMessageBox.information(self, "WOL 진단 결과", result)

    def _wol_enable_remote(self):
        if not self.config_widget:
            return
        cfg = self.config_widget.get_config()
        host = cfg.get("host", "")
        if not host:
            QMessageBox.warning(self, "오류", "IP 주소를 먼저 입력하세요.")
            return
        reply = QMessageBox.question(
            self, "WOL 원격 설정",
            f"'{host}' PC의 WOL(Wake on Magic Packet)을 원격으로 활성화합니다.\n\n"
            "※ 대상 PC가 현재 켜져 있어야 합니다.\n"
            "※ SSH 또는 Windows 원격 PowerShell 권한이 필요합니다.\n\n"
            "계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from controllers.computer_controller import ComputerController
        ctrl = ComputerController(
            host=host,
            mac=cfg.get("mac", ""),
            shutdown_method=cfg.get("shutdown_method", "wmi"),
            ssh_user=cfg.get("ssh_user", ""),
            ssh_password=cfg.get("ssh_password", ""),
        )
        ok, msg = ctrl.enable_wol_remote()
        if ok:
            QMessageBox.information(self, "WOL 설정 완료", msg)
        else:
            QMessageBox.critical(self, "WOL 설정 실패", msg)

    def _save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "오류", "이름을 입력하세요.")
            return
        if self.config_widget:
            valid, msg = self.config_widget.validate()
            if not valid:
                QMessageBox.warning(self, "오류", msg)
                return
        self.accept()

    def get_data(self):
        cfg = self.config_widget.get_config() if self.config_widget else {}
        return {
            "name": self.name_input.text().strip(),
            "zone_id": self.zone_combo.currentData(),
            "device_type": self.type_combo.currentData(),
            "config": cfg,
            "is_enabled": 1 if self.enabled_check.isChecked() else 0,
        }


class DeviceManager(QWidget):
    devices_changed = Signal()

    def __init__(self, db, current_user, scheduler=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self.scheduler = scheduler
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("디바이스 관리")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        header.addWidget(title)
        header.addStretch()

        if self.current_user["role"] in ("admin", "operator"):
            add_btn = QPushButton("+ 디바이스 추가")
            add_btn.setObjectName("primary")
            add_btn.clicked.connect(self._add_device)
            header.addWidget(add_btn)

        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["이름", "타입", "구역", "IP/포트", "상태", "작업"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def refresh(self):
        devices = self.db.get_all_devices()
        self.table.setRowCount(len(devices))
        for i, dev in enumerate(devices):
            cfg = dev.get("config", {})
            self.table.setItem(i, 0, QTableWidgetItem(dev["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(DEVICE_TYPES.get(dev["device_type"], dev["device_type"])))
            self.table.setItem(i, 2, QTableWidgetItem(dev.get("zone_name") or "-"))
            host_str = cfg.get("host", cfg.get("port", "-")) if isinstance(cfg, dict) else "-"
            self.table.setItem(i, 3, QTableWidgetItem(str(host_str)))
            status_item = QTableWidgetItem("활성" if dev.get("is_enabled", 1) else "비활성")
            status_item.setForeground(
                Qt.GlobalColor.green if dev.get("is_enabled", 1) else Qt.GlobalColor.red
            )
            self.table.setItem(i, 4, status_item)

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            on_btn = QPushButton("ON")
            on_btn.setObjectName("success")
            on_btn.setFixedHeight(26)
            on_btn.clicked.connect(lambda checked, d=dev: self._manual_trigger(d, "on"))
            btn_layout.addWidget(on_btn)

            off_btn = QPushButton("OFF")
            off_btn.setObjectName("danger")
            off_btn.setFixedHeight(26)
            off_btn.clicked.connect(lambda checked, d=dev: self._manual_trigger(d, "off"))
            btn_layout.addWidget(off_btn)

            if dev.get("device_type") == "computer":
                screen_btn = QPushButton("🖥 화면")
                screen_btn.setFixedHeight(26)
                screen_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1a4a80;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 0 6px;
                        font-size: 12px;
                    }
                    QPushButton:hover { background-color: #2a5a90; }
                """)
                screen_btn.clicked.connect(lambda checked, d=dev: self._open_screen_viewer(d))
                btn_layout.addWidget(screen_btn)

            if self.current_user["role"] in ("admin", "operator"):
                edit_btn = QPushButton("편집")
                edit_btn.setFixedHeight(26)
                edit_btn.clicked.connect(lambda checked, d=dev: self._edit_device(d))
                btn_layout.addWidget(edit_btn)

            if self.current_user["role"] == "admin":
                del_btn = QPushButton("삭제")
                del_btn.setObjectName("danger")
                del_btn.setFixedHeight(26)
                del_btn.clicked.connect(lambda checked, d=dev: self._delete_device(d))
                btn_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 5, btn_widget)
            self.table.setRowHeight(i, 40)

    def _open_screen_viewer(self, device):
        from ui.screen_viewer import ScreenViewerDialog
        dlg = ScreenViewerDialog(device, self)
        dlg.show()

    def _manual_trigger(self, device, action):
        if not self.scheduler:
            QMessageBox.warning(self, "오류", "스케줄러가 초기화되지 않았습니다.")
            return
        ok, msg = self.scheduler.run_device_now(device, action)
        if ok:
            QMessageBox.information(self, "완료", f"[{device['name']}] {action.upper()} 실행 완료\n{msg}")
        else:
            QMessageBox.critical(self, "실패", f"[{device['name']}] {action.upper()} 실패\n{msg}")

    def _add_device(self):
        dlg = DeviceDialog(self.db, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.db.create_device(data["zone_id"], data["name"], data["device_type"], data["config"])
            self.refresh()
            self.devices_changed.emit()

    def _edit_device(self, device):
        dlg = DeviceDialog(self.db, self, device=device)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.db.update_device(
                device["id"], data["zone_id"], data["name"],
                data["device_type"], data["config"], data["is_enabled"]
            )
            self.refresh()
            self.devices_changed.emit()

    def _delete_device(self, device):
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"'{device['name']}' 디바이스를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_device(device["id"])
            self.refresh()
            self.devices_changed.emit()
