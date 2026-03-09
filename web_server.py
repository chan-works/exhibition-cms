"""
Exhibition CMS - 웹 서버 독립 실행 스크립트

같은 네트워크뿐 아니라 인터넷 어디서든 접속 가능합니다 (--tunnel 옵션).

실행:
    python web_server.py                   # LAN 전용 (기본)
    python web_server.py --tunnel          # 인터넷 어디서나 접속 가능 (ngrok)
    python web_server.py --tunnel --port 9000
    python web_server.py --debug

접속:
    LAN:      http://<이-PC의-IP>:8080
    인터넷:   --tunnel 실행 시 출력되는 https://xxxx.ngrok-free.app 주소 사용

ngrok 설치 (최초 1회):
    Windows: https://ngrok.com/download 에서 다운로드 후 PATH에 추가
             또는: pip install pyngrok
    Mac:     brew install ngrok  또는  pip install pyngrok
"""
import sys
import argparse
import logging
import socket
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_local_ips():
    """이 PC의 로컬 IP 목록 반환."""
    ips = []
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        for info in infos:
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return list(dict.fromkeys(ips))  # 중복 제거


def get_tailscale_ip() -> str:
    """Tailscale IP(100.x.x.x) 반환. 설치되지 않았으면 빈 문자열."""
    # 방법 1: tailscale CLI
    try:
        import subprocess
        result = subprocess.run(
            ["tailscale", "ip", "--4"],
            capture_output=True, text=True, timeout=3
        )
        ip = result.stdout.strip()
        if ip.startswith("100."):
            return ip
    except Exception:
        pass

    # 방법 2: 네트워크 인터페이스에서 100.x.x.x 직접 탐색
    try:
        import socket
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        for info in infos:
            ip = info[4][0]
            if ip.startswith("100."):
                return ip
    except Exception:
        pass

    return ""


def start_ngrok_tunnel(port: int, authtoken: str = None) -> str:
    """
    pyngrok으로 ngrok 터널을 열고 공개 URL을 반환합니다.
    authtoken이 없으면 임시 URL (8시간 제한) 이 발급됩니다.

    영구 URL을 원하면:
      1. https://dashboard.ngrok.com 에서 무료 계정 생성
      2. authtoken 복사 후 --ngrok-token 옵션으로 전달
    """
    try:
        from pyngrok import ngrok, conf
    except ImportError:
        print("\n[터널 오류] pyngrok 패키지가 필요합니다:")
        print("  pip install pyngrok")
        print("  또는 https://ngrok.com/download 에서 ngrok 설치\n")
        return ""

    try:
        if authtoken:
            conf.get_default().auth_token = authtoken

        tunnel = ngrok.connect(port, "http")
        return tunnel.public_url.replace("http://", "https://")
    except Exception as e:
        print(f"\n[터널 오류] ngrok 연결 실패: {e}")
        print("  ngrok이 설치되어 있는지 확인하세요: ngrok --version\n")
        return ""


def open_firewall(port: int):
    """Windows 방화벽에 포트를 자동으로 엽니다."""
    import platform
    if platform.system() != "Windows":
        return
    import subprocess
    rule_name = f"Exhibition CMS Web ({port})"
    # 이미 규칙이 있으면 스킵
    check = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
        capture_output=True, text=True
    )
    if "규칙 없음" in check.stdout or "No rules match" in check.stdout or check.returncode != 0:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={rule_name}", "protocol=TCP", "dir=in",
             f"localport={port}", "action=allow"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  [방화벽] 포트 {port} 자동 허용 완료")
        else:
            print(f"  [방화벽] 자동 설정 실패 - 관리자 권한으로 실행하거나 수동으로 허용하세요")
            print(f"  수동 명령: netsh advfirewall firewall add rule name=\"{rule_name}\" protocol=TCP dir=in localport={port} action=allow")
    else:
        print(f"  [방화벽] 포트 {port} 이미 허용됨")


def print_banner(port: int, tunnel_url: str = ""):
    ts_ip = get_tailscale_ip()
    print("\n" + "=" * 54)
    print("  Exhibition CMS 웹 서버")
    print("=" * 54)
    print(f"  로컬 접속:     http://localhost:{port}")
    for ip in get_local_ips():
        print(f"  같은 네트워크: http://{ip}:{port}")
    if ts_ip:
        print()
        print(f"  ★ Tailscale:   http://{ts_ip}:{port}")
        print(f"    → Tailscale 연결된 어느 기기에서나 접속 가능")
    if tunnel_url:
        print()
        print(f"  ★ 인터넷 접속: {tunnel_url}")
        print(f"    → 맥북, 스마트폰 등 어디서나 접속 가능")
    print()
    print(f"  기본 계정:     admin / admin123")
    print("  Ctrl+C 로 종료")
    print("=" * 54 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Exhibition CMS 웹 서버")
    parser.add_argument("--port", type=int, default=8080,
                        help="포트 번호 (기본: 8080)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="바인드 호스트 (기본: 0.0.0.0)")
    parser.add_argument("--debug", action="store_true",
                        help="Flask 디버그 모드")
    parser.add_argument("--db-path", default=None,
                        help="DB 파일 경로 (기본: ~/.exhibition_cms/exhibition_cms.db)")
    parser.add_argument("--tunnel", action="store_true",
                        help="ngrok 터널로 인터넷에서 접속 가능하게 설정")
    parser.add_argument("--ngrok-token", default=None,
                        help="ngrok authtoken (무료 계정 발급: https://dashboard.ngrok.com)")
    args = parser.parse_args()

    # DB 초기화
    from database.db_manager import DatabaseManager
    try:
        db = DatabaseManager(db_path=args.db_path)
    except Exception as e:
        print(f"[오류] 데이터베이스 초기화 실패: {e}")
        sys.exit(1)

    # 스케줄러 초기화
    from controllers.scheduler import ExhibitionScheduler
    scheduler = ExhibitionScheduler(db)

    # 웹 서버 초기화
    from web.server import init_app, run_server
    init_app(db, scheduler)

    # ngrok 터널 (--tunnel 옵션)
    tunnel_url = ""
    if args.tunnel:
        print("\n[터널] ngrok 연결 중...")
        tunnel_url = start_ngrok_tunnel(args.port, args.ngrok_token)
        if not tunnel_url:
            print("[경고] 터널 없이 LAN 전용으로 시작합니다.")

    # Windows 방화벽 자동 허용
    open_firewall(args.port)

    # 접속 주소 출력
    print_banner(args.port, tunnel_url)

    # 서버 시작 (블로킹)
    run_server(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
