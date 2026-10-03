---
name: pdf-bookmarks
description: 为扫描版 PDF（无文本层、无内嵌书签）按印刷结构添加分级书签（常规两级：1=章，2=节）。覆盖标题识别（有目录页/无目录页两条路径，渲染成图目视转录，不用 OCR）、页码偏移实测验证，以及三种落地方式：①导出《csvtopdfbkmk》样式的书签 CSV；②导出福昕高级 PDF 编辑器可导入的书签 XML；③用 pymupdf 直接把书签写入 PDF。凡涉及"给 PDF 加书签/加目录/做书签、书签 CSV、书签 XML、csvtopdfbkmk、福昕书签导入、扫描版教材添加书签"的任务都使用本 skill，即使用户没有明说"书签"二字。依赖：Python 3.10+，硬依赖 pymupdf、pillow（`pip install pymupdf pillow`，脚本启动时自检，缺失会打印安装提示）；软依赖 numpy（加速色彩扫描）、tkinter（保存对话框，Windows 官方 Python 自带）、csvtopdfbkmk 源码（仅 parity 比对用）。
prerequisites:
  python: "3.10+"
  required:
    - "pymupdf（pip install pymupdf）"
    - "pillow（pip install pillow）"
  optional:
    - "numpy（软依赖：加速色彩扫描；缺失时自动降级为抽样计算并提示）"
    - "tkinter（软依赖：保存对话框；Windows 官方 Python 自带，Linux 需 python3-tk；缺失时退回默认路径）"
    - "csvtopdfbkmk 源码（仅 parity 子命令需要，--tool-dir / CSVTOPDFBKMK_DIR 指定）"
---

# 扫描版 PDF 添加书签

工作流三段：**识别标题 → 核验页码 → 落地（CSV / XML / 直写）**。
本文件给出流程与命令；CSV/XML 的精确格式、报错文案、样例在
[references/csv-format.md](references/csv-format.md) 和
[references/xml-format.md](references/xml-format.md)，需要核对格式细节时再读。

依赖：Python 3.10+；硬依赖 `pymupdf`、`pillow`（`pip install pymupdf pillow`）；软依赖 `numpy`（加速色彩扫描，缺失自动降级为抽样计算）、`tkinter`（保存对话框，Windows 官方 Python 自带；缺失时退回默认路径）、csvtopdfbkmk 源码（仅 `parity` 子命令需要）。各脚本启动时自检依赖：缺硬依赖会打印安装提示并以非零码退出，软依赖缺失自动降级并提示。
安装与分发说明见 [README.md](README.md)。
下文命令中的脚本路径相对本 skill 目录（`scripts/…`），执行时用绝对路径。

## 第 0 步 检查现状

用 pymupdf 打开目标 PDF：

- `get_toc()` 已有书签 → 先把现有书签打印/存档，防止后续覆盖丢失；
- `get_text()` 判断扫描版还是有文本层，**按类型走不同识别路径**：
  - **有文本层** → `python scripts/extract_titles.py 书.pdf --out titles.txt` 按字体大小
    提取标题（快且不会认错字；`--debug` 可看字号分布调 `--min-ratio`），直接跳到第 2 步。
    提取结果仍需抽查几条（防正文大字误判）；
  - **无文本层（扫描版）** → 按第 1 步的分支 A/B 视觉转录；
- 记录 `page_count`。

## 第 1 步 识别标题（仅扫描版需要；文本版已由 extract_titles.py 完成）

**逐字转录规则（不可妥协）**：破折号（——）、全角冒号（：）、节号格式必须与原书
完全一致，**不得"规范化"改写**（如"力的合成和分解"不能写成"力的合成与分解"）。
拿不准的字放大重渲染再看；文字正确优先于一切格式美化。

### 分支 A：有目录页

1. 前 8 页渲染 130 dpi PNG，目视找"目 录"页（教材目录常在版权页后、正文前）。
2. 目录页以 220 dpi 渲染，逐字转录全部章、节标题及其印刷页码。

### 分支 B：无目录页（标题来源 = 章扉页 + 节起始页）

1. `python scripts/structure_scan.py scan 书.pdf` —— 全页色彩扫描，
   `fracColorful ≥ 0.5` 的整页彩色分隔页即章扉页候选（封面、封底同样命中，按位置排除）。
2. `python scripts/structure_scan.py sheets 书.pdf --pages 4-111 --outdir _render`
   —— 正文页 3×3 缩略图网格（红框 + 页码标签），逐张目视找带大号数字徽标的节起始页。
3. 章扉页、节起始页分别以 220 dpi 渲染，逐字转录章名、节名。
4. 交叉验证：书末索引的词条页码应落在对应节起始页或节内；可借外部标准版本
   （国家中小学智慧教育平台 basic.smartedu.cn 电子课本、纸质书）做清单底稿，
   **逐字以扫描件为准**——不同印次目录可能微调，"对不上"往往是版次差异或缺页信号。

## 第 2 步 页码映射与验证

