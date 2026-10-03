#!/usr/bin/env python3
"""扫描版 PDF 结构扫描工具（无目录页时的标题定位辅助）。

子命令:
  scan    全页色彩扫描，输出每页饱和度指标，标记章扉页候选（整页彩色分隔页）
  sheets  按页码范围生成 3x3 缩略图网格（红框 + 页码标签），供目视查找节起始页

用法:
  python structure_scan.py scan 书.pdf [--dpi 25] [--threshold 0.5]
  python structure_scan.py sheets 书.pdf --pages 4-111 --outdir _render [--dpi 100] [--cols 3]

页码均为 1-based PDF 物理页码。scan 需要范围内逐页渲染，约百页的书几秒内完成；
sheets 输出 sheetNN_pXXX-pYYY.png，人工/模型逐张目视即可。
"""
from __future__ import annotations

import argparse
import os
import sys


def parse_pages(spec: str, page_count: int) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
        else:
            lo = hi = int(part)
        if lo < 1 or hi > page_count or lo > hi:
            raise SystemExit(f"页码范围无效: {part}（PDF 共 {page_count} 页）")
        pages.extend(range(lo, hi + 1))
    return pages


def page_stats(pix) -> tuple[float, float]:
    """返回 (平均饱和度, 彩色像素占比)。优先用 numpy，缺失时纯 Python 抽样。"""
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
        sat = a.max(axis=2) - a.min(axis=2)
        return float(sat.mean()), float((sat > 40).mean())
    samples, n = pix.samples, pix.n
    step = n * 4  # 每 4 个像素抽 1 个
    total = count = seen = 0
    for j in range(0, len(samples) - n + 1, step):
        r, g, b = samples[j], samples[j + 1], samples[j + 2]
        s = max(r, g, b) - min(r, g, b)
        total += s
        if s > 40:
            count += 1
        seen += 1
    return total / seen, count / seen


def cmd_scan(args) -> None:
    import pymupdf

    doc = pymupdf.open(args.pdf)
    print(f"{'页':>4} {'平均饱和度':>10} {'彩色占比':>9}  备注")
    for i in range(doc.page_count):
        pix = doc[i].get_pixmap(dpi=args.dpi)
        mean_sat, frac = page_stats(pix)
        note = ""
        if frac >= args.threshold:
            note = "<== 章扉页候选（整页彩色分隔页）"
        print(f"{i + 1:>4} {mean_sat:>10.1f} {frac:>9.3f}  {note}")
    doc.close()


def cmd_sheets(args) -> None:
    import io

    import pymupdf
    from PIL import Image, ImageDraw

    doc = pymupdf.open(args.pdf)
    pages = parse_pages(args.pages, doc.page_count)
    os.makedirs(args.outdir, exist_ok=True)
    cols, per = args.cols, args.cols * 3
    made = 0
    for s in range(0, len(pages), per):
        chunk = pages[s : s + per]
        imgs = []
        for pg in chunk:
            pix = doc[pg - 1].get_pixmap(dpi=args.dpi)
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            im = im.resize((im.width // 2, im.height // 2))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, im.width - 1, im.height - 1], outline=(255, 0, 0), width=3)
            d.rectangle([0, 0, 70, 34], fill=(255, 0, 0))
            d.text((6, 6), f"P{pg}", fill=(255, 255, 255))
            imgs.append(im)
        cw = max(im.width for im in imgs)
        ch = max(im.height for im in imgs)
        sheet = Image.new("RGB", (cols * cw, 3 * ch), (60, 60, 60))
        for k, im in enumerate(imgs):
            sheet.paste(im, ((k % cols) * cw, (k // cols) * ch))
        fp = os.path.join(args.outdir, f"sheet{s // per + 1:02d}_p{chunk[0]:03d}-{chunk[-1]:03d}.png")
        sheet.save(fp)
        made += 1
        print(fp, sheet.size)
    doc.close()
    print(f"共 {made} 张网格图，覆盖 {len(pages)} 页 -> {args.outdir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("scan", help="全页色彩扫描，标记章扉页候选")
    p1.add_argument("pdf")
    p1.add_argument("--dpi", type=int, default=25)
    p1.add_argument("--threshold", type=float, default=0.5, help="彩色占比阈值，默认 0.5")
    p1.set_defaults(func=cmd_scan)

    p2 = sub.add_parser("sheets", help="生成 3x3 缩略图网格")
    p2.add_argument("pdf")
    p2.add_argument("--pages", required=True, help="页码范围，如 4-111 或 4,9,13-20")
    p2.add_argument("--outdir", default="_render")
    p2.add_argument("--dpi", type=int, default=100)
    p2.add_argument("--cols", type=int, default=3)
    p2.set_defaults(func=cmd_sheets)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
