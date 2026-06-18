# arXiv Zotero Archive 使用说明 / User Guide

这份说明面向日常使用：当你要按关键词追踪 arXiv 新论文，并把它们归档到 Zotero 指定文件夹时，可以直接照这里的提示词或命令走。

This guide is for everyday use: use it when you want to search arXiv by topic and archive matching preprints into a specific Zotero collection.

---

## 中文版

### 适合什么任务

`$arxiv-zotero-archive` 适合这些场景：

| 需求 | 例子 |
|---|---|
| 按关键词检索 arXiv | 搜索 2026 年 6 月关于 skyrmion 的 arXiv 新文章 |
| 生成文献文件 | 导出 RIS、BibTeX、metadata 和 Markdown 表格 |
| 批量归档到 Zotero | 导入到 `1-Altermagnet/arxiv26/arxiv26_6` |
| 避免重复条目 | 全 Zotero 库查重，不重复新建 |
| 保留预印本信息 | 即使已正式发表，也保留 `preprint` 条目 |
| 附上 PDF | 使用最新 arXiv 版本的 PDF，并验证是否为链接附件 |

### 推荐提示词

你可以直接这样说：

```text
用 $arxiv-zotero-archive 搜索 2026 年 6 月关于 [关键词] 的 arXiv 新文章，
生成 RIS/BibTeX/中文表格，并归档到 Zotero 的 [目标文件夹路径]。
```

更具体一点：

```text
用 $arxiv-zotero-archive 检索 2026-06-01 到 2026-06-30 arXiv 上
包含 "topological spin texture" 或 "skyrmion" 的预印本，
生成中文表格，整理每篇论文的关键词和简记，导入到 Zotero 文件夹
1-Spintronics/arxiv26/arxiv26_6。
```

### 表格语言和格式

如果提示词没有说明中文或英文，默认生成英文表格。需要中文表格时，请在提示词中明确写“中文表格”或“中文内容”。

中文表格使用固定表头：

```text
| # | 日期 | arXiv | 标题 | 关键词 | 简记 |
```

规则：

- `标题` 保留 arXiv 原始英文标题，不翻译。
- `关键词` 用中文短语，使用中文分号分隔。
- `简记` 用中文一句话概括摘要，要求简练，不粘贴或机械截断英文摘要。
- 日期和 arXiv 链接保持不变，顺序沿用导出 metadata 的顺序。

### 标准流程

1. 确认检索范围：关键词、日期范围、是否需要复杂检索式。
2. 从 arXiv API 抓取结果，生成本地文件。
3. 人工或模型辅助筛选：去掉不相关论文，按语言要求整理关键词与简记表格。
4. 打开 Zotero，并选中目标 collection。
5. 运行导入脚本：先 dry-run，再正式导入。
6. 做最终校验：数量、重复、条目类型、PDF 附件、链接附件状态。

### 常用命令

检索并导出：

```bash
python scripts/arxiv_search_export.py --terms skyrmion "topological spin texture" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix skyrmion_arxiv_2026-06
```

使用复杂 arXiv query：

```bash
python scripts/arxiv_search_export.py --query "(all:skyrmion OR all:\"topological spin texture\") AND cat:cond-mat.mtrl-sci" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix skyrmion_arxiv_2026-06
```

导入前预检查：

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --dry-run
```

正式导入：

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --sleep 1
```

