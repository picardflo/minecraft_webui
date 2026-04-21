import struct
import zlib
from pathlib import Path

_M_GLYPH = [
    [1, 0, 0, 0, 1],
    [1, 1, 0, 1, 1],
    [1, 0, 1, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
]
_GLYPH_W, _GLYPH_H = 5, 7
_BG = (23, 24, 28)    # #17181c
_FG = (90, 171, 40)   # #5aab28


def _pixel(x: int, y: int, size: int) -> tuple[int, int, int]:
    scale = max(1, size // 10)
    gw, gh = _GLYPH_W * scale, _GLYPH_H * scale
    ox, oy = (size - gw) // 2, (size - gh) // 2
    lx, ly = x - ox, y - oy
    if 0 <= lx < gw and 0 <= ly < gh:
        if _M_GLYPH[ly // scale][lx // scale]:
            return _FG
    return _BG


def _make_png(size: int) -> bytes:
    raw = b"".join(
        b"\x00" + b"".join(bytes(_pixel(x, y, size)) for x in range(size))
        for y in range(size)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ensure_pwa_icons() -> None:
    icons_dir = Path("static/icons")
    icons_dir.mkdir(exist_ok=True)
    for size in (192, 512):
        p = icons_dir / f"icon-{size}.png"
        if not p.exists():
            p.write_bytes(_make_png(size))
