# 福昕书签 XML 样式（《csvtopdfbkmk》导出产物）

> 本文件与工作区 `AGENTS.md` 文末附录同步维护。XML 用于描述 PDF 的**分级书签（标签）**，
> 由福昕高级编辑器导入后，左侧「标签」面板出现完整层级目录。以下 schema 与样例均为
> 程序实际输出，可直接作为格式基准。

## 定位

| 项目 | 说明 |
| --- | --- |
| 输入 | 书签 CSV（`级别`、`标题`、`物理页码`） |
| 输出 | 福昕可导入的书签 XML |
| 使用方 | 福昕高级编辑器 → 标签面板 → 导入 |
| 是否改动 PDF | **否**。真正写入 PDF 发生在福昕导入并保存那一步 |
| 与 pymupdf 路径的关系 | 互为备选，页码语义一致，可互相校验 |

## 文件级规格

| 项目 | 规格 |
| --- | --- |
| 扩展名 | `.xml` |
| 默认文件名 | `CSV文件名_层数级.xml`，例：`<stem>_书签_2级.xml` |
| 编码 | **UTF-8** |
| BOM | **不写 BOM**（与 CSV 模板不同；BOM 反而可能干扰解析） |
| XML 声明 | `<?xml version="1.0" encoding="UTF-8"?>` |
| 缩进 | 4 空格，逐层递增；**纯为可读性，不影响导入** |
| 空元素 | 无子书签的项写成自闭合 `<ITEM .../>`（`/>` 前无空格） |
| 行尾/末尾 | Windows 下 CRLF；`</BOOKMARKS>` 后有一个换行 |
| 体积 | 极小，几十条书签通常几 KB |

## Schema

元素树：

```
<?xml version="1.0" encoding="UTF-8"?>
<BOOKMARKS>                      ← 根元素，唯一，无属性
    <ITEM ...>                   ← 一条书签 = 一个 ITEM
        <ITEM ... />             ← 子书签直接嵌套在父 ITEM 内部
        <ITEM ... />
    </ITEM>
    <ITEM ... />
</BOOKMARKS>
```

根元素 `<BOOKMARKS>`：有且仅有一个，无属性，子元素为若干顶级 `<ITEM>`。

书签元素 `<ITEM>` 的属性（每条**全部出现**，顺序固定 `NAME` → `PAGE` → `FITETYPE` → `INDENT`）：

| 属性 | 类型 | 取值来源 | 语义 |
| --- | --- | --- | --- |
| `NAME` | 字符串 | CSV 的「标题」 | 书签显示文字 |
| `PAGE` | 整数 | CSV 的「物理页码」 | 跳转目标页，**1-based PDF 物理页码**（文件首页 = `1`） |
| `FITETYPE` | 枚举 | 固定 `Fit` | 跳转后缩放方式：整页适应窗口 |
| `INDENT` | 非负整数 | `级别 − 1` | 层级标记，顶级为 `0`，每深一级 +1 |

**层级由嵌套位置决定**；`INDENT` 与嵌套表达同一信息（同源 CSV「级别」列），属冗余字段，
但为福昕导入所必需，**两者必须一致**。无子书签的项写自闭合：

```xml
<ITEM NAME="第1章 起步" PAGE="16" FITETYPE="Fit" INDENT="1"/>
```

## 完整样例（实测输出）

输入 8 行示例 CSV（见 csv-format.md），导出 4 级（完整层级）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BOOKMARKS>
    <ITEM NAME="第一部分 基础知识" PAGE="15" FITETYPE="Fit" INDENT="0">
        <ITEM NAME="第1章 起步" PAGE="16" FITETYPE="Fit" INDENT="1">
            <ITEM NAME="1.1 搭建编程环境" PAGE="17" FITETYPE="Fit" INDENT="2">
                <ITEM NAME="1.1.1 Python版本" PAGE="17" FITETYPE="Fit" INDENT="3"/>
            </ITEM>
        </ITEM>
        <ITEM NAME="第2章 变量和简单数据类型" PAGE="30" FITETYPE="Fit" INDENT="1">
            <ITEM NAME="2.1 运行 hello_world.py" PAGE="31" FITETYPE="Fit" INDENT="2"/>
        </ITEM>
    </ITEM>
    <ITEM NAME="第二部分 进阶" PAGE="88" FITETYPE="Fit" INDENT="0"/>
</BOOKMARKS>
```

同一份 CSV 导出 2 级（3 级及以下**整枝丢弃**，不是隐藏——不写入文件）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BOOKMARKS>
    <ITEM NAME="第一部分 基础知识" PAGE="15" FITETYPE="Fit" INDENT="0">
        <ITEM NAME="第1章 起步" PAGE="16" FITETYPE="Fit" INDENT="1"/>
        <ITEM NAME="第2章 变量和简单数据类型" PAGE="30" FITETYPE="Fit" INDENT="1"/>
    </ITEM>
    <ITEM NAME="第二部分 进阶" PAGE="88" FITETYPE="Fit" INDENT="0"/>
</BOOKMARKS>
```

