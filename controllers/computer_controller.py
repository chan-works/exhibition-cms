import subprocess
import platform
import socket
import struct
import ipaddress
from typing import Tuple, List


def normalize_mac(mac_address: str) -> str:
    """Normalize MAC address to colon-separated uppercase."""
    clean = mac_address.replace(":", "").replace("-", "").replace(".", "").upper()
    if len(clean) != 12:
        raise ValueError(f"잘못된 MAC 주소: {mac_address}")
    return ":".join(clean[i:i+2] for i in range(0, 12, 2))


def send_magic_packet(mac_address: str, target: str = "255.255.255.255", port: int = 9):
    """Send Wake-on-LAN magic packet to target IP (broadcast or unicast)."""
    mac_clean = mac_address.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError(f"잘못된 MAC 주소: {mac_address}")
    mac_bytes = bytes.fromhex(mac_clean)
    magic = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2)
        sock.sendto(magic, (target, port))


def get_subnet_broadcast(ip: str, prefix: int = 24) -> str:
    """Calculate subnet broadcast address from IP."""
    try:
        net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
        return str(net.broadcast_address)
    except Exception:
        return "255.255.255.255"


def send_wol_all_methods(mac: str, host: str, broadcast: str = "255.255.255.255") -> List[str]:
    """Try multiple WOL methods and return list of results."""
    results = []
    targets = list({broadcast, "255.255.255.255"})

    # Also try subnet broadcasts if host IP is given
    if host and host not in ("", "255.255.255.255"):
        for prefix in (24, 16):
            sb = get_subnet_broadcast(host, prefix)
            if sb not in targets:
                targets.append(sb)
        # Unicast to host IP
        if host not in targets:
            targets.append(host)

    for target in targets:
        for port in (9, 7):
            try:
                send_magic_packet(mac, target=target, port=port)
                results.append(f"✓ {target}:{port}")
            except Exception as e:
                results.append(f"✗ {target}:{port} → {e}")
    return results


