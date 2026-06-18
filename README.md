# arXiv Zotero Archive

A Codex skill for searching arXiv by topic and archiving matching preprints into Zotero collections.

It exports reusable citation files, builds review tables, imports new arXiv records through Zotero Connector, checks for duplicates across the whole Zotero library, preserves formal-publication metadata in `Extra`, and verifies linked PDF attachments.

## Features

- Search arXiv by keywords, raw arXiv API query, and date range.
- Export `metadata.json`, RIS, BibTeX, and Markdown summary tables.
- Import records as Zotero `preprint` items through Zotero Connector.
- Check the whole Zotero library before creating new items.
- Avoid creating duplicate Zotero items when a matching item already exists elsewhere.
- Keep preprint identity even when the work has been formally published.
- Store published journal reference and published DOI in Zotero `Extra`.
- Use first arXiv posting date as the Zotero item date.
- Download the latest arXiv version PDF.
- Verify PDF attachments and linked-file status.

## Installation

Clone or copy this repository into your Codex skills directory:

```bash
git clone https://github.com/weltnacht/arxiv-zotero-archive.git ~/.codex/skills/arxiv-zotero-archive
```

On Windows, the target directory is usually:

```text
C:\Users\<you>\.codex\skills\arxiv-zotero-archive
```

Then invoke the skill in Codex:

```text
Use $arxiv-zotero-archive to search arXiv for recent papers on skyrmion and archive them into my Zotero collection.
```

## Typical Workflow

1. Search arXiv and export local artifacts.
2. Review and refine the generated table.
3. Open Zotero and select the target collection.
4. Run the importer in dry-run mode.
5. Import new records through Zotero Connector.
6. Verify the Zotero collection.

## Command Examples

Search and export:

```bash
python scripts/arxiv_search_export.py --terms skyrmion "topological spin texture" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix skyrmion_arxiv_2026-06
```

Dry-run before Zotero import:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --dry-run
```

Live import:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --sleep 1
```

Verify only:

```bash
python scripts/zotero_connector_archive.py --metadata references/skyrmion_arxiv_2026-06_metadata.json --collection-path "1-Spintronics/arxiv26/arxiv26_6" --verify-only
```

## Zotero Notes

Zotero must be running. The importer uses Zotero Connector's local service at `http://127.0.0.1:23119`.

Zotero Connector creates new items in the currently selected Zotero collection. If a matching item already exists elsewhere in the Zotero library, this skill reports `EXISTS_ELSEWHERE` and does not create a duplicate. Adding an existing item into another collection requires a writable Zotero channel, such as supported UI automation or a dedicated Zotero bridge.

The scripts never write directly to `zotero.sqlite`. They only read database snapshots for collection lookup, duplicate checks, and verification.

## Documentation

- [Skill instructions](SKILL.md)
- [Detailed workflow notes](references/workflow.md)
- [Bilingual user guide](references/usage.md)

## 中文简介

这是一个用于 Codex 的 arXiv 到 Zotero 文献追踪与归档 skill。它可以按关键词和时间范围检索 arXiv，导出 RIS/BibTeX/metadata/Markdown 表格，并通过 Zotero Connector 将新论文作为 `preprint` 条目导入指定 Zotero 文件夹。

主要规则：

- 全 Zotero 库查重，避免重复新建条目。
- 如果目标文件夹已有，跳过。
- 如果库里其他位置已有，报告 `EXISTS_ELSEWHERE`，默认不重复创建。
- 即使预印本已正式发表，也保留 `preprint` 类型。
- 正式发表期刊信息和 published DOI 写入 Zotero `Extra/其他`。
- `date` 使用第一次挂 arXiv 的日期。
- PDF 使用最新 arXiv version。

更多中文说明见 [references/usage.md](references/usage.md)。

## License

MIT