只做校验：

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --verify-only
```

### 输出文件

| 文件 | 用途 |
|---|---|
| `<prefix>_metadata.json` | 核心 metadata；后续导入 Zotero 依赖它 |
| `<prefix>.ris` | 可批量导入 Zotero/EndNote 的备用文件 |
| `<prefix>.bib` | BibTeX 备用文件 |
| `<prefix>_table.md` | Markdown 表格；默认英文，或按提示词生成中文；简记/Note 要短 |
| `zotero_connector_import_log.jsonl` | 导入日志，记录成功、跳过、错误 |

### Zotero 归档规则

| 规则 | 行为 |
|---|---|
| 全库查重 | 先扫描整个 Zotero 库，而不是只看目标文件夹 |
| 目标文件夹已有 | 跳过，不重复导入 |
| 库里其他文件夹已有 | 报告 `EXISTS_ELSEWHERE`，不新建重复条目 |
| 全库都没有 | 用 Zotero Connector 新建 `preprint` 条目 |
| 已正式发表 | 仍保留 `preprint`；正式发表信息写入 `Extra/其他` |
| 日期字段 | 使用第一次挂 arXiv 的日期 |
| PDF 文件 | 下载最新 arXiv version 的 PDF |
| 附件校验 | 检查 PDF 是否存在，并尽量确认是 linked attachment |

### 已正式发表的预印本如何记录

如果 arXiv metadata 带有正式发表信息，Zotero 条目仍保持：

```text
Item Type: Preprint
DOI: 10.48550/arXiv.xxxx.xxxxx
Date: 第一次挂 arXiv 的日期
```

`Extra/其他` 中会加入类似：

```text
arXiv:2601.00001
arXiv latest version: 2601.00001v3
arXiv updated: 2026-02-03
Published: Example Journal 1, 2 (2026)
Published DOI: 10.1234/example.published
```

### 注意事项

> 导入前请确认 Zotero 已打开，并且左侧已经选中目标文件夹。Connector 保存条目时依赖 Zotero 当前选中的 collection。

> 如果出现 `EXISTS_ELSEWHERE`，说明这篇文章已在整个 Zotero 库中存在。默认安全行为是不重复创建第二个条目。

> 如果 arXiv 返回 `429 Too Many Requests`，等待一段时间后重试。脚本已内置重试和退避参数。

---

## English

### What This Skill Is For

Use `$arxiv-zotero-archive` for these workflows:

| Need | Example |
|---|---|
| Search arXiv by topic | Find June 2026 arXiv papers on skyrmions |
| Generate reference files | Export RIS, BibTeX, metadata, and a Markdown table |
| Archive into Zotero | Import into `1-Spintronics/arxiv26/arxiv26_6` |
| Avoid duplicates | Check the whole Zotero library before creating items |
| Preserve preprint identity | Keep the Zotero item as `preprint`, even if formally published |
| Attach PDFs | Use the latest arXiv version PDF and verify linked attachments |

### Recommended Prompt

You can ask:

```text
Use $arxiv-zotero-archive to search arXiv papers from June 2026 on [keyword],
generate RIS/BibTeX and a concise English table, and archive them into the
Zotero collection [collection path].
```

More specific example:

```text
Use $arxiv-zotero-archive to search arXiv from 2026-06-01 to 2026-06-30
for preprints containing "topological spin texture" or "skyrmion".
Summarize English keywords and a short note for each paper, then import them
into Zotero collection 1-Spintronics/arxiv26/arxiv26_6.
```

### Table Language And Format

If the prompt does not specify Chinese or English, generate the English table by default. Generate the Chinese table only when the prompt explicitly asks for Chinese, 中文, 中文表格, or Chinese content.

English tables use this exact header:

```text
| # | Date | arXiv | Title | Keywords | Note |
```

Rules:

- Keep `Title` as the original English arXiv title.
- Write `Keywords` in concise English topic phrases separated by semicolons.
- Write `Note` as one short English sentence based on the abstract. Do not paste or mechanically truncate the abstract.
- Keep date and arXiv link columns unchanged, and preserve the metadata export order.

Chinese tables use this exact header:

```text
| # | 日期 | arXiv | 标题 | 关键词 | 简记 |
```

For Chinese tables, keep `标题` as the original English arXiv title, write `关键词` in Chinese, and write `简记` as a concise Chinese one-sentence summary.

### Standard Workflow

1. Confirm the search scope: keywords, date range, and whether a raw arXiv query is needed.
2. Fetch results from the arXiv API and write local artifacts.
3. Review or filter the records, then refine the keyword and short-note table in the requested language.
4. Open Zotero and select the target collection.
5. Run the importer: dry-run first, then live import.
6. Verify the final collection: count, duplicates, item type, PDF attachments, and linked-file status.

### Command Templates

Search and export:

```bash
python scripts/arxiv_search_export.py --terms skyrmion "topological spin texture" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix skyrmion_arxiv_2026-06
```

Use a raw arXiv query:

```bash
python scripts/arxiv_search_export.py --query "(all:skyrmion OR all:\"topological spin texture\") AND cat:cond-mat.mtrl-sci" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix skyrmion_arxiv_2026-06
```

Dry-run before import:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --dry-run
```

Live import:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --sleep 1
```

Verification only:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --verify-only
```

### Output Files

| File | Purpose |
|---|---|
| `<prefix>_metadata.json` | Canonical metadata used for Zotero import |
| `<prefix>.ris` | Backup import file for Zotero or EndNote |
| `<prefix>.bib` | BibTeX backup |
| `<prefix>_table.md` | Markdown table; English by default or Chinese when requested; notes must be concise |
| `zotero_connector_import_log.jsonl` | Append-only import log |

### Zotero Archiving Rules

| Rule | Behavior |
|---|---|
| Whole-library duplicate check | Scan the entire Zotero library before creating a new item |
| Already in target collection | Skip it |
| Exists elsewhere in Zotero | Report `EXISTS_ELSEWHERE`; do not create a duplicate |
| New to the library | Create a Zotero `preprint` item through Zotero Connector |
| Formally published | Keep as `preprint`; write publication info into `Extra` |
| Date field | Use the first arXiv posting date |
| PDF file | Download the latest arXiv version |
| Attachment verification | Check that a PDF exists and is linked when required |

### How Formal Publication Is Recorded

If arXiv metadata includes publication information, the Zotero item remains:

```text
Item Type: Preprint
DOI: 10.48550/arXiv.xxxx.xxxxx
Date: first arXiv posting date
```

The `Extra` field receives lines such as:

```text
arXiv:2601.00001
arXiv latest version: 2601.00001v3
arXiv updated: 2026-02-03
Published: Example Journal 1, 2 (2026)
Published DOI: 10.1234/example.published
```

### Notes

> Before importing, make sure Zotero is open and the target collection is selected in the left sidebar. Zotero Connector saves into the currently selected collection.

> `EXISTS_ELSEWHERE` means the paper already exists somewhere in Zotero. The safe default is to avoid creating a second item.

> If arXiv returns `429 Too Many Requests`, wait and retry later. The export script includes retry and backoff options.
