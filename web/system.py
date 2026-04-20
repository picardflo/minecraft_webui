import psutil
from config import settings

if settings.host_proc:
    psutil.PROCFS_PATH = settings.host_proc


def get_system_metrics() -> dict:
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "cpu": round(psutil.cpu_percent(interval=0.5), 1),
        "ram_pct": round(ram.percent, 1),
        "ram_used_gb": round(ram.used / 1024**3, 1),
        "ram_total_gb": round(ram.total / 1024**3, 1),
        "swap_pct": round(swap.percent, 1),
        "swap_used_gb": round(swap.used / 1024**3, 1),
        "swap_total_gb": round(swap.total / 1024**3, 1),
    }
