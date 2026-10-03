#!/usr/bin/env python3
"""从有文本层的 PDF 按字体大小提取标题层级，生成 titles.txt（供 bookmarks.py 使用）。

原理：pymupdf 读取每行文字的字号，显著大于正文字号（默认 ≥1.15 倍）的行视为标题；
标题字号从大到小聚类，依次映射为级别 1、2、3…。自动过滤噪声：页眉页脚（大量重复
出现的行）、纯页码行、目录条目（含点线引导符的行）。

适用边界：要求排版用"字号"区分层级（教材、报告、书籍均属此类）；若标题只加粗
不加大则无法识别，请改走 skill 的视觉转录路径。

用法:
  python extract_titles.py 书.pdf [--out titles.txt] [--min-ratio 1.15] [--max-level N] [--debug]

输出: 打印提取结果与统计；--out 指定时写出 titles.txt（级别|标题|物理页码）。
无文本层（扫描版）时明确报错——那种 PDF 请走 skill 的视觉转录路径。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter


def _require_deps() -> None:
    """启动自检：硬依赖缺失时打印安装提示并非零退出。"""
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print("缺少硬依赖 pymupdf。安装: pip install pymupdf（需 Python 3.10+）", file=sys.stderr)
        sys.exit(1)


def collect_lines(doc) -> list[dict]:
    """聚合每页每个文本行为 (page, y, size, text)；行内 span 按位置拼接。"""
    lines: list[dict] = []
    for pno in range(doc.page_count):
        d = doc[pno].get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s["text"].strip()]
                if not spans:
                    continue
                spans.sort(key=lambda s: s["bbox"][0])
                size = max(s["size"] for s in spans)
                parts: list[str] = []
                prev_x1 = None
                for s in spans:
                    if prev_x1 is not None and s["bbox"][0] - prev_x1 > 0.25 * size:
                        parts.append(" ")
                    parts.append(s["text"])
                    prev_x1 = s["bbox"][2]
                text = " ".join("".join(parts).split())
                if not text:
                    continue
                lines.append({
                    "page": pno + 1,
                    "y": min(s["bbox"][1] for s in spans),
                    "size": size,
                    "text": text,
                })
    return lines


def is_noise(text: str) -> bool:
    t = text.strip()
    if len(t) < 2:
        return True
    if re.fullmatch(r"[\d\s\-—–·.．/|]+", t):  # 纯页码/分隔符
        return True
    if re.search(r"[.．]{3,}|…{2,}|_{4,}|-{6,}", t):  # 目录条目（点线引导）
        return True
    return False


def drop_repeated(lines: list[dict], page_count: int) -> list[dict]:
    """去掉页眉页脚：跨大量页面重复出现的行。"""
    counter: Counter[str] = Counter(l["text"] for l in lines)
    thresh = max(5, int(page_count * 0.25))
    repeated = {t for t, c in counter.items() if c >= thresh}
    return [l for l in lines if l["text"] not in repeated]


def body_size(lines: list[dict]) -> float:
    """正文字号 = 按字符数加权的最常见字号。"""
    c: Counter[float] = Counter()
    for l in lines:
        c[round(l["size"], 1)] += len(l["text"])
    return c.most_common(1)[0][0] if c else 0.0


def cluster_levels(sizes: set[float], tol: float = 0.8) -> dict[float, int]:
    """字号从大到小聚类，映射为级别 1、2、3…。"""
    level_of: dict[float, int] = {}
    groups: list[list[float]] = []
    for s in sorted(sizes, reverse=True):
        if groups and abs(groups[-1][-1] - s) <= tol:
            groups[-1].append(s)
        else:
            groups.append([s])
    for i, g in enumerate(groups):
        for s in g:
            level_of[s] = i + 1
    return level_of


def main() -> None:
    _require_deps()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--out", help="titles.txt 输出路径（级别|标题|物理页码）")
    ap.add_argument("--min-ratio", type=float, default=1.15, help="标题字号 ≥ 正文字号×该倍数（默认 1.15）")
    ap.add_argument("--max-level", type=int, help="只保留级别 <= N")
    ap.add_argument("--debug", action="store_true", help="打印字号分布，便于调参")
    args = ap.parse_args()

    import pymupdf

    doc = pymupdf.open(args.pdf)
    if not any(len(doc[i].get_text().strip()) for i in range(min(10, doc.page_count))):
        raise SystemExit("错误: 该 PDF 无文本层（扫描版）。请改用 skill 的视觉转录路径（分支 A/B）。")

    lines = drop_repeated(collect_lines(doc), doc.page_count)
    bsize = body_size(lines)
    if args.debug:
        hist = Counter(round(l["size"], 1) for l in lines)
        print(f"[debug] 正文字号 {bsize}；字号分布(字号:字符数):",
              dict(sorted(hist.items(), reverse=True)[:12]))

    cands = [l for l in lines
             if l["size"] >= bsize * args.min_ratio and not is_noise(l["text"])
             and len(l["text"]) <= 80]
    if not cands:
        raise SystemExit("错误: 未提取到任何标题。可尝试调低 --min-ratio，"
                         "或该 PDF 的标题不靠字号区分（请走视觉转录路径）。")
    level_of = cluster_levels({round(l["size"], 1) for l in cands})

    rows: list[tuple[int, str, int]] = []
    seen: set[tuple[str, int]] = set()
    for l in sorted(cands, key=lambda l: (l["page"], l["y"], l["size"]), reverse=False):
        level = level_of[round(l["size"], 1)]
        if args.max_level is not None and level > args.max_level:
            continue
        key = (l["text"], l["page"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((level, l["text"], l["page"]))
    doc.close()

    print(f"提取到 {len(rows)} 条标题（正文字号 {bsize}，倍数阈值 {args.min_ratio}）：")
    for level, text, page in rows:
        print(f"{'  ' * (level - 1)}[{level}] {text} -> P{page}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for level, text, page in rows:
                f.write(f"{level}|{text}|{page}\n")
        print(f"已写出: {args.out}")


if __name__ == "__main__":
    main()
