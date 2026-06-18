#!/usr/bin/env python3
import argparse
import html
import json
import re
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path


BASE = "http://127.0.0.1:23119"
ARXIV_RE = re.compile(
    r"(?:arXiv[:.\s/]*|arxiv\.org/(?:abs|pdf)/|arxiv\.)(\d{4}\.\d{4,5})(?:v\d+)?",
    re.I,
)


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def norm_title(value):
    value = html.unescape(str(value or "")).lower()
    value = re.sub(r"<[^>]+>|\\[a-zA-Z]+|[{}$_^]", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_arxiv_id(value):
    value = str(value or "")
    match = re.search(
        r"(?:arXiv[:.\s/]*|arxiv\.org/(?:abs|pdf)/|arxiv\.|^)(\d{4}\.\d{4,5})(?:v\d+)?",
        value,
        re.I,
    )
    return match.group(1) if match else ""


def find_arxiv_ids(value):
    return ARXIV_RE.findall(str(value or ""))


def record_id(record):
    for key in ["base_id", "arxiv_id", "id", "eprint"]:
        value = normalize_arxiv_id(record.get(key))
        if value:
            return value
    for key in ["abs_url", "pdf_url", "url", "doi"]:
        value = normalize_arxiv_id(record.get(key))
        if value:
            return value
    raise ValueError(f"Cannot find arXiv ID for record titled {record.get('title')!r}")


def snapshot_zotero_db(zotero_dir):
    srcdir = Path(zotero_dir).expanduser()
    tmp = tempfile.TemporaryDirectory()
    tmpdir = Path(tmp.name)
    for suffix in ["", "-wal", "-shm"]:
        src = srcdir / ("zotero.sqlite" + suffix)
        if src.exists():
            shutil.copy2(src, tmpdir / src.name)
    db_path = tmpdir / "zotero.sqlite"
    if not db_path.exists():
        tmp.cleanup()
        raise FileNotFoundError(f"Could not find zotero.sqlite under {srcdir}")
    return tmp, db_path


def load_collection_paths(zotero_dir):
    tmp, db_path = snapshot_zotero_db(zotero_dir)
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT collectionID, key, libraryID, collectionName, parentCollectionID FROM collections"
        ).fetchall()
        con.close()
    finally:
        tmp.cleanup()
    by_id = {
        row["collectionID"]: {
            "id": row["collectionID"],
            "key": row["key"],
            "libraryID": row["libraryID"],
            "name": row["collectionName"],
            "parent": row["parentCollectionID"],
        }
        for row in rows
    }

    def build_path(collection_id):
        names = []
        seen = set()
        current = collection_id
        while current and current not in seen and current in by_id:
            seen.add(current)
            node = by_id[current]
            names.append(node["name"])
            current = node["parent"]
        return "/".join(reversed(names))

    return {
        collection_id: {**node, "path": build_path(collection_id)}
        for collection_id, node in by_id.items()
    }


def normalize_collection_path(path):
    parts = [clean_text(part) for part in re.split(r"\s*(?:/|>)\s*", path or "") if clean_text(part)]
    return "/".join(parts)


def resolve_collection(args):
    if args.collection_id:
        return args.collection_id
    if not args.collection_path:
        return None
    wanted = normalize_collection_path(args.collection_path)
    paths = load_collection_paths(args.zotero_dir)
    matches = [cid for cid, data in paths.items() if normalize_collection_path(data["path"]) == wanted]
    if not matches:
        similar = [data["path"] for data in paths.values() if wanted.split("/")[-1].lower() in data["path"].lower()]
        raise RuntimeError(
            f"Could not resolve collection path {args.collection_path!r}. Similar paths: {similar[:10]}"
        )
    if len(matches) > 1:
        raise RuntimeError(f"Collection path {args.collection_path!r} matched multiple IDs: {matches}")
    return matches[0]


