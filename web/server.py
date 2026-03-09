"""
Exhibition CMS - 웹 인터페이스
브라우저(맥북 등)에서 접속 가능한 Flask 기반 웹 서버.
Windows CMS 앱이 실행 중일 때 백그라운드 스레드로 같이 실행됩니다.

접속: http://<Windows-PC-IP>:8080
"""
import os
import sys
import json
import threading
import logging
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask, render_template, request, session,
    redirect, url_for, jsonify, flash
)

# 부모 디렉터리를 sys.path에 추가 (컨트롤러/DB 공유)
_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=os.path.join(_dir, "templates"),
    static_folder=os.path.join(_dir, "static"),
)

# ngrok 브라우저 경고 자동 스킵
@app.after_request
def skip_ngrok_warning(response):
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

# 500 에러 상세 로깅
@app.errorhandler(500)
def internal_error(e):
    import traceback
    logger.error("500 Internal Server Error:\n%s", traceback.format_exc())
    return f"<pre>Internal Server Error:\n{traceback.format_exc()}</pre>", 500

# 전역 상태
_db = None
_scheduler = None


def init_app(db, scheduler=None):
    """앱 초기화 - DB와 스케줄러 주입."""
    global _db, _scheduler
    _db = db
    _scheduler = scheduler
    # DB에서 시크릿 키 로드 (재시작해도 세션 유지)
    key = _db.get_setting("web_secret_key")
    if not key:
        key = os.urandom(32).hex()
        _db.set_setting("web_secret_key", key)
    app.secret_key = key.encode()


# ── 인증 데코레이터 ──────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_session_vars():
    """모든 템플릿에서 사용할 수 있는 변수 주입."""
    return dict(
        current_role=session.get("role", ""),
        current_username=session.get("username", ""),
        current_fullname=session.get("full_name", session.get("username", "")),
    )


def operator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") not in ("admin", "operator"):
            return jsonify(error="권한이 없습니다"), 403
        return f(*args, **kwargs)
    return decorated


# ── 인증 라우트 ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = _db.authenticate_user(username, password)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user.get("full_name") or user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"), 303)  # 303: POST→GET
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── 페이지 라우트 ────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    zones = _db.get_all_zones()
    devices = _db.get_all_devices()

    # 구역별 디바이스 그룹핑
    devices_by_zone = {}
    for d in devices:
        zid = d.get("zone_id")
        devices_by_zone.setdefault(zid, []).append(d)

    today_str = date.today().isoformat()
    schedules = _db.get_schedules_for_date(today_str)

    return render_template(
        "dashboard.html",
        active="dashboard",
        zones=zones,
        devices_by_zone=devices_by_zone,
        unzoned=devices_by_zone.get(None, []),
        schedules=schedules,
        today=today_str,
    )


@app.route("/devices")
@login_required
def devices_page():
    devices = _db.get_all_devices()
    zones = _db.get_all_zones()
    return render_template(
        "devices.html",
        active="devices",
        devices=devices,
        zones=zones,
    )


@app.route("/calendar")
@login_required
def calendar_page():
    import calendar as cal_mod
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    schedules = _db.get_schedules_for_month(year, month)
    zones = _db.get_all_zones()
    first_weekday, days_in_month = cal_mod.monthrange(year, month)
    cal_days = [{"empty": True}] * first_weekday + [
        {"empty": False, "day": d, "weekday": (first_weekday + d - 1) % 7}
        for d in range(1, days_in_month + 1)
    ]
    sched_map = {}
    for s in schedules:
        key = s["schedule_date"]
        sched_map.setdefault(key, []).append(s)
    return render_template("calendar.html", active="calendar",
        schedules=schedules, zones=zones, year=year, month=month,
        today=today.isoformat(), cal_days=cal_days, sched_map=sched_map)


@app.route("/recurring")
@login_required
def recurring_page():
    zones = _db.get_all_zones()
    recurring = _db.get_all_recurring_schedules()
    return render_template("recurring.html", active="recurring",
        zones=zones, recurring=recurring)


@app.route("/api/recurring/save", methods=["POST"])
@login_required
@operator_required
def recurring_save():
    d = request.get_json() or {}
    _db.save_recurring_schedule(
        d["zone_id"], d["day_of_week"],
        d.get("time_on") or None, d.get("time_off") or None,
        d.get("is_enabled", 1), d.get("notes", "")
    )
    return jsonify(ok=True)


