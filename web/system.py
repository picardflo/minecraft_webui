import os
import time
from pathlib import Path

import psutil

from config import settings

if settings.host_proc:
    psutil.PROCFS_PATH = settings.host_proc

# ── Mémoire de la machine ───────────────────────────────────────────────────
# Trois environnements à couvrir, avec la même sortie : la mémoire de la MACHINE
# qui héberge le serveur Minecraft.
#
#   Serveur physique / VM KVM — /proc/meminfo (via /host/proc) décrit déjà la
#       machine entière : psutil est exact. Le cgroup racine n'expose pas
#       memory.current (fichier réservé aux cgroups enfants), la lecture cgroup
#       rend donc None d'elle-même. En cgroup v1 le fichier racine existe et
#       décrit lui aussi la machine entière : les deux sources concordent.
#
#   LXC Proxmox — lxcfs répond à /proc/meminfo EN FONCTION DU CGROUP DU LECTEUR.
#       Le lecteur est le process Python du conteneur `web`, dans un cgroup
#       imbriqué : psutil renvoie la conso du conteneur (~51 Mio) et non celle du
#       LXC. Monter le /proc de l'hôte n'y change rien — c'est l'identité du
#       lecteur qui compte, pas le chemin du fichier. Le cgroup racine vu depuis
#       le LXC EST celui du LXC : memory.current y donne la bonne valeur.
#
# Le seul mode de panne connu est donc la SOUS-estimation (un cgroup imbriqué ne
# voit qu'une fraction de la machine) : on retient la plus grande des deux
# lectures, ce qui reste correct dans les trois cas même si le montage
# /host/cgroup est absent, partiel ou mal ciblé.
#
# `total` vient toujours de psutil : il est exact partout — RAM physique sur
# bare-metal, RAM de la VM en KVM, limite du conteneur en LXC (via lxcfs).


def _stat_field(path: Path, key: str) -> int:
    """Valeur d'une clé d'un fichier memory.stat, 0 si absente ou illisible."""
    try:
        for line in path.read_text().splitlines():
            name, _, value = line.partition(" ")
            if name == key:
                return int(value)
    except Exception:
        pass
    return 0


def _cgroup_used() -> int | None:
    """Mémoire utilisée du cgroup racine hôte, ou None si indisponible."""
    base = Path(settings.host_cgroup)
    # (fichier d'usage, fichier de stats, clé du cache réclamable)
    layouts = (
        ("memory.current", "memory.stat", "inactive_file"),                          # v2
        ("memory/memory.usage_in_bytes", "memory/memory.stat", "total_inactive_file"),  # v1
    )
    for usage, stat, cache_key in layouts:
        try:
            used = int((base / usage).read_text().split()[0])
        except Exception:
            continue
        # L'usage cgroup inclut le cache de fichiers réclamable ; on le retire
        # pour obtenir une valeur comparable au « used » de `free`
        # (convention docker stats / cAdvisor).
        return max(0, used - _stat_field(base / stat, cache_key))
    return None


def _memory() -> tuple[int, int]:
    """(utilisé, total) en octets — physique, VM ou LXC."""
    ram = psutil.virtual_memory()
    # total - available plutôt que .used : MemAvailable tient compte du cache
    # réclamable et reflète mieux la mémoire réellement indisponible.
    used, total = ram.total - ram.available, ram.total

    cgroup_used = _cgroup_used()
    if cgroup_used is not None:
        used = max(used, cgroup_used)

    return max(0, min(used, total)), total


# État partagé SSE (fenêtre ~5s)
_prev_net  = None
_prev_disk = None
_prev_ts   = None

# État indépendant pour le recorder (fenêtre ~5min, pas de race condition avec SSE)
_prev_net_rec  = None
_prev_disk_rec = None
_prev_ts_rec   = None


def _compute_metrics(prev_net, prev_disk, prev_ts) -> tuple[dict, object, object, float]:
    """Calcule les métriques et renvoie (résultats, net_c, disk_c, now)."""
    swap = psutil.swap_memory()

    ram_used, ram_total = _memory()
    ram_pct = round(ram_used / ram_total * 100, 1) if ram_total else 0.0

    try:
        disk = psutil.disk_usage(settings.host_srv)
        disk_pct      = round(disk.percent, 1)
        disk_used_gb  = round(disk.used  / 1024**3, 1)
        disk_total_gb = round(disk.total / 1024**3, 1)
    except Exception:
        disk_pct = disk_used_gb = disk_total_gb = 0

    now    = time.monotonic()
    net_c  = psutil.net_io_counters()
    disk_c = psutil.disk_io_counters()
    net_in = net_out = disk_read = disk_write = 0.0
    if prev_net and prev_ts:
        dt = now - prev_ts
        if dt > 0:
            net_in    = max(0, round((net_c.bytes_recv  - prev_net.bytes_recv)  / dt / 1024, 1))
            net_out   = max(0, round((net_c.bytes_sent  - prev_net.bytes_sent)  / dt / 1024, 1))
            if prev_disk and disk_c:
                disk_read  = max(0, round((disk_c.read_bytes  - prev_disk.read_bytes)  / dt / 1024, 1))
                disk_write = max(0, round((disk_c.write_bytes - prev_disk.write_bytes) / dt / 1024, 1))

    try:
        proxmox_uptime = time.clock_gettime(time.CLOCK_BOOTTIME)
        proc_root = settings.host_proc or "/proc"
        stat_text = Path(proc_root + "/1/stat").read_text()
        after_comm = stat_text[stat_text.rfind(")") + 2:]
        starttime_ticks = int(after_comm.split()[19])
        try:
            clk_tck = os.sysconf("SC_CLK_TCK")
        except Exception:
            clk_tck = 100
        vm_uptime_s = max(0, int(proxmox_uptime - starttime_ticks / clk_tck))
    except Exception:
        vm_uptime_s = 0

    metrics = {
        "cpu":           round(psutil.cpu_percent(interval=0.5), 1),
        "ram_pct":       ram_pct,
        "ram_used_gb":   round(ram_used  / 1024**3, 1),
        "ram_total_gb":  round(ram_total / 1024**3, 1),
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
    return metrics, net_c, disk_c, now


def get_system_metrics() -> dict:
    """SSE dashboard — fenêtre courte (~5s), état partagé _prev_*."""
    global _prev_net, _prev_disk, _prev_ts
    metrics, net_c, disk_c, now = _compute_metrics(_prev_net, _prev_disk, _prev_ts)
    _prev_net, _prev_disk, _prev_ts = net_c, disk_c, now
    return metrics


def get_system_metrics_for_record() -> dict:
    """Metrics recorder — état indépendant (~5min), pas de race avec SSE."""
    global _prev_net_rec, _prev_disk_rec, _prev_ts_rec
    metrics, net_c, disk_c, now = _compute_metrics(_prev_net_rec, _prev_disk_rec, _prev_ts_rec)
    _prev_net_rec, _prev_disk_rec, _prev_ts_rec = net_c, disk_c, now
    return metrics
