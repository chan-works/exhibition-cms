from pythonosc import udp_client
from pythonosc.osc_message_builder import OscMessageBuilder


class OscController:
    """OSC UDP client."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = udp_client.SimpleUDPClient(self.host, self.port)
        return self._client

    def send(self, address: str, *args):
        """Send an OSC message with arbitrary arguments."""
        try:
            client = self._get_client()
            client.send_message(address, list(args) if len(args) > 1 else (args[0] if args else []))
            return True, "전송 성공"
        except OSError as e:
            if e.errno in (10061, 111):
                return False, f"연결 거부됨 ({self.host}:{self.port})\n→ 대상 프로그램이 실행 중인지 확인하세요."
            return False, f"네트워크 오류: {e}"
        except Exception as e:
            return False, str(e)

    def send_on(self, address: str, on_value=1):
        return self.send(address, on_value)

    def send_off(self, address: str, off_value=0):
        return self.send(address, off_value)

    def test_connection(self):
        try:
            self._client = udp_client.SimpleUDPClient(self.host, self.port)
            self._client.send_message("/ping", 1)
            return True, f"OSC 전송 성공 → {self.host}:{self.port}"
        except Exception as e:
            return False, str(e)