@app.route("/api/recurring/delete", methods=["POST"])
@login_required
@operator_required
def recurring_delete():
    d = request.get_json() or {}
    _db.delete_recurring_schedule(d["zone_id"], d["day_of_week"])
    return jsonify(ok=True)


@app.route("/zones")
@login_required
def zones_page():
    zones = _db.get_all_zones()
    return render_template("zones.html", active="zones", zones=zones)


@app.route("/api/zone/create", methods=["POST"])
@login_required
@operator_required
def zone_create():
    d = request.get_json() or {}
    zid = _db.create_zone(d["name"], d.get("description", ""), d.get("color", "#2196F3"))
    return jsonify(ok=True, id=zid)


@app.route("/api/zone/<int:zone_id>/update", methods=["POST"])
@login_required
@operator_required
def zone_update(zone_id):
    d = request.get_json() or {}
    _db.update_zone(zone_id, d["name"], d.get("description", ""), d.get("color", "#2196F3"))
    return jsonify(ok=True)


@app.route("/api/zone/<int:zone_id>/delete", methods=["POST"])
@login_required
@operator_required
def zone_delete(zone_id):
    _db.delete_zone(zone_id)
    return jsonify(ok=True)


@app.route("/users")
@login_required
def users_page():
    if session.get("role") != "admin":
        return render_template("access_denied.html", active="users")
    users = _db.get_all_users()
    return render_template("users.html", active="users", users=users)


@app.route("/api/user/create", methods=["POST"])
@login_required
def user_create():
    if session.get("role") != "admin":
        return jsonify(error="권한 없음"), 403
    d = request.get_json() or {}
    try:
        _db.create_user(d["username"], d["password"], d.get("full_name", ""), d.get("role", "operator"))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route("/api/user/<int:user_id>/update", methods=["POST"])
@login_required
def user_update(user_id):
    if session.get("role") != "admin":
        return jsonify(error="권한 없음"), 403
    d = request.get_json() or {}
    _db.update_user(user_id, d.get("full_name", ""), d.get("role", "operator"), d.get("is_active", 1))
    return jsonify(ok=True)


@app.route("/api/user/<int:user_id>/password", methods=["POST"])
@login_required
def user_password(user_id):
    if session.get("role") != "admin":
        return jsonify(error="권한 없음"), 403
    d = request.get_json() or {}
    _db.update_user_password(user_id, d["password"])
    return jsonify(ok=True)


@app.route("/api/user/<int:user_id>/delete", methods=["POST"])
@login_required
def user_delete(user_id):
    if session.get("role") != "admin":
        return jsonify(error="권한 없음"), 403
    if user_id == session.get("user_id"):
        return jsonify(error="자기 자신은 삭제할 수 없습니다"), 400
    _db.delete_user(user_id)
    return jsonify(ok=True)


@app.route("/notifications")
@login_required
def notifications_page():
    notifs = _db.get_notifications(limit=100)
    unread = _db.get_unread_count()
    return render_template("notifications.html", active="notifications",
        notifications=notifs, unread=unread)


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    _db.mark_all_notifications_read()
    return jsonify(ok=True)


@app.route("/api/schedule/save", methods=["POST"])
@login_required
@operator_required
def schedule_save():
    d = request.get_json() or {}
    _db.save_schedule(
        d["zone_id"], d["date"],
        d.get("time_on") or None, d.get("time_off") or None,
        d.get("is_enabled", 1), d.get("is_holiday", 0),
        d.get("holiday_name", ""), d.get("notes", "")
    )
    return jsonify(ok=True)


@app.route("/api/schedule/delete", methods=["POST"])
@login_required
@operator_required
def schedule_delete():
    d = request.get_json() or {}
    _db.delete_schedule(d["zone_id"], d["date"])
    return jsonify(ok=True)


