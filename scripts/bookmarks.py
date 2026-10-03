#!/usr/bin/env python3
"""书签导出/写入工具（pdf-bookmarks skill 的功能 1/2/3）。

输入（二选一）:
  titles.txt  转录的标题清单，每行 `级别|标题|物理页码`，# 为注释、空行忽略
  book.csv    csvtopdfbkmk 样式 CSV（表头 级别,标题,物理页码，utf-8-sig 读取）

子命令:
  export <input> [--csv [OUT.csv]] [--xml [OUT.xml]] [--level N] [--pdf PDF]
      功能 1/2：导出书签 CSV 和/或福昕书签 XML。--csv/--xml 带路径则直接写出；
      不带值则在数据校验通过后弹出系统"另存为"对话框（CSV 默认名 <PDF名>_书签.csv，
      XML 默认名 <PDF名>_书签_N级.xml，--pdf 未给时用输入文件名；取消则该文件不写出）。
      --level 只截断 XML 深度（整枝丢弃），CSV 始终保留全部层级（它才是数据源）。
      --pdf 提供时补查页码是否越界。
  write <pdf> <input> [--out OUT.pdf] [--level N] [--in-place]
      功能 3：写入书签。默认不修改原始文件——加签完成后弹出系统"另存为"对话框，
      默认文件名 <stem>_书签版.pdf、默认目录为原文件所在目录；取消则不写出任何文件。
      --out 指定路径则不弹框直接写出；--in-place 原位写入（先备份）。写后自检。
  parity <csv> <xml> [--level N] [--tool-dir DIR]
      用《csvtopdfbkmk》的 converter 从 csv 重新生成 XML，与给定 xml 做字节级比对
      （round-trip 验收）。可选功能：--tool-dir 指定工具源码根目录，或环境变量
      CSVTOPDFBKMK_DIR；未提供且找不到时给出提示并失败，不影响 export/write。

页码一律为 1-based PDF 物理页码（封面 = 1），不是印刷页码。
XML 生成路径与 csvtopdfbkmk/src/converter.py 完全一致（ElementTree + minidom
toprettyxml，4 空格缩进，UTF-8 无 BOM），同机输出字节级一致。
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from xml.dom import minidom
from xml.etree.ElementTree import Element, tostring

REQUIRED_FIELDS = {"级别", "标题", "物理页码"}
DIALOG = "\x00save-dialog"  # --csv/--xml 不带值时的哨兵：弹出另存为对话框


def _require_deps() -> None:
    """启动自检：硬依赖缺失时打印安装提示并非零退出；软依赖（numpy/tkinter）缺失时
    在用到处自动降级并提示。"""
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print("缺少硬依赖 pymupdf。安装: pip install pymupdf（需 Python 3.10+）", file=sys.stderr)
        sys.exit(1)


class BookmarkError(Exception):
    pass


class Node:
    __slots__ = ("title", "page", "level", "children")

    def __init__(self, title: str, page: int, level: int):
        self.title = title
        self.page = page
        self.level = level
        self.children: list[Node] = []


# ---------- 输入解析与校验 ----------

def _to_int(value: str, lineno: int, field: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise BookmarkError(f"第 {lineno} 行「{field}」值无效: {value}") from None
    if n < 1:
        raise BookmarkError(f"第 {lineno} 行「{field}」值无效: {value}")
    return n


def load_titles(path: str) -> list[tuple[int, str, int]]:
    if path.lower().endswith(".csv"):
        return load_csv(path)
    return load_pipes(path)


def load_pipes(path: str) -> list[tuple[int, str, int]]:
    rows: list[tuple[int, str, int]] = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                raise BookmarkError(f"第 {lineno} 行格式无效（应为 级别|标题|物理页码）: {line}")
            level = _to_int(parts[0], lineno, "级别")
            title = parts[1]
            page = _to_int(parts[2], lineno, "物理页码")
            if not title:
                raise BookmarkError(f"第 {lineno} 行「标题」为空")
            rows.append((level, title, page))
    if not rows:
        raise BookmarkError("titles 中没有数据行")
    return rows


def load_csv(path: str) -> list[tuple[int, str, int]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn for fn in (reader.fieldnames or []) if fn is not None]
        missing = REQUIRED_FIELDS - set(fieldnames)
        if missing:
            raise BookmarkError(f"缺少必填字段: {', '.join(sorted(missing))}")
        rows: list[tuple[int, str, int]] = []
        for i, row in enumerate(reader, start=2):
            level_val = (row.get("级别") or "").strip()
            title_val = (row.get("标题") or "").strip()
            page_val = (row.get("物理页码") or "").strip()
            if not level_val:
                raise BookmarkError(f"第 {i} 行「级别」为空")
            if not title_val:
                raise BookmarkError(f"第 {i} 行「标题」为空")
            if not page_val:
                raise BookmarkError(f"第 {i} 行「物理页码」为空")
            level = _to_int(level_val, i, "级别")
            page = _to_int(page_val, i, "物理页码")
            rows.append((level, title_val, page))
    if not rows:
        raise BookmarkError("CSV 中没有数据行")
    return rows


def extra_checks(rows: list[tuple[int, str, int]], page_count: int | None) -> list[str]:
    """csvtopdfbkmk 不做的检查：级别跳级、页码回跳、页码越界。返回警告列表。"""
    warns: list[str] = []
    for idx, (level, _title, page) in enumerate(rows, start=1):
        if idx > 1:
            prev_level, _t, prev_page = rows[idx - 2]
            if level > prev_level + 1:
                warns.append(f"第 {idx} 条级别从 {prev_level} 跳到 {level}（应逐级递进）")
            if page < prev_page:
                warns.append(f"第 {idx} 条页码回跳（{prev_page} → {page}）")
    if page_count is not None:
        for idx, (_l, _t, page) in enumerate(rows, start=1):
            if page > page_count:
                warns.append(f"第 {idx} 条页码 {page} 超出 PDF 页数 {page_count}")
    return warns


# ---------- 树构建 / 截断 / XML 生成（与 csvtopdfbkmk converter.py 一致）----------

def build_tree(rows: list[tuple[int, str, int]]) -> list[Node]:
    roots: list[Node] = []
    stack: list[Node] = []
    for level, title, page in rows:
        node = Node(title, page, level)
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def truncate(nodes: list[Node], max_depth: int) -> list[Node]:
    """保留级别 <= max_depth 的节点，更深层级连同后代整体丢弃。"""
    result: list[Node] = []
    for node in nodes:
        if node.level > max_depth:
            continue
        copy = Node(node.title, node.page, node.level)
        copy.children = truncate(node.children, max_depth)
        result.append(copy)
    return result


def build_xml(nodes: list[Node]) -> str:
    root = Element("BOOKMARKS")

    def populate(parent: Element, items: list[Node]) -> None:
        for node in items:
            el = Element(
                "ITEM",
                attrib={
                    "NAME": node.title,
                    "PAGE": str(node.page),
                    "FITETYPE": "Fit",
                    "INDENT": str(node.level - 1),
                },
            )
            populate(el, node.children)
            parent.append(el)

    populate(root, nodes)
    xml_str = minidom.parseString(tostring(root, encoding="UTF-8")).toprettyxml(
        indent="    ", encoding="UTF-8"
    )
    return xml_str.decode("UTF-8")


def write_csv(path: str, rows: list[tuple[int, str, int]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["级别", "标题", "物理页码"])
        w.writerows(rows)


def write_xml(path: str, nodes: list[Node]) -> None:
    content = build_xml(nodes)
    with open(path, "w", encoding="UTF-8") as f:  # 无 BOM；Windows 默认 CRLF，与 converter 一致
        f.write(content)


# ---------- 功能 3：直写 PDF ----------

def ask_save_path(default_path: str) -> str | None:
    """弹出系统"另存为"对话框；返回所选路径，取消返回 None。tkinter 不可用时退回默认路径。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:  # 无 tkinter、无显示环境等（tkinter 为软依赖）
        msg = f"无法打开保存对话框（{e}），改用默认路径: {default_path}"
        if "No module named 'tkinter'" in str(e):
            msg += "（tkinter 缺失：Windows 官方 Python 自带；Linux 需 python3-tk）"
        print(msg)
        return default_path
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)  # 确保对话框置顶可见
        chosen = filedialog.asksaveasfilename(
            title="书签版 PDF 另存为",
            defaultextension=".pdf",
            initialfile=os.path.basename(default_path),
            initialdir=os.path.dirname(os.path.abspath(default_path)) or ".",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
        )
    finally:
        root.destroy()
    return chosen or None


