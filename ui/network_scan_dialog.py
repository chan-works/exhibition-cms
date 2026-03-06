import threading
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QFrame, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QThread, QObject

from controllers.network_scanner import NetworkScanner, get_local_subnets


class ScanWorker(QObject):
    progress = Signal(int, int)        # done, total
    finished = Signal(dict)            # results
    error = Signal(str)

    def __init__(self, subnet=None):
        super().__init__()
        self.subnet = subnet
        self._scanner = NetworkScanner()

    def run(self):
        try:
            self._scanner.progress_callback = lambda d, t: self.progress.emit(d, t)
            results = self._scanner.scan(subnet=self.subnet)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._scanner.stop()


class NetworkScanDialog(QDialog):
    device_selected = Signal(str, str, str)  # device_type, ip, mac

    def __init__(self, parent=None, device_type_filter=None):
        super().__init__(parent)
        self.device_type_filter = device_type_filter  # 'computer' or 'pjlink' or None
        self._worker = None
        self._thread = None
        self.setWindowTitle("네트워크 디바이스 자동 감지")
        self.setMinimumSize(640, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("네트워크 자동 감지")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e94560;")
        layout.addWidget(title)

        hint = QLabel("로컬 네트워크에서 PC와 PJLink 프로젝터를 자동으로 탐색합니다.")
        hint.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(hint)

        # Subnet row
        subnet_row = QHBoxLayout()
        subnet_lbl = QLabel("서브넷:")
        subnet_lbl.setFixedWidth(60)
        subnet_row.addWidget(subnet_lbl)

        self.subnet_combo = QComboBox()
        self.subnet_combo.setEditable(True)
        self.subnet_combo.addItem("자동 감지")
        for sub in get_local_subnets():
            self.subnet_combo.addItem(sub)
        subnet_row.addWidget(self.subnet_combo, 1)

        subnet_hint = QLabel("예: 192.168.1  (마지막 숫자 제외)")
        subnet_hint.setStyleSheet("color: #606070; font-size: 11px;")
        subnet_row.addWidget(subnet_hint)
        layout.addLayout(subnet_row)

        # Progress
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        prog_row.addWidget(self.progress_bar)

        self.scan_btn = QPushButton("스캔 시작")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setFixedWidth(100)
        self.scan_btn.clicked.connect(self._toggle_scan)
        prog_row.addWidget(self.scan_btn)
        layout.addLayout(prog_row)

        self.status_lbl = QLabel("스캔 준비 완료")
        self.status_lbl.setStyleSheet("color: #a0b0c0; font-size: 12px;")
        layout.addWidget(self.status_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["IP 주소", "호스트명", "MAC 주소", "PJLink", "선택"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _toggle_scan(self):
        if self._thread and self._thread.isRunning():
            self._stop_scan()
        else:
            self._start_scan()

    def _start_scan(self):
        self.table.setRowCount(0)
        self.scan_btn.setText("중지")
        self.progress_bar.setValue(0)
        self.status_lbl.setText("스캔 중...")

        subnet_text = self.subnet_combo.currentText().strip()
        subnet = None if subnet_text == "자동 감지" else subnet_text

        self._worker = ScanWorker(subnet=subnet)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _stop_scan(self):
        if self._worker:
            self._worker.stop()
        self.scan_btn.setText("스캔 시작")
        self.status_lbl.setText("스캔 중지됨")

    def _on_progress(self, done, total):
        pct = int(done / total * 100) if total else 0
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(f"스캔 중... {done}/{total}")

    def _on_finished(self, results):
        self.scan_btn.setText("스캔 시작")
        self.progress_bar.setValue(100)

        all_devices = []
        for d in results.get("pjlink", []):
            all_devices.append(d)
        for d in results.get("computers", []):
            all_devices.append(d)

        # Apply filter
        if self.device_type_filter == "pjlink":
            all_devices = [d for d in all_devices if d.get("pjlink")]
        elif self.device_type_filter == "computer":
            all_devices = [d for d in all_devices if not d.get("pjlink")]

        self.table.setRowCount(len(all_devices))
        for i, dev in enumerate(all_devices):
            self.table.setItem(i, 0, QTableWidgetItem(dev["ip"]))
            self.table.setItem(i, 1, QTableWidgetItem(dev.get("hostname", "")))
            self.table.setItem(i, 2, QTableWidgetItem(dev.get("mac", "")))

            pjlink_item = QTableWidgetItem("✓ PJLink" if dev.get("pjlink") else "PC")
            pjlink_item.setForeground(
                Qt.GlobalColor.green if dev.get("pjlink") else Qt.GlobalColor.cyan
            )
            self.table.setItem(i, 3, pjlink_item)

            btn_widget = QPushButton("이 IP 사용")
            btn_widget.setFixedHeight(26)
            btn_widget.setObjectName("primary" if dev.get("pjlink") else "success")
            dtype = "pjlink" if dev.get("pjlink") else "computer"
            btn_widget.clicked.connect(
                lambda checked, d=dev, t=dtype: self._select(t, d["ip"], d.get("mac", ""))
            )
            self.table.setCellWidget(i, 4, btn_widget)
            self.table.setRowHeight(i, 38)

        found = len(all_devices)
        pjlink_cnt = sum(1 for d in all_devices if d.get("pjlink"))
        pc_cnt = found - pjlink_cnt
        self.status_lbl.setText(f"완료 — 총 {found}개 발견 (PJLink: {pjlink_cnt}, PC: {pc_cnt})")

        if self._thread:
            self._thread.quit()

    def _on_error(self, msg):
        self.scan_btn.setText("스캔 시작")
        self.status_lbl.setText(f"오류: {msg}")
        if self._thread:
            self._thread.quit()

    def _select(self, dtype, ip, mac):
        self.device_selected.emit(dtype, ip, mac)
        self.accept()

    def closeEvent(self, event):
        self._stop_scan()
        super().closeEvent(event)