class ComputerController:
    """Wake-on-LAN + remote shutdown controller."""

    def __init__(self, host: str, mac: str = "", broadcast: str = "255.255.255.255",
                 wol_port: int = 9, ssh_user: str = "", ssh_password: str = "",
                 shutdown_method: str = "wmi"):
        """
        shutdown_method:
          'wmi'   – Windows Net Use / shutdown command (same AD/workgroup)
          'ssh'   – SSH shutdown (requires paramiko)
          'local' – local machine
        """
        self.host = host
        self.mac = mac
        self.broadcast = broadcast
        self.wol_port = wol_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.shutdown_method = shutdown_method

    def power_on(self) -> Tuple[bool, str]:
        """Wake-on-LAN - tries multiple broadcast targets and ports."""
        if not self.mac:
            return False, "MAC 주소가 설정되지 않았습니다.\n→ 디바이스 설정에서 MAC 주소를 입력하세요."
        try:
            results = send_wol_all_methods(self.mac, self.host, self.broadcast)
            success = any(r.startswith("✓") for r in results)
            detail = "\n".join(results)
            if success:
                return True, f"WOL 패킷 전송 완료\n{detail}"
            return False, f"모든 WOL 방식 실패\n{detail}"
        except Exception as e:
            return False, f"WOL 전송 실패: {e}"

    def wol_diagnose(self) -> str:
        """Send WOL via all methods and return detailed result string."""
        if not self.mac:
            return "MAC 주소가 설정되지 않았습니다."
        try:
            mac_norm = normalize_mac(self.mac)
        except ValueError as e:
            return str(e)

        lines = [f"MAC: {mac_norm}", f"대상 IP: {self.host or '미설정'}", ""]
        results = send_wol_all_methods(mac_norm, self.host, self.broadcast)
        lines += results
        lines += [
            "",
            "※ WOL이 작동하지 않는 경우:",
            "  1. 대상 PC BIOS → 'Wake on LAN' 활성화",
            "  2. Windows: 장치관리자 → 네트워크 어댑터",
            "     → 속성 → 전원관리 → '이 장치로 컴퓨터를 켤 수 있음' 체크",
            "  3. 대상 PC가 완전 종료 상태여야 함 (재시작 후 종료 필요)",
        ]
        return "\n".join(lines)

    def power_off(self) -> Tuple[bool, str]:
        """Remote shutdown."""
        try:
            if self.shutdown_method == "ssh":
                return self._ssh_shutdown()
            elif self.shutdown_method == "wmi":
                return self._wmi_shutdown()
            elif self.shutdown_method == "local":
                return self._local_shutdown()
            else:
                return False, f"알 수 없는 종료 방식: {self.shutdown_method}"
        except Exception as e:
            return False, str(e)

    def _wmi_shutdown(self) -> Tuple[bool, str]:
        """Windows shutdown via net rpc / shutdown command."""
        if platform.system() != "Windows":
            return False, "WMI 종료는 Windows에서만 사용 가능합니다"
        cmd = ["shutdown", "/s", "/m", f"\\\\{self.host}", "/t", "0", "/f"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True, f"종료 명령 전송: {self.host}"
        return False, result.stderr or result.stdout

    def _ssh_shutdown(self) -> Tuple[bool, str]:
        """SSH shutdown (Linux/Mac/Windows with SSH)."""
        try:
            import paramiko
        except ImportError:
            return False, "paramiko 패키지가 필요합니다: pip install paramiko"
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(self.host, username=self.ssh_user, password=self.ssh_password, timeout=5)
            # Try Windows shutdown first, fallback to Linux
            stdin, stdout, stderr = ssh.exec_command("shutdown /s /t 0 2>nul || sudo shutdown -h now")
            ssh.close()
            return True, f"SSH 종료 명령 전송: {self.host}"
        except Exception as e:
            return False, str(e)

    def _local_shutdown(self) -> Tuple[bool, str]:
        if platform.system() == "Windows":
            subprocess.run(["shutdown", "/s", "/t", "0"])
        else:
            subprocess.run(["sudo", "shutdown", "-h", "now"])
        return True, "로컬 시스템 종료 중"

    def enable_ssh_remote(self) -> Tuple[bool, str]:
        """
        Enable OpenSSH Server on remote Windows PC via WinRM or SSH.
        Requires either: WinRM enabled (same network/domain) or SSH already working.
        """
        ps_script = r"""
# 1. OpenSSH Server 설치
$cap = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($cap -and $cap.State -ne 'Installed') {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
    "OpenSSH 서버 설치 완료"
} else {
    "OpenSSH 서버 이미 설치됨"
}

# 2. 서비스 시작 및 자동 시작 설정
Start-Service sshd -ErrorAction SilentlyContinue
Set-Service -Name sshd -StartupType Automatic
"sshd 서비스 시작 완료"

# 3. 방화벽 규칙 추가 (포트 22)
$rule = Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' `
        -DisplayName 'OpenSSH Server (sshd)' `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    "방화벽 규칙 추가 완료"
} else {
    "방화벽 규칙 이미 존재함"
}

# 결과 확인
$svc = Get-Service sshd -ErrorAction SilentlyContinue
"sshd 상태: $($svc.Status)"
"""
        if self.shutdown_method == "ssh":
            return self._run_ps_via_ssh(ps_script)
        else:
            return self._run_ps_via_wmi(ps_script)

    def enable_wol_remote(self) -> Tuple[bool, str]:
        """
        Remotely enable WOL on Windows network adapters via PowerShell (WMI/SSH).
        The target PC must be ON and reachable.
        """
        ps_script = r"""
$adapters = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' }
$results = @()
foreach ($adapter in $adapters) {
    try {
        # Enable Wake on Magic Packet via advanced property
        $params = @{
            Name         = $adapter.Name
            RegistryKeyword = 'WakeOnMagicPacket'
            RegistryValue   = 1
        }
        Set-NetAdapterAdvancedProperty @params -ErrorAction SilentlyContinue

        # Enable via power management (WMI)
        $wmi = Get-WmiObject -Class MSPower_DeviceWakeEnable `
            -Namespace root\wmi -ErrorAction SilentlyContinue |
            Where-Object { $_.InstanceName -like "*$($adapter.InterfaceDescription)*" }
        if ($wmi) { $wmi.Enable = $true; $wmi.Put() | Out-Null }

        $results += "OK: $($adapter.Name)"
    } catch {
        $results += "SKIP: $($adapter.Name) - $_"
    }
}

# Also disable 'Fast Startup' which can block WOL
powercfg /hibernate off 2>$null

$results -join "`n"
"""
        if self.shutdown_method == "ssh":
            return self._run_ps_via_ssh(ps_script)
        else:
            return self._run_ps_via_wmi(ps_script)

    def _run_ps_via_wmi(self, script: str) -> Tuple[bool, str]:
        if platform.system() != "Windows":
            return False, "WMI 방식은 Windows CMS에서만 사용 가능합니다.\nSSH 방식을 사용하세요."
        try:
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1",
                                             delete=False, encoding="utf-8") as f:
                f.write(script)
                tmp = f.name
            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command",
                f"Invoke-Command -ComputerName {self.host} "
                f"-ScriptBlock {{ {script.strip()} }}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            os.unlink(tmp)
            if result.returncode == 0:
                return True, f"WOL 설정 완료:\n{result.stdout.strip()}"
            return False, result.stderr.strip() or "실행 실패"
        except Exception as e:
            return False, str(e)

    def _run_ps_via_ssh(self, script: str) -> Tuple[bool, str]:
        try:
            import paramiko
        except ImportError:
            return False, "paramiko 패키지가 필요합니다: pip install paramiko"
        if not self.ssh_user:
            return False, "SSH 사용자 이름이 설정되지 않았습니다."
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, username=self.ssh_user,
                        password=self.ssh_password, timeout=10)
            cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{script.strip()}"'
            _, stdout, stderr = ssh.exec_command(cmd, timeout=30)
            out = stdout.read().decode(errors="ignore").strip()
            err = stderr.read().decode(errors="ignore").strip()
            ssh.close()
            if out:
                return True, f"WOL 설정 완료:\n{out}"
            if err:
                return False, err
            return True, "WOL 설정 명령 전송 완료"
        except Exception as e:
            return False, str(e)

    def test_ping(self) -> Tuple[bool, str]:
        """Ping the host to check if it is online."""
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", "1000", self.host]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", self.host]
            result = subprocess.run(cmd, capture_output=True, timeout=3)
            if result.returncode == 0:
                return True, f"{self.host} 온라인"
            return False, f"{self.host} 오프라인"
        except Exception as e:
            return False, str(e)
