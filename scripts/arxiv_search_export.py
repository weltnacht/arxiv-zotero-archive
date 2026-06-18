#!/usr/bin/env python3
import argparse
import html
import json
import re
import ssl
import textwrap
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def arxiv_id_from_url(url):
    tail = url.rstrip("/").split("/")[-1]
    return re.sub(r"v\d+$", "", tail), tail


def term_query(term):
    term = term.strip()
    if not term:
        return ""
    escaped = term.replace('"', '\\"')
    if re.search(r"\s", term):
        return f'all:"{escaped}"'
    return f"all:{escaped}"


def build_query(args):
    if args.query:
        query = args.query.strip()
    else:
        query = " OR ".join(term_query(term) for term in args.terms if term.strip())
        query = f"({query})"
    if args.date_from and args.date_to:
        start = args.date_from.replace("-", "") + "0000"
        end = args.date_to.replace("-", "") + "2359"
        query = f"({query}) AND submittedDate:[{start} TO {end}]"
    return query


def fetch_page(query, start, max_results, verify_tls=False, retries=3, retry_sleep=20):
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = "https://export.arxiv.org/api/query?" + params
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Codex arxiv-zotero-archive/1.0"},
    )
    ctx = None if verify_tls else ssl._create_unverified_context()
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120, context=ctx) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 503) or attempt == retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else retry_sleep * attempt
            time.sleep(delay)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(retry_sleep * attempt)
    raise last_error


def parse_entry(entry):
    atom_id = clean_text(entry.findtext(ATOM + "id"))
    base_id, versioned_id = arxiv_id_from_url(atom_id)
    title = clean_text(entry.findtext(ATOM + "title"))
    summary = clean_text(entry.findtext(ATOM + "summary"))
    published = clean_text(entry.findtext(ATOM + "published"))
    updated = clean_text(entry.findtext(ATOM + "updated"))
    authors = [
        clean_text(author.findtext(ATOM + "name"))
        for author in entry.findall(ATOM + "author")
    ]
    categories = [
        cat.attrib.get("term", "")
        for cat in entry.findall(ATOM + "category")
        if cat.attrib.get("term")
    ]
    primary = entry.find(ARXIV + "primary_category")
    primary_category = primary.attrib.get("term", "") if primary is not None else ""
    raw_doi = clean_text(entry.findtext(ARXIV + "doi"))
    arxiv_doi = "10.48550/arXiv." + base_id
    published_doi = raw_doi if raw_doi and "10.48550/arxiv" not in raw_doi.lower() else ""
    journal_ref = clean_text(entry.findtext(ARXIV + "journal_ref"))
    comment = clean_text(entry.findtext(ARXIV + "comment"))
    pdf_url = ""
    for link in entry.findall(ATOM + "link"):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break
    # Use the latest version for the PDF while keeping the date as the first arXiv posting.
    pdf_url = "https://arxiv.org/pdf/" + versioned_id
    version_match = re.search(r"v(\d+)$", versioned_id)
    return {
        "base_id": base_id,
        "versioned_id": versioned_id,
        "latest_version": int(version_match.group(1)) if version_match else None,
        "title": title,
        "authors": authors,
        "summary": summary,
        "published": published,
        "updated": updated,
        "published_date": published[:10],
        "updated_date": updated[:10],
        "doi": arxiv_doi,
        "arxiv_doi": arxiv_doi,
        "published_doi": published_doi,
        "is_formally_published": bool(journal_ref or published_doi),
        "journal_ref": journal_ref,
        "comment": comment,
        "categories": categories,
        "primary_category": primary_category,
        "abs_url": "https://arxiv.org/abs/" + base_id,
        "pdf_url": pdf_url,
    }


def fetch_records(query, args):
    records = []
    seen = set()
    start = 0
    page_size = min(args.page_size, 100)
    while start < args.max_results:
        data = fetch_page(
            query,
            start,
            page_size,
            verify_tls=args.verify_tls,
            retries=args.retries,
            retry_sleep=args.retry_sleep,
        )
        root = ET.fromstring(data)
        entries = root.findall(ATOM + "entry")
        if not entries:
            break
        for entry in entries:
            record = parse_entry(entry)
            if record["base_id"] in seen:
                continue
            seen.add(record["base_id"])
            if args.date_from and record["published_date"] < args.date_from:
                continue
            if args.date_to and record["published_date"] > args.date_to:
                continue
            if args.require_match:
                blob = " ".join(
                    [
                        record["title"],
                        record["summary"],
                        " ".join(record["categories"]),
                    ]
                )
                if not re.search(args.require_match, blob, re.I):
                    continue
            records.append(record)
        start += page_size
        if len(entries) < page_size:
            break
        time.sleep(args.sleep)
    return records


def ris_escape(value):
    return clean_text(value).replace("\n", " ")