def post_json(base, path, payload, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Zotero-Connector-API-Version": "3",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def post_bytes(base, path, body, headers, timeout=300):
    request = urllib.request.Request(base + path, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def get_selected_collection(base):
    status, body = post_json(base, "/connector/getSelectedCollection", {})
    if status != 200:
        raise RuntimeError(f"getSelectedCollection failed: {status} {body}")
    return json.loads(body)


def target_existing(records, collection_id, zotero_dir):
    metadata_by_title = {norm_title(record.get("title")): record_id(record) for record in records}
    arxiv_pat = re.compile(
        r"(?:arXiv[:.\s/]*|arxiv\.org/(?:abs|pdf)/|arxiv\.)(\d{4}\.\d{4,5})(?:v\d+)?",
        re.I,
    )
    tmp, db_path = snapshot_zotero_db(zotero_dir)
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        query = """
        SELECT i.itemID, it.typeName, f.fieldName, v.value
        FROM collectionItems ci
        JOIN items i ON i.itemID = ci.itemID
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        LEFT JOIN itemData d ON d.itemID = i.itemID
        LEFT JOIN fields f ON f.fieldID = d.fieldID
        LEFT JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE ci.collectionID = ?
        """
        items = {}
        for row in con.execute(query, (collection_id,)):
            item = items.setdefault(
                row["itemID"], {"type": row["typeName"], "fields": {}}
            )
            if row["fieldName"]:
                item["fields"][row["fieldName"]] = row["value"]
        con.close()
    finally:
        tmp.cleanup()

    existing = set()
    for item in items.values():
        if item["type"] == "attachment":
            continue
        fields = item["fields"]
        blob = " ".join(
            str(fields.get(key, ""))
            for key in ["DOI", "url", "extra", "archiveID", "title"]
        )
        existing.update(arxiv_pat.findall(blob))
        title_id = metadata_by_title.get(norm_title(fields.get("title")))
        if title_id:
            existing.add(title_id)
    return existing


def library_matches(records, collection_id, zotero_dir, title_match_any_type=False):
    expected_ids = {record_id(record) for record in records}
    metadata_by_title = {norm_title(record.get("title")): record_id(record) for record in records}
    paths = load_collection_paths(zotero_dir)
    tmp, db_path = snapshot_zotero_db(zotero_dir)
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        query = """
        SELECT i.itemID, i.key, i.libraryID, it.typeName, ci.collectionID, f.fieldName, v.value
        FROM items i
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        LEFT JOIN deletedItems di ON di.itemID = i.itemID
        LEFT JOIN collectionItems ci ON ci.itemID = i.itemID
        LEFT JOIN itemData d ON d.itemID = i.itemID
        LEFT JOIN fields f ON f.fieldID = d.fieldID
        LEFT JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE di.itemID IS NULL
        """
        items = {}
        for row in con.execute(query):
            item = items.setdefault(
                row["itemID"],
                {
                    "itemID": row["itemID"],
                    "key": row["key"],
                    "libraryID": row["libraryID"],
                    "type": row["typeName"],
                    "fields": {},
                    "collections": set(),
                },
            )
            if row["fieldName"]:
                item["fields"][row["fieldName"]] = row["value"]
            if row["collectionID"] is not None:
                item["collections"].add(row["collectionID"])
        con.close()
    finally:
        tmp.cleanup()

    matches = {}
    for item in items.values():
        if item["type"] == "attachment":
            continue
        fields = item["fields"]
        blob = " ".join(
            str(fields.get(key, ""))
            for key in ["DOI", "url", "extra", "archiveID", "title"]
        )
        arxiv_ids = [value for value in find_arxiv_ids(blob) if value in expected_ids]
        title_id = metadata_by_title.get(norm_title(fields.get("title")))
        match_id = ""
        match_basis = ""
        if arxiv_ids:
            match_id = arxiv_ids[0]
            match_basis = "arxiv-id"
        elif title_id and (title_match_any_type or item["type"] == "preprint"):
            match_id = title_id
            match_basis = "title"
        if not match_id:
            continue
        item_copy = {
            **item,
            "collections": sorted(item["collections"]),
            "collection_paths": [
                paths.get(cid, {}).get("path", str(cid)) for cid in sorted(item["collections"])
            ],
            "match_basis": match_basis,
        }
        matches.setdefault(match_id, []).append(item_copy)
    return matches


def classify_records(records, collection_id, zotero_dir, title_match_any_type=False):
    matches = library_matches(
        records,
        collection_id,
        zotero_dir,
        title_match_any_type=title_match_any_type,
    )
    in_target = {}
    elsewhere = {}
    new_records = []
    for record in records:
        arxiv_id = record_id(record)
        record_matches = matches.get(arxiv_id, [])
        target_matches = [
            item for item in record_matches if collection_id in set(item["collections"])
        ]
        if target_matches:
            in_target[arxiv_id] = target_matches
        elif record_matches:
            elsewhere[arxiv_id] = record_matches
        else:
            new_records.append(record)
    return in_target, elsewhere, new_records


def creator(name):
    name = clean_text(name)
    if not name:
        return None
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return {"creatorType": "author", "firstName": first, "lastName": last}
    parts = name.split()
    if len(parts) <= 1:
        return {"creatorType": "author", "name": name}
    return {"creatorType": "author", "firstName": " ".join(parts[:-1]), "lastName": parts[-1]}


def record_authors(record):
    authors = record.get("authors") or []
    if isinstance(authors, str):
        authors = [part.strip() for part in re.split(r"\s+and\s+|;", authors) if part.strip()]
    names = []
    for author in authors:
        if isinstance(author, str):
            names.append(author)
        elif isinstance(author, dict):
            names.append(author.get("name") or " ".join([author.get("firstName", ""), author.get("lastName", "")]))
    return [name for name in names if clean_text(name)]


def item_json(record):
    arxiv_id = record_id(record)
    arxiv_doi = clean_text(record.get("arxiv_doi")) or "10.48550/arXiv." + arxiv_id
    raw_doi = clean_text(record.get("doi"))
    published_doi = clean_text(record.get("published_doi"))
    if raw_doi and raw_doi.lower() != arxiv_doi.lower() and "10.48550/arxiv" not in raw_doi.lower():
        published_doi = published_doi or raw_doi
    journal_ref = clean_text(record.get("journal_ref"))
    extra_lines = ["arXiv:" + arxiv_id]
    if clean_text(record.get("versioned_id")):
        extra_lines.append("arXiv latest version: " + clean_text(record.get("versioned_id")))
    if clean_text(record.get("updated_date")):
        extra_lines.append("arXiv updated: " + clean_text(record.get("updated_date")))
    if journal_ref:
        extra_lines.append("Published: " + journal_ref)
    if published_doi:
        extra_lines.append("Published DOI: " + published_doi)
    categories = record.get("categories") or []
    keywords = record.get("keywords") or []
    if isinstance(categories, str):
        categories = [categories]
    if isinstance(keywords, str):
        keywords = [keywords]
    tags = []
    for tag in list(categories) + list(keywords):
        tag = clean_text(tag)
        if tag and tag not in [existing["tag"] for existing in tags]:
            tags.append({"tag": tag, "type": 1})
    authors = [creator(name) for name in record_authors(record)]
    authors = [author for author in authors if author]
    return {
        "id": arxiv_id,
        "itemType": "preprint",
        "title": clean_text(record.get("title")),
        "creators": authors,
        "abstractNote": clean_text(record.get("summary") or record.get("abstract")),
        "date": clean_text(record.get("published_date") or record.get("date")),
        "archive": "arXiv",
        "archiveID": "arXiv:" + arxiv_id,
        "DOI": arxiv_doi,
        "url": clean_text(record.get("abs_url") or record.get("url")) or "https://arxiv.org/abs/" + arxiv_id,
        "libraryCatalog": "arXiv.org",
        "extra": "\n".join(extra_lines),
        "tags": tags,
    }


def formal_publication_info(record):
    arxiv_id = record_id(record)
    arxiv_doi = clean_text(record.get("arxiv_doi")) or "10.48550/arXiv." + arxiv_id
    raw_doi = clean_text(record.get("doi"))
    published_doi = clean_text(record.get("published_doi"))
    if raw_doi and raw_doi.lower() != arxiv_doi.lower() and "10.48550/arxiv" not in raw_doi.lower():
        published_doi = published_doi or raw_doi
    return {
        "journal_ref": clean_text(record.get("journal_ref")),
        "published_doi": published_doi,
    }


def download_pdf(record, insecure_tls=True, retries=3):
    arxiv_id = record_id(record)
    url = clean_text(record.get("pdf_url")) or "https://arxiv.org/pdf/" + arxiv_id
    ctx = ssl._create_unverified_context() if insecure_tls else None
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 ZoteroConnectorLike/1.0"},
            )
            with urllib.request.urlopen(request, timeout=300, context=ctx) as response:
                data = response.read()
            if len(data) < 1000 or not data.startswith(b"%PDF"):
                raise RuntimeError(f"downloaded data does not look like a PDF ({len(data)} bytes)")
            return data, url
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(3 * attempt)
    raise last_error


def save_one(base, record, insecure_tls=True):
    arxiv_id = record_id(record)
    pdf, pdf_url = download_pdf(record, insecure_tls=insecure_tls)
    session = "codex-" + uuid.uuid4().hex
    status, body = post_json(
        base,
        "/connector/saveItems",
        {
            "sessionID": session,
            "uri": clean_text(record.get("abs_url")) or "https://arxiv.org/abs/" + arxiv_id,
            "items": [item_json(record)],
        },
    )
    if status != 201:
        raise RuntimeError(f"saveItems failed: {status} {body}")

    metadata = {
        "sessionID": session,
        "parentItemID": arxiv_id,
        "title": "Full Text PDF",
        "url": pdf_url,
    }
    status, body = post_bytes(
        base,
        "/connector/saveAttachment",
        pdf,
        {
            "Content-Type": "application/pdf",
            "Content-Length": str(len(pdf)),
            "X-Metadata": json.dumps(metadata),
            "X-Zotero-Connector-API-Version": "3",
        },
    )
    if status != 201:
        raise RuntimeError(f"saveAttachment failed: {status} {body}")
    return len(pdf)


def verify_collection(records, collection_id, zotero_dir):
    expected_by_title = {norm_title(record.get("title")): record_id(record) for record in records}
    expected_ids = {record_id(record) for record in records}
    arxiv_pat = re.compile(
        r"(?:arXiv[:.\s/]*|arxiv\.org/(?:abs|pdf)/|arxiv\.)(\d{4}\.\d{4,5})(?:v\d+)?",
        re.I,
    )
    tmp, db_path = snapshot_zotero_db(zotero_dir)
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        query = """
        SELECT i.itemID, i.key, it.typeName, f.fieldName, v.value
        FROM collectionItems ci
        JOIN items i ON i.itemID = ci.itemID
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        LEFT JOIN itemData d ON d.itemID = i.itemID
        LEFT JOIN fields f ON f.fieldID = d.fieldID
        LEFT JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE ci.collectionID = ?
        ORDER BY i.itemID
        """
        items = {}
        for row in con.execute(query, (collection_id,)):
            item = items.setdefault(
                row["itemID"],
                {"itemID": row["itemID"], "key": row["key"], "type": row["typeName"], "fields": {}},
            )
            if row["fieldName"]:
                item["fields"][row["fieldName"]] = row["value"]

        top = {iid: item for iid, item in items.items() if item["type"] != "attachment"}
        matched = {}
        for item_id, item in top.items():
            fields = item["fields"]
            blob = " ".join(
                str(fields.get(key, ""))
                for key in ["DOI", "url", "extra", "archiveID", "title"]
            )
            ids = [value for value in arxiv_pat.findall(blob) if value in expected_ids]
            match_id = ids[0] if ids else expected_by_title.get(norm_title(fields.get("title")))
            if match_id:
                matched.setdefault(match_id, []).append(item_id)

        attachments = {}
        if top:
            placeholders = ",".join("?" for _ in top)
            attachment_query = f"""
            SELECT ia.parentItemID, i.itemID, ia.linkMode, ia.contentType, ia.path, f.fieldName, v.value
            FROM itemAttachments ia
            JOIN items i ON i.itemID = ia.itemID
            LEFT JOIN itemData d ON d.itemID = i.itemID
            LEFT JOIN fields f ON f.fieldID = d.fieldID
            LEFT JOIN itemDataValues v ON v.valueID = d.valueID
            WHERE ia.parentItemID IN ({placeholders})
            """
            for row in con.execute(attachment_query, tuple(top.keys())):
                attachment = attachments.setdefault(
                    row["itemID"],
                    {
                        "parentItemID": row["parentItemID"],
                        "linkMode": row["linkMode"],
                        "contentType": row["contentType"],
                        "path": row["path"],
                        "fields": {},
                    },
                )
                if row["fieldName"]:
                    attachment["fields"][row["fieldName"]] = row["value"]
        con.close()
    finally:
        tmp.cleanup()

    by_parent = {}
    for attachment in attachments.values():
        by_parent.setdefault(attachment["parentItemID"], []).append(attachment)

    wrong_type = []
    missing_pdf = []
    not_linked_pdf = []
    for arxiv_id, item_ids in matched.items():
        for item_id in item_ids:
            item = top[item_id]
            if item["type"] != "preprint":
                wrong_type.append({"arxiv": arxiv_id, "itemID": item_id, "type": item["type"]})
            pdfs = [
                attachment
                for attachment in by_parent.get(item_id, [])
                if (attachment.get("contentType") or "").lower() == "application/pdf"
                or (attachment.get("path") or "").lower().endswith(".pdf")
            ]
            if not pdfs:
                missing_pdf.append({"arxiv": arxiv_id, "itemID": item_id})
            elif not any(
                attachment.get("linkMode") == 2
                or str(attachment.get("path", "")).startswith("attachments:_/")
                for attachment in pdfs
            ):
                not_linked_pdf.append({"arxiv": arxiv_id, "itemID": item_id})

    return {
        "collection_id": collection_id,
        "top_level_items_in_collection": len(top),
        "expected_records": len(records),
        "matched_expected_records": len(matched),
        "missing_expected_records": sorted(expected_ids - set(matched)),
        "duplicate_expected_records": {key: value for key, value in matched.items() if len(value) > 1},
        "item_type_counts": dict(Counter(item["type"] for item in top.values())),
        "attachments_total_for_target_items": len(attachments),
        "attachment_link_mode_counts": dict(Counter(str(attachment["linkMode"]) for attachment in attachments.values())),
        "wrong_type": wrong_type,
        "missing_pdf": missing_pdf,
        "not_linked_pdf": not_linked_pdf,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--collection-id", type=int)
    parser.add_argument("--collection-path")
    parser.add_argument("--zotero-dir", default=str(Path.home() / "Zotero"))
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--limit", type=int, default=0, help="0 means all missing records.")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument(
        "--reuse-existing-mode",
        choices=["report", "error", "ignore"],
        default="report",
        help="What to do when a matching item exists elsewhere in the library.",
    )
    parser.add_argument(
        "--match-title-any-type",
        action="store_true",
        help="Treat title matches in any Zotero item type as duplicates. Default only title-matches preprints.",
    )
    parser.add_argument("--log", default="zotero_connector_import_log.jsonl")
    args = parser.parse_args()

    records = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    records_by_id = {record_id(record): record for record in records}
    collection_id = resolve_collection(args)
    selected = get_selected_collection(args.base)
    selected_id = selected.get("id")
    if collection_id is None:
        collection_id = selected_id
    if selected_id != collection_id:
        raise RuntimeError(
            f"Zotero selected collection is {selected_id} {selected.get('name')!r}; "
            f"expected {collection_id}. Select the target collection in Zotero and rerun."
        )

    if args.verify_only:
        print(json.dumps(verify_collection(records, collection_id, args.zotero_dir), ensure_ascii=False, indent=2))
        return

    in_target, elsewhere, new_records = classify_records(
        records,
        collection_id,
        args.zotero_dir,
        title_match_any_type=args.match_title_any_type,
    )
    todo = list(new_records)
    remaining_before_batch = len(todo)
    if args.limit and args.limit > 0:
        todo = todo[: args.limit]
    print(
        json.dumps(
            {
                "selected_collection_id": selected_id,
                "selected_collection_name": selected.get("name"),
                "target_existing_count": len(in_target),
                "existing_elsewhere_count": len(elsewhere),
                "new_record_count": len(new_records),
                "remaining_before_batch": remaining_before_batch,
                "batch_size": len(todo),
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if elsewhere and args.reuse_existing_mode == "error":
        raise RuntimeError(
            "Matching items already exist elsewhere in Zotero. "
            "No duplicate items were created; add those existing items to the target collection with a writable Zotero channel."
        )
    if elsewhere and args.reuse_existing_mode == "report":
        for arxiv_id, items in sorted(elsewhere.items()):
            item = items[0]
            published = formal_publication_info(records_by_id[arxiv_id])
            print(
                "EXISTS_ELSEWHERE {aid} itemKey={key} itemID={item_id} type={typ} basis={basis} collections={cols}{pub}".format(
                    aid=arxiv_id,
                    key=item["key"],
                    item_id=item["itemID"],
                    typ=item["type"],
                    basis=item["match_basis"],
                    cols="; ".join(item["collection_paths"]) or "(no collection)",
                    pub=(
                        " published_doi=" + published["published_doi"]
                        if published["published_doi"]
                        else ""
                    ),
                ),
                flush=True,
            )
    if args.dry_run:
        for record in todo:
            print(f"NEW {record_id(record)} {clean_text(record.get('title'))}", flush=True)
        return

    results = [
        {
            "arxiv": arxiv_id,
            "status": "exists_elsewhere_not_duplicated",
            "itemKey": items[0]["key"],
            "itemID": items[0]["itemID"],
            "collections": items[0]["collection_paths"],
            **formal_publication_info(records_by_id[arxiv_id]),
        }
        for arxiv_id, items in sorted(elsewhere.items())
    ]
    for index, record in enumerate(todo, 1):
        arxiv_id = record_id(record)
        try:
            size = save_one(args.base, record, insecure_tls=not args.verify_tls)
            result = {"arxiv": arxiv_id, "status": "ok", "pdf_bytes": size}
            print(f"[{index}/{len(todo)}] OK {arxiv_id} {size} bytes", flush=True)
        except Exception as exc:
            result = {"arxiv": arxiv_id, "status": "error", "error": repr(exc)}
            print(f"[{index}/{len(todo)}] ERROR {arxiv_id}: {exc!r}", flush=True)
        results.append(result)
        time.sleep(args.sleep)

    log_path = Path(args.log)
    with log_path.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "created": sum(result["status"] == "ok" for result in results),
                "existing_elsewhere_not_duplicated": sum(
                    result["status"] == "exists_elsewhere_not_duplicated" for result in results
                ),
                "errors": [result for result in results if result["status"] == "error"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    print(json.dumps(verify_collection(records, collection_id, args.zotero_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