最小样例（单条书签）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BOOKMARKS>
    <ITEM NAME="第五章 抛体运动" PAGE="4" FITETYPE="Fit" INDENT="0"/>
</BOOKMARKS>
```

## CSV → XML → set_toc 字段映射

| CSV 列 | XML 属性 | pymupdf `set_toc` 条目 |
| --- | --- | --- |
| `级别`（1） | 顶级 `ITEM`，`INDENT="0"` | `[1, title, page]` |
| `级别`（2） | 嵌套一级，`INDENT="1"` | `[2, title, page]` |
| `标题` | `NAME` | 条目的 `title` |
| `物理页码` | `PAGE` | 条目的 `pdf_page`（同为 1-based 物理页码） |
| 行序 | `ITEM` 排列顺序（不排序） | toc 列表顺序 |
| — | `FITETYPE="Fit"` 程序固定写入 | 无对应项 |

两条路径页码语义一致，同一份输入的书签条数、层级、页码应逐条对应，可互相校验。

## 深度截断机制

| 选择 | 结果 |
| --- | --- |
| 1级 | 只保留 1 级标题 |
| 2级 | 保留 1～2 级，更深层级整枝丢弃 |
| 最大级 | 保留 CSV 中出现过的全部层级 |

- 截断只影响 XML，原始 CSV 不变，可反复导出不同深度；层数上限由数据中实际出现的最大级别决定。
- 「章 + 节」两级结构导 2 级即可；需要细到知识点时才导最大级。
- csvtopdfbkmk 的 `truncate_tree` 以每层首个节点的级别为基准判断（首行级别为 1 的正常输入下，
  等价于"保留级别 ≤ N 的节点，更深层级连同后代整体不写入"）。

## 特殊字符转义（实测）

标题含 `&`、`<`、`>`、`"` 时**程序自动转义**（序列化层隐式完成），CSV 中按原文填写：

| CSV 中的标题 | XML 中的 `NAME` |
| --- | --- |
| `第1章 C&D <进阶> "引号"` | `第1章 C&amp;D &lt;进阶&gt; &quot;引号&quot;` |
| `带, 逗号的标题` | `带, 逗号的标题`（XML 无需转义，但 CSV 里该字段必须用双引号包裹） |

控制字符转数值引用：Tab→`&#9;`、LF→`&#10;`、CR→`&#13;`。
**反向禁忌**：不要在 CSV 里手写 `&amp;` 等 XML 实体，否则会显示成字面的 `&amp;`。

## 导入福昕的步骤

1. 用福昕高级编辑器打开**目标 PDF**（即 CSV 页码所对应的那一份）。
2. 左侧面板切到「**标签**」。
3. 点标签面板工具栏的导入按钮，选择导出的 `.xml`。
4. 抽查若干条书签的跳转落点（章首页、末条、跨章处）。
5. 确认无误后 **Ctrl+S 保存 PDF**——此时书签才真正写入文件。
6. 若只想临时看效果而不改原文件，导入后不保存即可；也可先另存为 `_书签版.pdf` 再操作。

## 校验与排错

| 现象 | 原因与处理 |
| --- | --- |
| 层级/缩进与预期不符 | CSV 中「级别」跳级（如 `1 → 3`）。实际层数按相对大小决定，应逐级递进 |
| 跳转位置偏前/偏后若干页 | 页码填了印刷页码或目录页码，应改为 PDF 物理页码（含偏移量换算） |
| 标题显示乱码 | XML 被非 UTF-8 编辑器改存过。**不要手工编辑该 XML**，重新导出 |
| 福昕提示格式错误、拒绝导入 | 文件被手工改坏（标签未闭合等）。重新导出，不要修补 |
| 书签数量少于预期 | 导出时选的层数小于 CSV 最大级别，改选「最大级」重导 |
| 页面缩放不合适 | `FITETYPE` 固定为 `Fit`（整页适应）；如需其他缩放，在福昕内手工调整 |

## 与 PDF 的配套关系（维护要点）

- XML 只对**特定版本 PDF** 有效：页码是硬编码的物理页码。PDF 换版、增删页、重排后书签会整体错位，必须重做 CSV 再导出。
- CSV 与 PDF 同目录保存且文件名对应；**一份 PDF 只保留一份 CSV 作「源」**，不同深度的 XML 都从它导出，避免多份 CSV 各自漂移。
- 中间产物（`_render*` 渲染目录等）在导入确认后即可整体删除。

## 程序化生成接口（round-trip 验收基准）

```bash
cd E:/csvtopdfbkmk
python -c "
from src.converter import csv_to_bookmark_xml
csv_to_bookmark_xml('示例.csv', '示例_2级.xml', rows=2)
"
```

`rows` 参数即界面上的「N级」。CSV 需为 UTF-8（建议带 BOM），表头为 `级别,标题,物理页码`。
本 skill 的 `scripts/bookmarks.py` 按同一 schema 生成 XML（同机同 Python 下应与该接口输出
字节级一致），`parity` 子命令即做此比对。
