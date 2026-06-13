#!/usr/bin/env python3
"""Sync recent Google Scholar profile papers into a static publications page."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SCHOLAR_URL = (
    "https://scholar.google.com/citations?"
    "hl=zh-CN&user=mO40IjIAAAAJ&view_op=list_works&sortby=pubdate"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

VENUES = [
    {
        "needles": ["pattern analysis and machine intelligence", "tpami"],
        "abbr": "TPAMI",
        "name": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
        "url": "https://www.computer.org/csdl/journal/tp",
        "color": "#e91e63",
        "kind": "journal",
    },
    {
        "needles": ["transactions on image processing", "tip"],
        "abbr": "TIP",
        "name": "IEEE Transactions on Image Processing",
        "url": "https://signalprocessingsociety.org/publications-resources/ieee-transactions-image-processing",
        "color": "#2e7d32",
        "kind": "journal",
    },
    {
        "needles": ["medical image analysis"],
        "abbr": "MedIA",
        "name": "Medical Image Analysis",
        "url": "https://www.journals.elsevier.com/medical-image-analysis",
        "color": "#6a1b9a",
        "kind": "journal",
    },
]


@dataclass
class ScholarPaper:
    title: str
    authors: str
    venue: str
    year: str
    href: str
    publication_date: str = ""
    pdf_url: str = ""


def fetch(url: str, timeout: int = 25) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(title: str) -> str:
    title = html.unescape(title).lower()
    title = re.sub(r"[^a-z0-9]+", "", title)
    return title


def parse_scholar_list(page_html: str) -> list[ScholarPaper]:
    rows = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page_html, flags=re.S)
    papers: list[ScholarPaper] = []
    for row in rows:
        link = re.search(r'<a href="([^"]+)" class="gsc_a_at">(.*?)</a>', row, flags=re.S)
        grays = re.findall(r'<div class="gs_gray">(.*?)</div>', row, flags=re.S)
        year = re.search(r'<span class="gsc_a_h gsc_a_hc gs_ibl">(.*?)</span>', row, flags=re.S)
        if not link or len(grays) < 2:
            continue
        papers.append(
            ScholarPaper(
                title=strip_tags(link.group(2)),
                authors=strip_tags(grays[0]),
                venue=strip_tags(grays[1]),
                year=strip_tags(year.group(1)) if year else "",
                href=html.unescape(link.group(1)),
            )
        )
    return papers


def parse_scholar_detail(detail_html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    blocks = re.findall(
        r'<div class="gs_scl"><div class="gsc_oci_field">(.*?)</div><div class="gsc_oci_value"[^>]*>(.*?)</div>',
        detail_html,
        flags=re.S,
    )
    for field, value in blocks:
        values[strip_tags(field)] = strip_tags(value)
    return values


def infer_pdf_url(paper: ScholarPaper, detail_html: str) -> str:
    text = html.unescape(detail_html)
    arxiv = re.search(r"arXiv[:/\s]*(\d{4}\.\d{4,5})(?:v\d+)?", text, flags=re.I)
    if arxiv:
        return f"https://arxiv.org/pdf/{arxiv.group(1)}.pdf"
    return paper.pdf_url


def enrich_from_detail(paper: ScholarPaper, scholar_url: str) -> ScholarPaper:
    detail_url = urllib.parse.urljoin(scholar_url, paper.href)
    detail_html = fetch(detail_url)
    details = parse_scholar_detail(detail_html)
    paper.authors = details.get("作者") or details.get("Authors") or paper.authors
    paper.publication_date = details.get("发表日期") or details.get("Publication date") or ""
    paper.venue = (
        details.get("期刊")
        or details.get("会议")
        or details.get("Journal")
        or details.get("Conference")
        or paper.venue
    )
    paper.pdf_url = infer_pdf_url(paper, detail_html)
    return paper


def existing_publication_titles(publications_html: str) -> set[str]:
    titles = re.findall(r'<div class="title">(.*?)</div>', publications_html, flags=re.S)
    return {normalize_title(strip_tags(title)) for title in titles}


def split_authors(authors: str) -> list[str]:
    parts = [part.strip() for part in authors.split(",") if part.strip()]
    if len(parts) <= 1:
        return parts
    return parts


def format_authors(authors: str) -> str:
    parts = split_authors(authors)
    if not parts:
        return html.escape(authors)
    if len(parts) == 1:
        return html.escape(parts[0])
    if len(parts) == 2:
        return f"{html.escape(parts[0])} and {html.escape(parts[1])}"
    return ", ".join(html.escape(part) for part in parts[:-1]) + f", and {html.escape(parts[-1])}"


def venue_meta(venue: str) -> dict[str, str]:
    venue_lower = venue.lower()
    for item in VENUES:
        if any(needle in venue_lower for needle in item["needles"]):
            return item
    raise ValueError(f"Unknown venue metadata for: {venue}")


def title_slug(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    for word in words:
        lowered = word.lower()
        if lowered not in {"a", "an", "the", "on", "for", "to", "and", "with", "in", "of"}:
            return lowered[:18]
    return "paper"


def first_author_last_name(authors: str) -> str:
    first = split_authors(authors)[0] if split_authors(authors) else "paper"
    tokens = re.findall(r"[A-Za-z0-9]+", first)
    return (tokens[-1] if tokens else "paper").lower()


def make_entry_id(paper: ScholarPaper, existing_ids: set[str]) -> str:
    base = f"{first_author_last_name(paper.authors)}{paper.year}{title_slug(paper.title)}"
    base = re.sub(r"[^a-z0-9]+", "", base.lower())
    candidate = base
    index = 2
    while candidate in existing_ids:
        candidate = f"{base}{index}"
        index += 1
    existing_ids.add(candidate)
    return candidate


def render_publication_entry(paper: ScholarPaper, display_date: str, entry_id: str) -> str:
    meta = venue_meta(paper.venue)
    title = html.escape(paper.title)
    authors = format_authors(paper.authors)
    note = f"Published on {html.escape(display_date)}" if display_date else ""
    links = ""
    if paper.pdf_url:
        links = (
            f'<a href="{html.escape(paper.pdf_url)}" class="btn btn-sm z-depth-0" '
            'role="button" rel="external nofollow noopener" target="_blank">PDF</a>'
        )
    return f'''<li>
<div class="row">
  <div class="col col-sm-2 abbr">
    <abbr class="badge rounded w-100" style="background-color:{meta["color"]}">
      <a href="{meta["url"]}" rel="external nofollow noopener" target="_blank">{meta["abbr"]}</a>
    </abbr>
  </div>

  <!-- Entry bib key -->
  <div id="{entry_id}" class="col-sm-8">
    <!-- Title -->
    <div class="title">{title}</div>
    <!-- Author -->
    <div class="author">{authors}</div>

    <!-- Journal/Book title and date -->
    <div class="periodical">
      <em>{meta["name"]} (<b>{meta["abbr"]}</b>)</em>,  {html.escape(paper.year)}
    </div>
    <div class="periodical">{note}</div>

    <!-- Links/Buttons -->
    <div class="links">{links}</div>
  </div>
</div>
</li>

'''


def render_news_row(paper: ScholarPaper, display_date: str) -> str:
    meta = venue_meta(paper.venue)
    noun = "paper"
    return f'''          <tr style="padding: 2px 0;">
            <th scope="row" style="width: 20%; padding: 2px 0;">{html.escape(display_date)}</th>
            <td style="padding: 2px 0;">
              1 {noun} accepted to <strong>{html.escape(meta["abbr"])}</strong>.
            </td>
          </tr>

'''


def insert_publications(publications_html: str, entries: list[str]) -> str:
    marker = re.search(
        r'(<h2 class="bibliography">2026</h2>\s*<ol class="bibliography">\s*)',
        publications_html,
        flags=re.S,
    )
    if not marker:
        raise ValueError("Could not find the 2026 bibliography insertion point.")
    return publications_html[: marker.end()] + "".join(entries) + publications_html[marker.end() :]


def insert_news(index_html: str, rows: list[str]) -> str:
    marker = re.search(r'(<table class="table table-sm table-borderless"[^>]*>)', index_html, flags=re.S)
    if not marker:
        raise ValueError("Could not find the homepage news table insertion point.")
    return index_html[: marker.end()] + "\n" + "".join(rows) + index_html[marker.end() :]


def manual_dates(value: str, count: int) -> list[str]:
    if not value:
        return [""] * count
    dates = [item.strip() for item in value.split(";")]
    if len(dates) != count:
        raise ValueError(f"Expected {count} manual dates separated by ';', got {len(dates)}.")
    return dates


def manual_pdf_urls(value: str, count: int) -> list[str]:
    if not value:
        return [""] * count
    urls = [item.strip() for item in value.split(";")]
    if len(urls) != count:
        raise ValueError(f"Expected {count} manual PDF URLs separated by ';', got {len(urls)}.")
    return urls


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--scholar-url", default=DEFAULT_SCHOLAR_URL)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--top-new-count", type=int, default=3)
    parser.add_argument("--manual-dates", default="")
    parser.add_argument("--manual-pdf-urls", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update-news", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.4)
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    publications_path = repo / "publications" / "index.html"
    index_path = repo / "index.html"
    if not publications_path.exists():
        raise FileNotFoundError(publications_path)

    publications_html = publications_path.read_text(encoding="utf-8")
    existing_titles = existing_publication_titles(publications_html)
    existing_ids = set(re.findall(r'<div id="([^"]+)" class="col-sm-8">', publications_html))

    scholar_html = fetch(args.scholar_url)
    papers = parse_scholar_list(scholar_html)[: args.limit]
    missing = [paper for paper in papers if normalize_title(paper.title) not in existing_titles]
    selected = missing[: args.top_new_count]

    for paper in selected:
        time.sleep(args.sleep)
        try:
            enrich_from_detail(paper, args.scholar_url)
        except urllib.error.URLError as exc:
            print(f"warning: failed to enrich {paper.title!r}: {exc}", file=sys.stderr)

    dates = manual_dates(args.manual_dates, len(selected))
    pdf_urls = manual_pdf_urls(args.manual_pdf_urls, len(selected))
    for index, pdf_url in enumerate(pdf_urls):
        if pdf_url:
            selected[index].pdf_url = pdf_url

    result = {
        "scholar_checked": len(papers),
        "missing_count": len(missing),
        "missing_top_new": [
            {
                "title": paper.title,
                "authors": paper.authors,
                "venue": paper.venue,
                "year": paper.year,
                "scholar_publication_date": paper.publication_date,
                "display_date": dates[index] if index < len(dates) else "",
                "pdf_url": paper.pdf_url,
            }
            for index, paper in enumerate(selected)
        ],
        "apply": args.apply,
        "update_news": args.update_news,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not args.apply or not selected:
        return 0

    entries = [
        render_publication_entry(paper, dates[index], make_entry_id(paper, existing_ids))
        for index, paper in enumerate(selected)
    ]
    publications_path.write_text(insert_publications(publications_html, entries), encoding="utf-8", newline="\n")

    if args.update_news:
        if not index_path.exists():
            raise FileNotFoundError(index_path)
        index_html = index_path.read_text(encoding="utf-8")
        rows = [render_news_row(paper, dates[index]) for index, paper in enumerate(selected)]
        index_path.write_text(insert_news(index_html, rows), encoding="utf-8", newline="\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
