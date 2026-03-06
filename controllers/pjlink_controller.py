import socket
import hashlib


class PJLinkController:
    """PJLink Class 1 TCP controller (port 4352)."""

    PORT = 4352
    TIMEOUT = 5

    def __init__(self, host, port=4352, password=None):
        self.host = host
        self.port = port
        self.password = password

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.TIMEOUT)
        sock.connect((self.host, self.port))
        banner = sock.recv(512).decode("utf-8", errors="ignore").strip()
        prefix = ""
        # Banner format: "PJLINK 0" (no auth) or "PJLINK 1 <random>"
        if banner.startswith("PJLINK 1"):
            parts = banner.split()
            rand = parts[2] if len(parts) > 2 else ""
            if self.password:
                token = (rand + self.password).encode()
                prefix = hashlib.md5(token).hexdigest()
        return sock, prefix

    def _send_command(self, command):
        try:
            sock, prefix = self._connect()
            cmd = f"{prefix}{command}\r"
            sock.sendall(cmd.encode())
            response = sock.recv(512).decode("utf-8", errors="ignore").strip()
            sock.close()
            return True, response
        except ConnectionRefusedError:
            return False, f"연결 거부됨 ({self.host}:{self.port})\n→ 기기가 꺼져있거나 PJLink가 비활성화 상태입니다."
        except TimeoutError:
            return False, f"연결 시간 초과 ({self.host}:{self.port})\n→ IP 주소를 확인하세요."
        except OSError as e:
            if e.errno in (10061, 111):
                return False, f"연결 거부됨 ({self.host}:{self.port})\n→ 기기가 꺼져있거나 네트워크를 확인하세요."
            if e.errno in (10060, 110):
                return False, f"연결 시간 초과 ({self.host}:{self.port})\n→ IP 주소를 확인하세요."
            return False, f"네트워크 오류: {e}"
        except Exception as e:
            return False, str(e)

    def power_on(self):
        return self._send_command("%1POWR 1")

    def power_off(self):
        return self._send_command("%1POWR 0")

    def get_power_status(self):
        ok, resp = self._send_command("%1POWR ?")
        if not ok:
            return "error"
        if "=1" in resp:
            return "on"
        if "=0" in resp:
            return "off"
        if "=2" in resp:
            return "cooling"
        if "=3" in resp:
            return "warming"
        return "unknown"

    def mute_on(self):
        """Audio+Video mute on."""
        return self._send_command("%1AVMT 31")

    def mute_off(self):
        """Audio+Video mute off."""
        return self._send_command("%1AVMT 30")

    def test_connection(self):
        try:
            sock, _ = self._connect()
            sock.close()
            return True, "연결 성공"
        except Exception as e:
            return False, str(e)
