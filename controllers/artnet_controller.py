import socket
import struct


class ArtNetController:
    """ArtNet DMX-over-UDP controller (port 6454)."""

    ARTNET_PORT = 6454
    ARTDMX_OPCODE = 0x5000
    PROTOCOL_VER = 14

    def __init__(self, host, universe=0, subnet=0, net=0, broadcast=False):
        self.host = host
        self.universe = universe & 0x0F
        self.subnet = subnet & 0x0F
        self.net = net & 0x7F
        self.broadcast = broadcast
        self.sequence = 0

    def _build_artdmx(self, channels):
        self.sequence = (self.sequence + 1) % 256
        header = b"Art-Net\x00"
        opcode = struct.pack("<H", self.ARTDMX_OPCODE)
        version = struct.pack(">H", self.PROTOCOL_VER)
        seq = struct.pack("B", self.sequence)
        physical = struct.pack("B", 0)
        # Port-address: Net(7) | Subnet(4) | Universe(4)
        port_addr = (self.net << 8) | (self.subnet << 4) | self.universe
        univ = struct.pack("<H", port_addr)
        data = list(channels)
        if len(data) < 2:
            data += [0] * (2 - len(data))
        if len(data) > 512:
            data = data[:512]
        # DMX length must be even
        if len(data) % 2:
            data.append(0)
        length = struct.pack(">H", len(data))
        return header + opcode + version + seq + physical + univ + length + bytes(data)

    def send_dmx(self, channels):
        """Send raw DMX channel list (values 0-255, up to 512 channels)."""
        packet = self._build_artdmx(channels)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if self.broadcast:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (self.host, self.ARTNET_PORT))
        finally:
            sock.close()

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
            self.send_dmx([0] * 512)
            return True, "ArtNet 패킷 전송 성공"
        except Exception as e:
            return False, str(e)