def write_pdf(pdf_path: str, rows: list[tuple[int, str, int]], out: str | None, max_depth: int | None, in_place: bool = False) -> None:
    import pymupdf

    if max_depth is not None:
        rows = [(l, t, p) for l, t, p in rows if l <= max_depth]
        if not rows:
            raise BookmarkError(f"--level {max_depth} 截断后没有剩余书签")
    # PDF 大纲要求：首条级别为 1，且逐级递进（比 XML 路径严格）
    if rows[0][0] != 1:
        raise BookmarkError(f"第 1 条级别为 {rows[0][0]}，PDF 大纲要求首条级别为 1")
    for idx in range(1, len(rows)):
        if rows[idx][0] > rows[idx - 1][0] + 1:
            raise BookmarkError(
                f"第 {idx + 1} 条级别从 {rows[idx - 1][0]} 跳到 {rows[idx][0]}；"
                "PDF 大纲要求逐级递进，请修正输入（跨级回退不受影响）"
            )

    src = pymupdf.open(pdf_path)
    page_count = src.page_count
    over = [(i + 1, p) for i, (_l, _t, p) in enumerate(rows) if p > page_count]
    if over:
        raise BookmarkError(f"页码超出 PDF 页数 {page_count}: {over}")
    entries = [[l, t, p] for l, t, p in rows]

    stem = os.path.splitext(pdf_path)[0]
    tmp_cleanup: list[str] = []
    try:
        if in_place or (out and os.path.abspath(out) == os.path.abspath(pdf_path)):
            # 原位写入（须显式要求）：先备份，再增量保存；被占用时自动转书签版
            backup = stem + "_backup.pdf"
            if os.path.exists(backup):
                print(f"备份已存在，沿用最早一份: {backup}")
            else:
                shutil.copy2(pdf_path, backup)
                print(f"已备份原文件: {backup}")
            target = pdf_path
            try:
                src.set_toc(entries)
                src.save(target, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
                print(f"已原位增量保存: {target}")
            except PermissionError:
                print("原文件被占用（PermissionError），改存书签版……")
                fallback = stem + "_书签版.pdf"
                shutil.copy2(pdf_path, fallback)
                redoc = pymupdf.open(fallback)
                redoc.set_toc(entries)
                tmp = fallback + ".tmp"
                tmp_cleanup.append(tmp)
                redoc.save(tmp, garbage=3, deflate=True)
                redoc.close()
                os.replace(tmp, fallback)
                tmp_cleanup.clear()
                target = fallback
                print(f"已另存书签版: {fallback}（原文件未改动）")
        else:
            # 默认：不修改原始文件。给了 --out 直接写出；否则加签完成后弹"另存为"对话框
            src.set_toc(entries)
            if out:
                target = out
                tmp = target + ".tmp"
                tmp_cleanup.append(tmp)
                src.save(tmp, garbage=3, deflate=True)
                os.replace(tmp, target)
                tmp_cleanup.clear()
                print(f"已写出书签版: {target}（原始文件未改动）")
            else:
                default_path = stem + "_书签版.pdf"
                chosen = ask_save_path(default_path)
                if not chosen:
                    print("已取消保存：未写出任何文件（原始文件未改动）")
                    return
                target = chosen
                src.save(target, garbage=3, deflate=True)
                print(f"已保存: {target}（原始文件未改动）")
    finally:
        for tmp in tmp_cleanup:
            if os.path.exists(tmp):
                os.remove(tmp)
        src.close()

    # 写后自检
    chk = pymupdf.open(target)
    toc = chk.get_toc()
    ok = chk.page_count == page_count and toc == entries
    print(f"自检: 页数 {chk.page_count}（原 {page_count}），书签 {len(toc)} 条（期望 {len(entries)}），逐条比对 {'一致' if toc == entries else '不一致'}")
    if not ok:
        for got, want in zip(toc, entries):
            if got != want:
                print(f"  差异: {got} != {want}")
    chk.close()
    if not ok:
        raise BookmarkError(f"自检未通过，请从备份恢复: {backup}")
    print(f"完成: {target}（共 {len(entries)} 条书签，最大层级 {max(l for l, _t, _p in rows)}）")


# ---------- parity：与 csvtopdfbkmk 输出字节级比对 ----------

def parity(csv_path: str, xml_path: str, max_depth: int | None, tool_dir: str | None = None) -> None:
    tool_dir = tool_dir or os.environ.get("CSVTOPDFBKMK_DIR") or r"E:/csvtopdfbkmk"
    if not os.path.isdir(tool_dir):
        raise BookmarkError(
            f"未找到 csvtopdfbkmk 源码（{tool_dir}）。parity 是可选功能："
            "用 --tool-dir 指定工具源码根目录，或设置环境变量 CSVTOPDFBKMK_DIR；"
            "没有该工具不影响 export/write 的正常使用。"
        )
    sys.path.insert(0, tool_dir)
    try:
        from src.converter import csv_to_bookmark_xml
    finally:
        sys.path.remove(tool_dir)
    if max_depth is None:
        max_depth = max(l for l, _t, _p in load_titles(csv_path))
    ref = xml_path + ".ref.tmp"
    try:
        csv_to_bookmark_xml(csv_path, ref, rows=max_depth)
        with open(xml_path, "rb") as f1, open(ref, "rb") as f2:
            ours, theirs = f1.read(), f2.read()
        if ours == theirs:
            print(f"字节级一致（{len(ours)} 字节，rows={max_depth}）")
        else:
            diff = next((i for i, (a, b) in enumerate(zip(ours, theirs)) if a != b), min(len(ours), len(theirs)))
            print(f"不一致（本工具 {len(ours)} 字节 vs converter {len(theirs)} 字节，首个差异偏移 {diff}）")
            sys.exit(1)
    finally:
        if os.path.exists(ref):
            os.remove(ref)


# ---------- 命令行 ----------

def main() -> None:
    _require_deps()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("export", help="功能 1/2：导出 CSV 和/或 XML（--csv/--xml 不带值时弹保存对话框）")
    p1.add_argument("input", help="titles.txt 或书签 CSV")
    p1.add_argument("--csv", nargs="?", const=DIALOG, default=None, metavar="OUT.csv",
                    help="输出 CSV 路径；不带值则弹出另存为对话框（默认名 <PDF名>_书签.csv）")
    p1.add_argument("--xml", nargs="?", const=DIALOG, default=None, metavar="OUT.xml",
                    help="输出 XML 路径；不带值则弹出另存为对话框（默认名 <PDF名>_书签_N级.xml）")
    p1.add_argument("--level", type=int, help="XML 深度截断（保留级别 <= N；CSV 不受影响）")
    p1.add_argument("--pdf", help="提供时补查页码是否超出该 PDF 页数")
    p1.set_defaults(func=lambda a: run_export(a))

    p2 = sub.add_parser("write", help="功能 3：写入书签（默认不改原件，输出 _书签版）")
    p2.add_argument("pdf")
    p2.add_argument("input")
    p2.add_argument("--out", help="输出路径（默认 <stem>_书签版.pdf）")
    p2.add_argument("--level", type=int, help="写入前截断深度（保留级别 <= N）")
    p2.add_argument("--in-place", action="store_true", help="原位写入原始文件（先备份；默认关闭）")
    p2.set_defaults(func=lambda a: run_write(a))

    p3 = sub.add_parser("parity", help="与 csvtopdfbkmk converter 输出做字节级比对（可选）")
    p3.add_argument("csv")
    p3.add_argument("xml")
    p3.add_argument("--level", type=int, help="比对用的导出层数（默认取 CSV 最大级别）")
    p3.add_argument("--tool-dir", help="csvtopdfbkmk 源码根目录（默认读环境变量 CSVTOPDFBKMK_DIR）")
    p3.set_defaults(func=lambda a: run_parity(a))

    args = ap.parse_args()
    try:
        args.func(args)
    except BookmarkError as e:
        print(f"错误: {e}")
        sys.exit(1)


def run_export(args) -> None:
    if args.csv is None and args.xml is None:
        raise BookmarkError("需要 --csv 和/或 --xml 至少一个输出（不带值则弹出保存对话框）")
    rows = load_titles(args.input)
    page_count = None
    if args.pdf:
        import pymupdf

        doc = pymupdf.open(args.pdf)
        page_count = doc.page_count
        doc.close()
    for warn in extra_checks(rows, page_count):
        print(f"警告: {warn}")

    # 对话框默认名：优先取 --pdf 的名称与目录（符合 <PDF名>_书签.csv 约定），否则用输入文件
    if args.pdf:
        base = os.path.splitext(args.pdf)[0]
        initdir = os.path.dirname(os.path.abspath(args.pdf))
    else:
        base = os.path.splitext(args.input)[0]
        initdir = os.path.dirname(os.path.abspath(args.input))
    stem = os.path.basename(base)

    if args.csv is not None:
        if args.csv == DIALOG:
            target = ask_save_path(os.path.join(initdir, stem + "_书签.csv"))
            if not target:
                print("已取消 CSV 保存：未写出")
            else:
                write_csv(target, rows)
                print(f"CSV 已保存: {target}（{len(rows)} 条，UTF-8 带 BOM）")
        else:
            write_csv(args.csv, rows)
            print(f"CSV 已写出: {args.csv}（{len(rows)} 条，UTF-8 带 BOM）")

    if args.xml is not None:
        nodes = build_tree(rows)
        if args.level is not None:
            nodes = truncate(nodes, args.level)
        if not nodes:
            raise BookmarkError(f"--level {args.level} 截断后没有剩余书签")
        if args.xml == DIALOG:
            level = tree_max_level(nodes)
            target = ask_save_path(os.path.join(initdir, stem + f"_书签_{level}级.xml"))
            if not target:
                print("已取消 XML 保存：未写出")
            else:
                write_xml(target, nodes)
                print(f"XML 已保存: {target}（{count_nodes(nodes)} 条，最大层级 {level}）")
        else:
            write_xml(args.xml, nodes)
            print(f"XML 已写出: {args.xml}（{count_nodes(nodes)} 条，最大层级 {tree_max_level(nodes)}）")


def count_nodes(nodes: list[Node]) -> int:
    return sum(1 + count_nodes(n.children) for n in nodes)


def tree_max_level(nodes: list[Node]) -> int:
    best = 0
    for n in nodes:
        best = max(best, n.level, tree_max_level(n.children))
    return best


def run_write(args) -> None:
    rows = load_titles(args.input)
    import pymupdf

    for warn in extra_checks(rows, pymupdf.open(args.pdf).page_count):
        print(f"警告: {warn}")
    write_pdf(args.pdf, rows, args.out, args.level, args.in_place)


def run_parity(args) -> None:
    parity(args.csv, args.xml, args.level, args.tool_dir)


if __name__ == "__main__":
    main()
