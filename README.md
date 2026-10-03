# pdf-bookmarks — PDF 添加书签 skill

当前版本 **v1.0.0**（首个版本：导出 CSV / 福昕 XML / 直写 PDF 三功能；扫描版与文本版双路径识别；parity 字节级比对验收）。版本随 git tag 管理，各版本的下载与更新说明见 [安装](#安装)。

为 PDF 按印刷结构添加分级书签（常规两级：一级 = 章，二级 = 节），**扫描版与文本版通吃**：

- **扫描版**（页面是图片、无文字层，`get_text()` 为空）：把页面渲染成图片，视觉逐字转录标题——有目录页走目录转录；无目录页用色彩扫描定位章扉页 + 缩略图网格找节起始页。
- **文本版**（有文字层）：`extract_titles.py` 按字体大小直接提取标题层级，几秒出清单、不会认错字。边界：要求排版**靠字号区分层级**（教材、报告均属此类）；标题只加粗不加大的 PDF 识别不了，请改走扫描版路径。
- **两条路径汇合后相同**：实测"印刷页 → PDF 物理页"偏移并抽查，然后三选一落地——导出《csvtopdfbkmk》样式的书签 CSV；导出福昕高级编辑器可导入的书签 XML；用 pymupdf 直接写入书签。三个落地命令都**不改动原始 PDF**；保存位置可直接给路径，也可以弹"另存为"对话框选（详见"直接使用脚本"）。

## 安装

1. 安装依赖（Python 3.10+）：

   ```bash
   pip install pymupdf pillow
   ```

   （`numpy` 可选，装了能加速色彩扫描；不装也能跑。弹"另存为"对话框用的 tkinter 已随 Windows 官方 Python 自带，Linux 需另装 `python3-tk`。）

2. 把 skill 装到你的智能体工具的 skills 目录（**仅为获得自动触发/斜杠调用**；其他智能体或纯终端直接用脚本即可，见下节）：

   ```bash
   # 方式 A：git 克隆（便于跟随更新）
   git clone https://github.com/upquark-dev/pdf-bookmarks "<你的用户目录>/.agents/skills/pdf-bookmarks"

   # 方式 B：直接复制整个 pdf-bookmarks/ 文件夹过去
   ```

   装到用户级（`<你的用户目录>/.agents/skills/`）则所有工作区可用；装到 `<项目>/.agents/skills/` 则仅该项目可用。不同工具的 skills 目录位置可能不同，以所用工具的文档为准。

3. 重启智能体工具的会话即生效。对模型说"给 xxx.pdf 加书签 / 导出书签 CSV / 导出书签 XML"即可触发。

## 其他智能体 / 纯终端也能用

skill 的核心是四个**独立 Python 脚本**和两份**格式规范文档**，不依赖任何智能体工具的专有功能：

- 任何能执行命令的智能体（Claude Code、Codex、Cursor……）或人在终端，直接调用 `scripts/` 里的 CLI 即可（命令见下节）；
- `SKILL.md` 与 `references/` 是普通 Markdown——把 `SKILL.md` 作为工作流说明、`references/` 作为格式规范喂给任何模型，它就能照着执行同样的流程；
- "自动触发 / 斜杠调用"只是支持 skill 发现机制的工具提供的便利层。

## 直接使用脚本（任何智能体 / 终端通用）

以下命令假定当前目录为 skill 的 `scripts/`（否则自行加上脚本路径前缀）；`书.pdf` 处填你自己的 PDF 路径。

```bash
# 功能 0：文本版 PDF 提取标题（扫描版用不了，走视觉转录）
python extract_titles.py 书.pdf --out titles.txt

# 功能 1：导出 CSV（utf-8-sig；--csv 不带值时弹出"另存为"对话框，默认名 书名_书签.csv）
python bookmarks.py export titles.txt --csv "书名_书签.csv" --pdf 书.pdf

# 功能 2：导出福昕 XML（--level N 截断深度；--xml 不带值时弹"另存为"对话框，默认名 书名_书签_N级.xml）
python bookmarks.py export titles.txt --xml "书名_书签_2级.xml" --level 2

# 功能 3：写入书签（处理完后弹出系统"另存为"对话框选保存位置，默认文件名
#         原文件名_书签版.pdf，原始文件不动；--out 跳过对话框；--in-place 原位写入）
python bookmarks.py write 书.pdf titles.txt

# 结构扫描（无目录页时）：①找章扉页 ②缩略图网格找节起始页
python structure_scan.py scan 书.pdf
python structure_scan.py sheets 书.pdf --pages 4-111 --outdir _render
```

标题清单 `titles.txt` 每行一条：`级别|标题|物理页码`（`#` 为注释），也接受现成的 csvtopdfbkmk 样式 CSV。页码一律是 **PDF 物理页码**（封面 = 1），不是书上印刷的页码。

## 可选组件

- 本机若有《csvtopdfbkmk》源码（含 `src/converter.py`），`parity` 子命令可对生成的 XML 做字节级比对验收：

  ```bash
  python bookmarks.py parity 书名_书签.csv 书名_书签_2级.xml --level 2 --tool-dir <工具源码根目录>
  ```

  也可设环境变量 `CSVTOPDFBKMK_DIR`。没有该工具不影响导出和写入。

## 文件结构

```
pdf-bookmarks/
├── SKILL.md                  # 模型执行的工作流（触发后加载）
├── README.md                 # 本文件
├── references/
│   ├── csv-format.md         # CSV 书签样式完整规范（含校验报错对照）
│   └── xml-format.md         # 福昕书签 XML 完整规范（schema + 实测样例）
└── scripts/
    ├── extract_titles.py     # 文本版 PDF：按字体大小提取标题 → titles.txt
    ├── bookmarks.py          # export / write / parity 三子命令
    └── structure_scan.py     # scan / sheets 结构扫描（扫描版无目录页时用）
```

## 注意事项

- 标题必须**逐字转录**原书（全角冒号、破折号等不得"规范化"改写）；文本版由脚本提取，交付前仍应抽查几条（防正文大字被误判为标题）。
- 每本书的页码偏移独立，换书必须重新实测。
- **原始 PDF 永远不会被修改**：书签写入输出到 `<原文件名>_书签版.pdf` 或你指定的位置；只有显式加 `--in-place` 才原位写入（且会先自动备份）。
- XML 页码是硬编码的物理页码，PDF 换版/增删页后必须重做 CSV 再导出。

## 版本记录

- **v1.0.0**（首个版本）：三功能落地（CSV / 福昕 XML / pymupdf 直写）；扫描版视觉转录与文本版字号提取双路径；保存对话框与直写优先级规则；parity 与《csvtopdfbkmk》字节级比对。
