---
name: arxiv-zotero-archive
description: Search arXiv by topic, date range, or keyword set; export reusable citation files and summary tables; then archive matching preprints into a specified Zotero collection through Zotero Connector with whole-library duplicate detection, formal-publication metadata preservation, latest-version PDF attachment, and linked PDF verification. Use when the user asks to track recent arXiv papers, generate RIS/BibTeX/metadata/table outputs, or import/organize arXiv preprints in Zotero folders for any research keyword or field.
---

# arXiv Zotero Archive

## Core workflow

Use this skill for repeatable arXiv literature tracking and Zotero archiving. Keep the workflow general: do not hard-code a topic, month, or collection unless the user asks for it.

1. Clarify or infer the search scope: keywords, arXiv query syntax, date range, and target Zotero collection path or folder name.
2. Search arXiv and export local artifacts with `scripts/arxiv_search_export.py`.
3. Review/filter the metadata. Use the abstracts to produce the user's requested keyword and main-content table; the script's Markdown table is a starting artifact, not a substitute for careful summarization when the user asks for analysis.
4. Ask the user to open Zotero and select the target collection if it is not already selected. The Zotero Connector can save only into Zotero's current selected collection.
5. Import with `scripts/zotero_connector_archive.py`, which uses the same local Connector service that browser connectors call (`http://127.0.0.1:23119`).
6. Verify the target collection: expected count, no target-folder duplicates, item type `preprint`, and linked PDF attachments.

## Scripts

Create arXiv exports:

```bash
python scripts/arxiv_search_export.py --terms altermagnet altermagnetic --date-from 2026-05-01 --date-to 2026-05-31 --output-dir references --prefix altermagnet_arxiv_2026-05
```

Use raw arXiv API query syntax when the term logic is more complex:

```bash
python scripts/arxiv_search_export.py --query "(all:spintronics AND all:altermagnetism)" --date-from 2026-06-01 --date-to 2026-06-30 --output-dir references --prefix spintronics_altermagnetism_2026-06
```

Import the exported metadata into the currently selected Zotero collection:

```bash
python scripts/zotero_connector_archive.py --metadata references/altermagnet_arxiv_2026-05_metadata.json --collection-path "1-Altermagnet/arxiv26/arxiv26_5" --sleep 1
```

Use `--dry-run` before live imports when changing a query, target collection, or deduplication rule:

```bash
python scripts/zotero_connector_archive.py --metadata references/results_metadata.json --collection-path "Parent/Child" --dry-run
```

Run verification only:

```bash
python scripts/zotero_connector_archive.py --metadata references/results_metadata.json --collection-path "Parent/Child" --verify-only
```

## Zotero rules

- Do not write directly to `zotero.sqlite`. Use database snapshots only for collection lookup, duplicate checks, and verification.
- Prefer Zotero Connector import over RIS import when the user wants Zotero `preprint` items with PDF files handled by their Zotero attachment workflow.
- Confirm that `getSelectedCollection` returns the target collection before importing. If it does not, ask the user to select the correct Zotero folder or use UI automation only if a browser/computer-use skill is available and appropriate.
- Treat duplicate checks as whole-library checks. If an arXiv preprint item already exists elsewhere in Zotero, do not create a second item. Reuse the existing item by adding it to the requested collection when a writable Zotero channel is available; otherwise report `EXISTS_ELSEWHERE` and stop short of duplicating it.
- Match duplicates primarily by arXiv ID in DOI, URL, archiveID, extra, or title fields. Use title fallback conservatively: by default, title fallback reuses existing `preprint` items only, so a formally published `journalArticle` does not suppress creation of the requested preprint record.
- Download the PDF first, then call `/connector/saveItems`, then `/connector/saveAttachment`. This avoids creating metadata-only items when a PDF download has already failed.
- Use the first arXiv posting date as the Zotero preprint date. Use the latest arXiv version for the PDF file.
- If arXiv metadata indicates formal publication, keep the Zotero item as `preprint`; put `Published:` and `Published DOI:` lines in Zotero `Extra` instead of converting the item to a journal article.
- After import, verify linked PDF attachments. In the user's Attanger-style setup, linked files generally have `linkMode=2` and often paths like `attachments:_/...pdf`.

## References

Read `references/workflow.md` when you need details about the Connector endpoints, collection lookup, or final verification fields.

Read `references/usage.md` when the user asks how to use the skill, wants a bilingual usage guide, or needs prompt/command templates for routine arXiv-to-Zotero archiving.