def write_ris(records, path):
    lines = []
    for record in records:
        lines.append("TY  - GEN")
        lines.append("TI  - " + ris_escape(record["title"]))
        for author in record["authors"]:
            lines.append("AU  - " + ris_escape(author))
        lines.append("AB  - " + ris_escape(record["summary"]))
        lines.append("DA  - " + record["published_date"])
        lines.append("DO  - " + record["doi"])
        lines.append("UR  - " + record["abs_url"])
        lines.append("PB  - arXiv")
        lines.append("T2  - arXiv")
        lines.append("N1  - arXiv:" + record["base_id"])
        if record.get("journal_ref"):
            lines.append("N1  - Published: " + ris_escape(record["journal_ref"]))
        if record.get("published_doi"):
            lines.append("N1  - Published DOI: " + ris_escape(record["published_doi"]))
        for category in record["categories"]:
            lines.append("KW  - " + category)
        lines.append("ER  - ")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def bibtex_key(record):
    first = "arxiv"
    if record["authors"]:
        first = re.sub(r"[^A-Za-z0-9]", "", record["authors"][0].split()[-1]) or "arxiv"
    year = record["published_date"][:4] or "n.d."
    return f"{first}{year}{record['base_id'].replace('.', '')}"


def bib_value(value):
    value = clean_text(value)
    value = value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return value


def write_bib(records, path):
    blocks = []
    for record in records:
        fields = {
            "title": record["title"],
            "author": " and ".join(record["authors"]),
            "year": record["published_date"][:4],
            "eprint": record["base_id"],
            "archivePrefix": "arXiv",
            "primaryClass": record["primary_category"] or (record["categories"][0] if record["categories"] else ""),
            "doi": record["doi"],
            "url": record["abs_url"],
            "abstract": record["summary"],
            "note": "; ".join(
                value
                for value in [
                    "Published: " + record.get("journal_ref", "") if record.get("journal_ref") else "",
                    "Published DOI: " + record.get("published_doi", "") if record.get("published_doi") else "",
                ]
                if value
            ),
        }
        lines = [f"@misc{{{bibtex_key(record)},"]
        for key, value in fields.items():
            if value:
                lines.append(f"  {key} = {{{bib_value(value)}}},")
        lines.append("}")
        blocks.append("\n".join(lines))
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def md_escape(value):
    return clean_text(value).replace("|", "\\|")


def infer_keywords(record, terms):
    keywords = []
    blob = (record["title"] + " " + record["summary"]).lower()
    for term in terms:
        if term.lower() in blob:
            keywords.append(term)
    keywords.extend(record["categories"][:4])
    deduped = []
    for keyword in keywords:
        if keyword and keyword not in deduped:
            deduped.append(keyword)
    return "; ".join(deduped)


def write_table(records, path, terms):
    lines = [
        "| # | Date | arXiv | Title | Keywords | Main content |",
        "|---:|---|---|---|---|---|",
    ]
    for index, record in enumerate(records, 1):
        abstract = textwrap.shorten(record["summary"], width=260, placeholder="...")
        lines.append(
            "| {idx} | {date} | [{aid}]({url}) | {title} | {keywords} | {abstract} |".format(
                idx=index,
                date=record["published_date"],
                aid=record["base_id"],
                url=record["abs_url"],
                title=md_escape(record["title"]),
                keywords=md_escape(infer_keywords(record, terms)),
                abstract=md_escape(abstract),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Raw arXiv API query fragment, without the date range.")
    group.add_argument("--terms", nargs="+", help="Terms to OR together as all:<term> clauses.")
    parser.add_argument("--date-from", help="Inclusive published-date filter, YYYY-MM-DD.")
    parser.add_argument("--date-to", help="Inclusive published-date filter, YYYY-MM-DD.")
    parser.add_argument("--require-match", help="Optional regex filter over title, abstract, and categories.")
    parser.add_argument("--max-results", type=int, default=500)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=3.0)
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=int, default=20)
    parser.add_argument("--output-dir", default="references")
    parser.add_argument("--prefix")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix
    if not prefix:
        start = args.date_from or "start"
        end = args.date_to or "end"
        prefix = f"arxiv_{start}_to_{end}"

    query = build_query(args)
    records = fetch_records(query, args)
    records.sort(key=lambda row: (row["published_date"], row["base_id"]), reverse=True)

    metadata_path = output_dir / f"{prefix}_metadata.json"
    ris_path = output_dir / f"{prefix}.ris"
    bib_path = output_dir / f"{prefix}.bib"
    table_path = output_dir / f"{prefix}_table.md"
    query_path = output_dir / f"{prefix}_query.txt"

    metadata_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    query_path.write_text(query + "\n", encoding="utf-8")
    write_ris(records, ris_path)
    write_bib(records, bib_path)
    write_table(records, table_path, args.terms or [])

    print(
        json.dumps(
            {
                "query": query,
                "count": len(records),
                "metadata": str(metadata_path),
                "ris": str(ris_path),
                "bib": str(bib_path),
                "table": str(table_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
