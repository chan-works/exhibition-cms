import struct
import serial
import serial.tools.list_ports
from typing import Optional


# ENTTEC USB DMX Pro message labels
ENTTEC_LABEL_DMX = 6
ENTTEC_START = 0x7E
ENTTEC_END = 0xE7


def list_serial_ports():
    """Return list of available serial port names."""
    return [p.device for p in serial.tools.list_ports.comports()]


class UsbDmxController:
    """ENTTEC USB DMX Pro compatible controller over serial port."""

    def __init__(self, port: str, universe: int = 0):
        self.port = port
        self.universe = universe
        self._serial: Optional[serial.Serial] = None

    def open(self):
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=57600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
            timeout=1
        )

    def close(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def _build_packet(self, channels) -> bytes:
        data = list(channels)
        if len(data) > 512:
            data = data[:512]
        # DMX start code (0x00) + channel data
        dmx_payload = bytes([0x00] + data)
        length = len(dmx_payload)
        packet = bytes([
            ENTTEC_START,
            ENTTEC_LABEL_DMX,
            length & 0xFF,
            (length >> 8) & 0xFF,
        ]) + dmx_payload + bytes([ENTTEC_END])
        return packet

    def send_dmx(self, channels):
        """Send DMX frame. Auto-opens port if needed."""
        if not self._serial or not self._serial.is_open:
            self.open()
        packet = self._build_packet(channels)
        self._serial.write(packet)

    def blackout(self):
        self.send_dmx([0] * 512)

    def full_on(self):
        self.send_dmx([255] * 512)

    def send_scene(self, scene):
        """
        scene: dict {channel(1-512): value(0-255)}
             or list of up to 512 values.
        """
        if isinstance(scene, dict):
            channels = [0] * 512
            for ch, val in scene.items():
                if 1 <= ch <= 512:
                    channels[ch - 1] = int(val)
        else:
            channels = [int(v) for v in scene]
        self.send_dmx(channels)

    def test_connection(self):
        try:
            self.open()
            self.send_dmx([0] * 512)
            return True, f"USB DMX 연결 성공: {self.port}"
        except Exception as e:
            return False, str(e)