@app.route("/schedules")
@login_required
def schedules_page():
    import calendar as cal_mod
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    schedules = _db.get_schedules_for_month(year, month)
    zones = _db.get_all_zones()
    recurring = _db.get_all_recurring_schedules()

    # 캘린더 날짜 목록 계산 (빈 칸 포함)
    first_weekday, days_in_month = cal_mod.monthrange(year, month)
    # first_weekday: 0=월, 6=일
    cal_days = []
    for _ in range(first_weekday):
        cal_days.append({"empty": True})
    for d in range(1, days_in_month + 1):
        weekday = (first_weekday + d - 1) % 7
        cal_days.append({"empty": False, "day": d, "weekday": weekday})

    return render_template(
        "schedules.html",
        active="schedules",
        schedules=schedules,
        zones=zones,
        recurring=recurring,
        year=year,
        month=month,
        today=today.isoformat(),
        cal_days=cal_days,
    )


# ── REST API ─────────────────────────────────────────────────────────────────

@app.route("/api/device/<int:device_id>/action", methods=["POST"])
@login_required
@operator_required
def device_action(device_id):
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("on", "off"):
        return jsonify(error="action은 on 또는 off여야 합니다"), 400

    devices = _db.get_all_devices()
    device = next((d for d in devices if d["id"] == device_id), None)
    if not device:
        return jsonify(error="디바이스를 찾을 수 없습니다"), 404

    if not _scheduler:
        return jsonify(error="스케줄러가 초기화되지 않았습니다"), 500

    ok, msg = _scheduler.run_device_now(device, action)
    return jsonify(ok=ok, message=msg)


@app.route("/api/zone/<int:zone_id>/action", methods=["POST"])
@login_required
@operator_required
def zone_action(zone_id):
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("on", "off"):
        return jsonify(error="action은 on 또는 off여야 합니다"), 400

    if not _scheduler:
        return jsonify(error="스케줄러가 초기화되지 않았습니다"), 500

    results = _scheduler.run_zone_now(zone_id, action)
    all_ok = all(r[1] for r in results)
    summary = [{"name": r[0], "ok": r[1], "message": r[2]} for r in results]
    return jsonify(ok=all_ok, results=summary)


@app.route("/api/detect-mac", methods=["POST"])
@login_required
def detect_mac():
    """IP 주소로 MAC 주소 자동 감지 (ARP 테이블 + iptime 공유기 조회)."""
    data = request.get_json() or {}
    ip = data.get("ip", "").strip()
    router_ip = data.get("router_ip", "").strip()
    router_user = data.get("router_user", "admin")
    router_password = data.get("router_password", "admin")

    if not ip:
        return jsonify(error="IP 주소를 입력하세요"), 400

    from controllers.network_scanner import ping, get_mac_from_arp, get_mac_from_iptime

    # 1) ARP 테이블 (ping 후 조회)
    ping(ip, timeout=1.0)
    mac = get_mac_from_arp(ip)

    if not mac and router_ip:
        # 2) iptime 공유기 DHCP 목록 조회
        mac = get_mac_from_iptime(router_ip, ip, router_user, router_password)

    if mac:
        return jsonify(mac=mac)
    return jsonify(
        error=f"{ip}의 MAC 주소를 찾을 수 없습니다. PC가 켜져 있고 같은 네트워크인지 확인하세요."
    ), 404


@app.route("/api/ping", methods=["POST"])
@login_required
def ping_host():
    """IP 주소 온라인 여부 확인."""
    data = request.get_json() or {}
    ip = data.get("ip", "").strip()
    if not ip:
        return jsonify(error="IP 주소가 필요합니다"), 400
    from controllers.network_scanner import ping
    online = ping(ip, timeout=1.5)
    return jsonify(online=online, ip=ip)


@app.route("/api/status")
@login_required
def api_status():
    """간단한 상태 확인 엔드포인트."""
    return jsonify(
        ok=True,
        user=session.get("username"),
        role=session.get("role"),
        server_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── 서버 실행 헬퍼 ───────────────────────────────────────────────────────────

def run_server(host="0.0.0.0", port=8080, debug=False):
    """Flask 개발 서버 실행 (블로킹)."""
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def start_background(db, scheduler=None, host="0.0.0.0", port=8080):
    """백그라운드 데몬 스레드로 웹 서버를 시작합니다."""
    init_app(db, scheduler)
    t = threading.Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        daemon=True,
        name="ExhibitionCMS-WebServer",
    )
    t.start()
    logger.info("웹 서버 시작: http://%s:%d", host, port)
    return t
