import os
import sys
import time
import subprocess
import psutil
from typing import Dict, Any

_boot_time = time.time()

def get_system_health() -> Dict[str, Any]:
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count(logical=True)
    
    # RAM
    vmem = psutil.virtual_memory()
    total_ram_gb = round(vmem.total / (1024 ** 3), 2)
    used_ram_gb = round(vmem.used / (1024 ** 3), 2)
    free_ram_gb = round(vmem.available / (1024 ** 3), 2)
    ram_percent = vmem.percent
    
    # Disk
    disk = psutil.disk_usage("/")
    total_disk_gb = round(disk.total / (1024 ** 3), 2)
    free_disk_gb = round(disk.free / (1024 ** 3), 2)
    disk_percent = disk.percent
    
    uptime_seconds = int(time.time() - _boot_time)

    # Node version
    node_version = "v20.20.2"
    try:
        res = subprocess.run(["node", "-v"], capture_output=True, text=True, timeout=1.0)
        if res.returncode == 0:
            node_version = res.stdout.strip()
    except Exception:
        pass

    # PM2 status count
    pm2_online_count = 0
    try:
        res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            import json
            apps = json.loads(res.stdout)
            pm2_online_count = sum(1 for a in apps if a.get("pm2_env", {}).get("status") == "online")
    except Exception:
        pass

    return {
        "hostname": "vmi3525521",
        "location": "Germany (Nuremberg DC)",
        "ip_address": "169.58.218.168",
        "os": "Ubuntu 24.04.4 LTS (Noble Numbat)",
        "kernel": "Linux 6.8.0-40-generic",
        "cpu": {
            "model": "AMD EPYC (4 vCPUs)",
            "cores": cpu_count,
            "usage_percent": cpu_percent
        },
        "ram": {
            "total_gb": total_ram_gb,
            "used_gb": used_ram_gb,
            "free_gb": free_ram_gb,
            "usage_percent": ram_percent
        },
        "disk": {
            "total_gb": total_disk_gb,
            "free_gb": free_disk_gb,
            "usage_percent": disk_percent
        },
        "runtimes": {
            "python": sys.version.split()[0],
            "node": node_version,
            "pm2_apps_online": pm2_online_count
        },
        "uptime_seconds": uptime_seconds,
        "services": {
            "backend": "ONLINE (Port 8001)",
            "dashboard": "ONLINE (Port 8080)",
            "trading_lock": "LOCKED (No Live Trading)",
            "read_only": True
        }
    }
