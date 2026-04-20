import os
import time
from pathlib import Path

import psutil

from config import settings

if settings.host_proc:
    psutil.PROCFS_PATH = settings.host_proc

_prev_net  = None
_prev_disk = None
_prev_ts   = None


def get_system_metrics() -> dict:
    global _prev_net, _prev_disk, _prev_ts

    ram  = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Disk usage
    try:
        disk = psutil.disk_usage(settings.host_srv)
        disk_pct      = round(disk.percent, 1)
        disk_used_gb  = round(disk.used  / 1024**3, 1)
        disk_total_gb = round(disk.total / 1024**3, 1)
    except Exception:
        disk_pct = disk_used_gb = disk_total_gb = 0

    # Network & disk I/O rates (KB/s)
    now      = time.monotonic()
    net_c    = psutil.net_io_counters()
    disk_c   = psutil.disk_io_counters()
    net_in = net_out = disk_read = disk_write = 0.0
    if _prev_net and _prev_ts:
        dt = now - _prev_ts
        if dt > 0:
            net_in    = max(0, round((net_c.bytes_recv  - _prev_net.bytes_recv)  / dt / 1024, 1))
            net_out   = max(0, round((net_c.bytes_sent  - _prev_net.bytes_sent)  / dt / 1024, 1))
            if _prev_disk and disk_c:
                disk_read  = max(0, round((disk_c.read_bytes  - _prev_disk.read_bytes)  / dt / 1024, 1))
                disk_write = max(0, round((disk_c.write_bytes - _prev_disk.write_bytes) / dt / 1024, 1))
    _prev_net  = net_c
    _prev_disk = disk_c
    _prev_ts   = now

    # CLOCK_BOOTTIME = uptime du host Proxmox (bypass namespaces).
    # PID 1 de /host/proc = init du LXC ; son starttime (jiffies depuis boot Proxmox)
    # soustrait à CLOCK_BOOTTIME donne l'uptime réel du LXC.
    try:
        proxmox_uptime = time.clock_gettime(time.CLOCK_BOOTTIME)
        proc_root = settings.host_proc or "/proc"
        stat_text = Path(proc_root + "/1/stat").read_text()
        # starttime = champ 22 ; parse après la comm "(…)" qui peut contenir des espaces
        after_comm = stat_text[stat_text.rfind(")") + 2:]
        starttime_ticks = int(after_comm.split()[19])  # champ 22 → index 19 après comm
        try:
            clk_tck = os.sysconf("SC_CLK_TCK")
        except Exception:
            clk_tck = 100
        vm_uptime_s = max(0, int(proxmox_uptime - starttime_ticks / clk_tck))
    except Exception:
        vm_uptime_s = 0

    return {
        "cpu":           round(psutil.cpu_percent(interval=0.5), 1),
        "ram_pct":       round(ram.percent, 1),
        "ram_used_gb":   round(ram.used  / 1024**3, 1),
        "ram_total_gb":  round(ram.total / 1024**3, 1),
        "swap_pct":      round(swap.percent, 1),
        "swap_used_gb":  round(swap.used  / 1024**3, 1),
        "swap_total_gb": round(swap.total / 1024**3, 1),
        "disk_pct":      disk_pct,
        "disk_used_gb":  disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "net_in_kbs":    net_in,
        "net_out_kbs":   net_out,
        "disk_read_kbs": disk_read,
        "disk_write_kbs":disk_write,
        "vm_uptime_s":   vm_uptime_s,
    }
