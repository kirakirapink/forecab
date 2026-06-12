#!/usr/bin/env python3
"""PWA用アイコンPNGを標準ライブラリだけで生成する（タクシー琥珀×市松×レーダー円環）。

使い方:
    python3 tools/make_icon.py   # web/icon-180.png と web/icon-512.png を生成
"""
import struct
import zlib
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

AMBER = (245, 179, 1)
BLACK = (18, 18, 22)
WHITE = (240, 240, 240)


def write_png(path, width, height, pixels):
    raw = b"".join(b"\x00" + b"".join(struct.pack("BBB", *p) for p in row) for row in pixels)

    def chunk(typ, data):
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def make_icon(size):
    cell = max(8, size // 15)        # 市松の1マス
    band = cell * 2                  # 上下の市松帯の高さ
    cx = cy = size / 2
    rings = [                        # レーダー風の黒い円環（外径比, 内径比）
        (0.36, 0.31),
        (0.22, 0.17),
        (0.08, 0.0),
    ]

    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            in_band = y < band or y >= size - band
            if in_band:
                row.append(BLACK if ((x // cell) + (y // cell)) % 2 == 0 else WHITE)
                continue
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / size
            color = AMBER
            for outer, inner in rings:
                if inner <= d <= outer:
                    color = BLACK
                    break
            row.append(color)
        pixels.append(row)
    return pixels


def main():
    for size in (180, 512):
        out = WEB / f"icon-{size}.png"
        write_png(out, size, size, make_icon(size))
        print(f"OK: {out}")


if __name__ == "__main__":
    main()
