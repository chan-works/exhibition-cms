import socket
import struct
import threading
import ipaddress
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable


def get_local_subnets() -> List[str]:
    """Return list of local subnet prefixes like '192.168.1'."""
    subnets = set()
    try:
        hostname = socket.gethostname()
        for ip in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = ip[4][0]
            if not addr.startswith("127."):
                parts = addr.split(".")
                subnets.add(".".join(parts[:3]))
    except Exception:
        pass
    # fallback
    if not subnets:
        subnets.add("192.168.1")
    return list(subnets)


def ping(ip: str, timeout: float = 0.5) -> bool:
    """Ping an IP. Returns True if alive."""
    try:
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 1)
        return result.returncode == 0
    except Exception:
        return False


def check_pjlink(ip: str, port: int = 4352, timeout: float = 1.0) -> bool:
    """Check if PJLink port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_mac_from_arp(ip: str) -> str:
    """Try to get MAC from ARP table."""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["arp", "-a", ip], capture_output=True, text=True, timeout=3)
            for line in result.stdout.splitlines():
                if ip in line:
                    parts = line.split()
                    for p in parts:
                        if "-" in p and len(p) == 17:
                            return p.replace("-", ":").upper()
        else:
            result = subprocess.run(["arp", "-n", ip], capture_output=True, text=True, timeout=3)
            for line in result.stdout.splitlines():
                if ip in line:
                    parts = line.split()
                    for p in parts:
                        if ":" in p and len(p) == 17:
                            return p.upper()
    except Exception:
        pass
    return ""


def get_hostname(ip: str) -> str:
    """Reverse DNS lookup."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


class NetworkScanner:
    """Scan local network for PCs and PJLink projectors."""

    def __init__(self, progress_callback: Callable = None):
        self.progress_callback = progress_callback
        self._stop = False

    def stop(self):
        self._stop = True

    def scan(self, subnet: str = None, max_workers: int = 50) -> Dict[str, List[dict]]:
        """
        Scan subnet for devices.
        Returns dict with keys 'computers' and 'pjlink'.
        """
        self._stop = False
        subnets = [subnet] if subnet else get_local_subnets()

        computers = []
        pjlink_devices = []
        all_ips = []

        for sub in subnets:
            for i in range(1, 255):
                all_ips.append(f"{sub}.{i}")

        total = len(all_ips)
        done = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._probe, ip): ip for ip in all_ips}
            for future in as_completed(futures):
                if self._stop:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                done += 1
                if self.progress_callback:
                    self.progress_callback(done, total)
                result = future.result()
                if result:
                    if result.get("pjlink"):
                        pjlink_devices.append(result)
                    else:
                        computers.append(result)

        return {"computers": computers, "pjlink": pjlink_devices}

    def _probe(self, ip: str) -> dict:
        if self._stop:
            return None
        alive = ping(ip, timeout=0.4)
        if not alive:
            return None

        has_pjlink = check_pjlink(ip)
        mac = get_mac_from_arp(ip)
        hostname = get_hostname(ip)

        return {
            "ip": ip,
            "hostname": hostname,
            "mac": mac,
            "pjlink": has_pjlink,
        }
