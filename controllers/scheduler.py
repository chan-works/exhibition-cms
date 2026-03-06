import json
import logging
from datetime import datetime, date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from controllers.pjlink_controller import PJLinkController
from controllers.artnet_controller import ArtNetController
from controllers.usb_dmx_controller import UsbDmxController
from controllers.osc_controller import OscController
from controllers.computer_controller import ComputerController

logger = logging.getLogger(__name__)


class ExhibitionScheduler:
    """Background scheduler that executes device ON/OFF at scheduled times."""

    def __init__(self, db_manager, notification_callback=None):
        self.db = db_manager
        self.notify = notification_callback or (lambda t, m, tp="info": None)
        self._scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._scheduler.start()
        self._reload_jobs()

    # ── Public API ────────────────────────────────────────────────────────────

    def reload(self):
        """Call this after schedule changes to refresh all jobs."""
        self._reload_jobs()

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reload_jobs(self):
        self._scheduler.remove_all_jobs()
        today = date.today().isoformat()
        schedules = self.db.get_schedules_for_date(today)

        for sched in schedules:
            if not sched["is_enabled"] or sched["is_holiday"]:
                continue
            zone_id = sched["zone_id"]
            zone_name = sched.get("zone_name", f"Zone {zone_id}")

            if sched.get("time_on"):
                h, m = map(int, sched["time_on"].split(":"))
                self._scheduler.add_job(
                    self._run_zone,
                    CronTrigger(hour=h, minute=m),
                    args=[zone_id, zone_name, "on"],
                    id=f"on_{zone_id}_{today}",
                    replace_existing=True
                )

            if sched.get("time_off"):
                h, m = map(int, sched["time_off"].split(":"))
                self._scheduler.add_job(
                    self._run_zone,
                    CronTrigger(hour=h, minute=m),
                    args=[zone_id, zone_name, "off"],
                    id=f"off_{zone_id}_{today}",
                    replace_existing=True
                )

        logger.info("스케줄 새로고침 완료: %d개 구역 로드", len(schedules))

    def _run_zone(self, zone_id: int, zone_name: str, action: str):
        devices = self.db.get_devices_by_zone(zone_id)
        results = []
        for device in devices:
            ok, msg = self._execute_device(device, action)
            results.append((device["name"], ok, msg))
            status = "성공" if ok else "실패"
            logger.info("[%s] %s %s → %s: %s", zone_name, device["name"], action, status, msg)

        success = all(r[1] for r in results)
        summary = "\n".join(f"  {n}: {'✓' if ok else '✗'} {m}" for n, ok, m in results)
        ntype = "success" if success else "warning"
        self.notify(
            f"[{zone_name}] {action.upper()} {'완료' if success else '일부 실패'}",
            summary,
            ntype
        )

    def _execute_device(self, device: dict, action: str):
        dtype = device["device_type"]
        cfg = device["config"] if isinstance(device["config"], dict) else {}

        try:
            if dtype == "pjlink":
                ctrl = PJLinkController(
                    host=cfg.get("host", ""),
                    port=int(cfg.get("port", 4352)),
                    password=cfg.get("password", "") or None
                )
                return ctrl.power_on() if action == "on" else ctrl.power_off()

            elif dtype == "computer":
                ctrl = ComputerController(
                    host=cfg.get("host", ""),
                    mac=cfg.get("mac", ""),
                    broadcast=cfg.get("broadcast", "255.255.255.255"),
                    wol_port=int(cfg.get("wol_port", 9)),
                    ssh_user=cfg.get("ssh_user", ""),
                    ssh_password=cfg.get("ssh_password", ""),
                    shutdown_method=cfg.get("shutdown_method", "wmi")
                )
                return ctrl.power_on() if action == "on" else ctrl.power_off()

            elif dtype == "artnet":
                ctrl = ArtNetController(
                    host=cfg.get("host", ""),
                    universe=int(cfg.get("universe", 0)),
                    subnet=int(cfg.get("subnet", 0)),
                    net=int(cfg.get("net", 0))
                )
                if action == "on":
                    scene_raw = cfg.get("scene_on", {})
                    scene = {int(k): int(v) for k, v in scene_raw.items()} if isinstance(scene_raw, dict) else scene_raw
                    ctrl.send_scene(scene)
                else:
                    ctrl.blackout()
                return True, "ArtNet 전송 완료"

            elif dtype == "usb_dmx":
                ctrl = UsbDmxController(
                    port=cfg.get("port", ""),
                    universe=int(cfg.get("universe", 0))
                )
                if action == "on":
                    scene_raw = cfg.get("scene_on", {})
                    scene = {int(k): int(v) for k, v in scene_raw.items()} if isinstance(scene_raw, dict) else scene_raw
                    ctrl.send_scene(scene)
                else:
                    ctrl.blackout()
                ctrl.close()
                return True, "USB DMX 전송 완료"

            elif dtype == "osc":
                ctrl = OscController(
                    host=cfg.get("host", ""),
                    port=int(cfg.get("port", 8000))
                )
                address = cfg.get("address", "/exhibition")
                on_val = cfg.get("on_value", 1)
                off_val = cfg.get("off_value", 0)
                return ctrl.send(address, on_val if action == "on" else off_val)

            else:
                return False, f"알 수 없는 디바이스 타입: {dtype}"

        except ConnectionRefusedError:
            return False, f"연결 거부됨 → 기기가 꺼져있거나 네트워크를 확인하세요. (타입: {dtype})"
        except OSError as e:
            if e.errno in (10061, 111):
                return False, f"연결 거부됨 ({dtype}) → 기기 전원 및 네트워크를 확인하세요."
            if e.errno in (10060, 110):
                return False, f"연결 시간 초과 ({dtype}) → IP 주소를 확인하세요."
            return False, f"네트워크 오류 ({dtype}): {e}"
        except Exception as e:
            return False, str(e)

    def run_device_now(self, device: dict, action: str):
        """Manually trigger a device action immediately."""
        return self._execute_device(device, action)

    def run_zone_now(self, zone_id: int, action: str):
        """Manually trigger all devices in a zone immediately."""
        devices = self.db.get_devices_by_zone(zone_id)
        results = []
        for d in devices:
            ok, msg = self._execute_device(d, action)
            results.append((d["name"], ok, msg))
        return results