- 偏移量 = 前置页面数（封面、扉页、版权页、目录页、空白页等）；**PDF 页 = 印刷页 + 偏移**。
- 至少抽查 6 处（各章扉页、若干节起始页、末尾附录/索引）页脚印刷页码；
  **全部吻合才可批量套用**；不吻合说明扫描缺页，需分段分别求偏移。
  每册书的偏移量独立，不得沿用上一册结论。
- 章扉页常不印页码：用相邻两个有页码的页"夹逼"验证。
- 完全没有印刷页码时：标题页是逐页目视找出的，物理页码天然已知；缺页风险改用
  图/表/例题/题号连续性（最有效，缺页必跳号）、翻页内容衔接、章节结构完整性、
  外部标准版本比对。

## 第 3 步 落地（三个功能）

先把转录结果写成中间文件 `titles.txt`，每行一条，竖线分隔（避免标题中逗号干扰），
`#` 开头为注释；也可直接用现成的 csvtopdfbkmk 样式 CSV 作输入：

```
1|第五章 抛体运动|4
2|1. 曲线运动|5
```

二级标题建议格式 `N. 标题`（节号后半角点 + 空格）；若该项目已有既定书签风格，先沿用既有风格。

### 功能 1：导出 CSV（供《csvtopdfbkmk》→ XML → 福昕）

```bash
python scripts/bookmarks.py export titles.txt --csv "<stem>_书签.csv" [--pdf 书.pdf]
```

UTF-8 带 BOM，表头 `级别,标题,物理页码`，规则详见 references/csv-format.md。
校验与 csvtopdfbkmk 一致，另加警告：级别跳级、页码非单调、页码超 PDF 页数（给了 `--pdf` 时）。
`--csv` / `--xml` **不带路径值**时，数据校验通过后弹出系统"另存为"对话框（CSV 默认名
`<PDF名>_书签.csv`，XML 默认名 `<PDF名>_书签_N级.xml`，默认目录为 PDF 所在目录；
`--pdf` 未给时用输入文件名派生）；取消则该文件不写出。对话框会阻塞命令直到用户
选择，调用时给足超时时间。

### 功能 2：导出 XML（供福昕高级编辑器直接导入）

```bash
python scripts/bookmarks.py export titles.txt --xml "<stem>_书签_2级.xml" --level 2
```

按福昕 schema 生成（`BOOKMARKS`/`ITEM NAME PAGE FITETYPE INDENT`，嵌套表达层级、
叶节点自闭合、UTF-8 无 BOM），schema 详见 references/xml-format.md。
`--level N` 截断深度（更深层级整枝丢弃）。`export` 可同时给 `--csv` 和 `--xml`。
生成结果可用 `parity` 子命令与 E:/csvtopdfbkmk 的 converter 做字节级比对（可选）：

```bash
python scripts/bookmarks.py parity "<stem>_书签.csv" "<stem>_书签_2级.xml" --level 2
```

parity 为可选功能：需本机有《csvtopdfbkmk》源码，用 `--tool-dir` 或环境变量
`CSVTOPDFBKMK_DIR` 指定其根目录；没有该工具不影响导出。

### 功能 3：写入 PDF（pymupdf `set_toc`）

```bash
python scripts/bookmarks.py write 书.pdf titles.txt [--out OUT.pdf] [--level N] [--in-place]
```

**默认不修改原始文件**。保存位置按下述优先级确定：
- **用户在对话中已明确保存位置**（如"都放在桌面""保存到 xx 目录"）→ 视同 `--out` 直接
  写出，**不弹对话框**；
- 未指定位置 → 加签完成后弹出系统"另存为"对话框，默认文件名 `<原文件名>_书签版.pdf`、
  默认目录为原文件所在目录；取消则不写出任何文件；
- `--out OUT.pdf` 始终跳过对话框直接写出；`--in-place` 才原位写入：先备份 `<stem>_backup.pdf`
（已存在则沿用最早的）→ 原位增量保存 → 被占用（PermissionError）时自动改存
`<stem>_书签版.pdf`。`--csv`/`--xml` 带路径同理不弹框、不带值才弹框。
写入前检查页码不超 PDF 页数、级别不可跳级（PDF 大纲限制，比 XML 路径严格）；
写出后自检页数不变、书签条数/层级/页码逐条核对并打印报告。注意：弹框会阻塞命令
直到用户选择，调用时给足超时时间。

## 验收与清理

- **交付时必须列出每个产物文件的完整绝对路径**（markdown 链接形式）并说明用途——工作区涉及多个目录（如 `files/`、用户桌面），只说"已导出"或目录名不算完成交付。
- 功能 1/2：用户经 csvtopdfbkmk + 福昕导入后，抽查书签跳转落点（章首页、末条、跨章处）。
- 功能 3：以脚本自检报告为准，并建议用户在阅读器里抽查跳转——**最终以"跳过去看到的页面"为准**。
- 确认无误后删除临时渲染目录（`_render*`）与测试产物。
