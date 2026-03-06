"""
Exhibition CMS - PC 화면 스크린샷 서버
관리 대상 PC에서 이 파일을 실행하면 CMS에서 화면을 실시간으로 모니터링할 수 있습니다.

실행 방법:
  pip install mss pillow
  python screenshot_server.py

기본 포트: 19999
"""

import io
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

PORT = 19999
QUALITY = 40        # JPEG 품질 (1-95)
MAX_WIDTH = 640     # 썸네일 최대 너비


def capture_screenshot() -> bytes:
    """Capture screen and return JPEG bytes."""
    if HAS_MSS and HAS_PIL:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            # Resize
            w, h = pil_img.size
            if w > MAX_WIDTH:
                ratio = MAX_WIDTH / w
                pil_img = pil_img.resize((MAX_WIDTH, int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=QUALITY, optimize=True)
            return buf.getvalue()
    return b""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/screenshot", "/screenshot.jpg"):
            data = capture_screenshot()
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(503, "캡처 불가 (mss/pillow 미설치)")
        elif self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"pong")
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # Suppress logs


if __name__ == "__main__":
    if not HAS_MSS or not HAS_PIL:
        print("필수 패키지 설치:")
        print("  pip install mss pillow")
        input("엔터를 누르면 종료...")
        exit(1)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Screenshot Server 시작: http://0.0.0.0:{PORT}/screenshot")
    print("종료하려면 Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("서버 종료")
