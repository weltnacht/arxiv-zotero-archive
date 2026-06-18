# arXiv-to-Zotero workflow notes

## Connector endpoints

Zotero must be running. The local Connector service usually listens at `http://127.0.0.1:23119`.

- `POST /connector/ping`: confirm Zotero and Connector API availability.
- `POST /connector/getSelectedCollection` with `{}`: read the currently selected Zotero collection.
- `POST /connector/saveItems`: create the preprint item in the currently selected collection.
- `POST /connector/saveAttachment`: attach PDF bytes to the saved item. Send `Content-Type: application/pdf` and `X-Metadata` containing `sessionID`, `parentItemID`, `title`, and `url`.

Use header `X-Zotero-Connector-API-Version: 3` on Connector calls.

The Connector cannot add an already existing Zotero item to another collection. The importer therefore performs whole-library duplicate detection before creating new items. If a duplicate exists elsewhere, it reports `EXISTS_ELSEWHERE` and does not create a duplicate. Use a writable Zotero channel, such as supported UI automation or an explicitly authorized API/plugin bridge, to add that existing item to the target collection.

## Collection lookup

The Connector saves only to the selected collection. The helper script can resolve a user-facing collection path from a read-only snapshot of `~/Zotero/zotero.sqlite`, but it cannot change Zotero's selected folder. If the selected collection differs from the expected ID/path, stop and ask the user to select the target folder.

Accepted path separators in the helper script: `/` or `>`, for example:

```text
1-Altermagnet/arxiv26/arxiv26_5
1-Altermagnet > arxiv26 > arxiv26_5
```

## Metadata shape

The importer expects records with these fields, matching the search-export script:

- `base_id`: arXiv identifier without version, e.g. `2605.05205`
- `title`
- `authors`: list of author names
- `summary`: abstract text
- `published_date`: `YYYY-MM-DD`
- `doi`: optional; if missing, the importer uses `10.48550/arXiv.<base_id>`
- `arxiv_doi`: optional; preferred Zotero DOI for the preprint item
- `published_doi`: optional; formal publication DOI, written to Zotero `Extra`
- `journal_ref`: optional; formal publication reference, written to Zotero `Extra`
- `versioned_id`: latest arXiv version, e.g. `2605.05205v2`
- `categories`: arXiv category list
- `abs_url`: arXiv abstract URL
- `pdf_url`: optional; if missing, the importer uses `https://arxiv.org/pdf/<base_id>`. The search-export script writes the latest version URL.

## Verification criteria

For the target collection, verify:

- all expected arXiv IDs or normalized titles are represented;
- no expected record maps to more than one top-level item in the target collection;
- each expected top-level item has Zotero item type `preprint`;
- formally published preprints remain `preprint` items, with journal information and published DOI in `Extra`;
- item date is the first arXiv posting date, while the linked PDF is the latest arXiv version;
- each expected item has at least one PDF attachment;
- PDF attachments are linked when the user's attachment workflow requires linked files (`linkMode=2` or a linked path pattern such as `attachments:_/`).

## Output files

For each search run, keep these artifacts in the project/workspace unless the user asks otherwise:

- `<prefix>_metadata.json`: canonical source for Zotero import and verification.
- `<prefix>.ris`: reference-manager backup import file.
- `<prefix>.bib`: BibTeX backup.
- `<prefix>_table.md`: initial table for human review and model-assisted refinement.
- `zotero_connector_import_log.jsonl`: append-only import log when running the importer.
