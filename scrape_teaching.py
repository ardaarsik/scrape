#!/usr/bin/env python3
"""Scrape a web page (default: https://ilmargh.com/teaching/) into JSON and Markdown.

The scraper does not assume a particular page layout. It finds the main content
area, splits it into sections by headings, and keeps paragraphs, list items,
tables and links in page order.

Usage (Windows):
    py scrape_teaching.py
    py scrape_teaching.py --url https://ilmargh.com/teaching/ --out output
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_URL = "https://ilmargh.com/teaching/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
BLOCKS = HEADINGS + ["p", "li", "table", "pre", "blockquote", "dt", "dd", "figcaption"]
CONTENT_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", ".post", ".page"]


def fetch(url, retries=3, timeout=30):
    """Download the page, retrying on network errors and 5xx responses."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code < 500:
                resp.raise_for_status()
                # requests guesses ISO-8859-1 when no charset is sent; prefer detection.
                if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                return resp.text, resp.url
            print(f"Server error {resp.status_code}, attempt {attempt}/{retries}")
        except (requests.ConnectionError, requests.Timeout) as exc:
            print(f"Network error ({exc.__class__.__name__}), attempt {attempt}/{retries}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise SystemExit(f"Failed to download {url} after {retries} attempts.")


def clean(text):
    return " ".join(text.split())


def links_in(el, base_url):
    out = []
    for a in el.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "#")):
            continue
        out.append({"text": clean(a.get_text(" ")), "url": urljoin(base_url, href)})
    return out


def parse_table(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    return rows


def has_block_ancestor(el, root):
    """True if el sits inside another block we already capture (e.g. <p> inside <li>)."""
    parent = el.parent
    while parent is not None and parent is not root:
        if isinstance(parent, Tag) and parent.name in BLOCKS:
            return True
        parent = parent.parent
    return False


def find_content_root(soup):
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node and len(clean(node.get_text(" "))) > 50:
            return node
    return soup.body or soup


def scrape(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    meta = {}
    for m in soup.find_all("meta"):
        key = m.get("name") or m.get("property")
        if key and m.get("content"):
            meta[key] = m["content"].strip()

    nav_links = []
    for nav in soup.find_all("nav"):
        nav_links.extend(links_in(nav, base_url))

    for junk in soup(["script", "style", "noscript", "template", "svg"]):
        junk.decompose()

    root = find_content_root(soup)
    if root is soup.body:
        # Whole body is the fallback; drop site chrome so it doesn't pollute sections.
        for chrome in root.find_all(["nav", "header", "footer"]):
            chrome.decompose()

    sections = []
    current = {"heading": None, "level": 0, "items": []}
    for el in root.find_all(BLOCKS):
        if has_block_ancestor(el, root):
            continue
        if el.name in HEADINGS:
            if current["heading"] or current["items"]:
                sections.append(current)
            current = {"heading": clean(el.get_text(" ")), "level": int(el.name[1]), "items": []}
            continue
        if el.name == "table":
            rows = parse_table(el)
            if rows:
                current["items"].append({"type": "table", "rows": rows, "links": links_in(el, base_url)})
            continue
        text = clean(el.get_text(" "))
        if text:
            current["items"].append({"type": el.name, "text": text, "links": links_in(el, base_url)})
    if current["heading"] or current["items"]:
        sections.append(current)

    images = [
        {"alt": img.get("alt", "").strip(), "src": urljoin(base_url, img["src"])}
        for img in root.find_all("img", src=True)
    ]

    return {
        "url": base_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": clean(soup.title.get_text()) if soup.title else None,
        "meta": meta,
        "navigation": nav_links,
        "sections": sections,
        "links": links_in(root, base_url),
        "images": images,
    }


def to_markdown(data):
    lines = [f"# {data['title'] or data['url']}", "", f"Source: {data['url']}  ", f"Scraped: {data['scraped_at']}", ""]
    for section in data["sections"]:
        if section["heading"]:
            lines += ["#" * min(section["level"] + 1, 6) + " " + section["heading"], ""]
        for item in section["items"]:
            if item["type"] == "table":
                header, *body = item["rows"]
                width = max(len(r) for r in item["rows"])
                pad = lambda r: r + [""] * (width - len(r))
                lines.append("| " + " | ".join(pad(header)) + " |")
                lines.append("|" + " --- |" * width)
                lines += ["| " + " | ".join(pad(r)) + " |" for r in body]
                lines.append("")
            elif item["type"] in ("li", "dd"):
                lines.append(f"- {item['text']}")
            else:
                lines += [item["text"], ""]
        lines.append("")
    if data["links"]:
        lines += ["## Links", ""]
        lines += [f"- [{l['text'] or l['url']}]({l['url']})" for l in data["links"]]
    return "\n".join(lines).strip() + "\n"


def main():
    # The Windows console may not be UTF-8; never crash on non-ASCII output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help=f"page to scrape (default: {DEFAULT_URL})")
    parser.add_argument("--out", default="output", help="output folder (default: output)")
    parser.add_argument("--from-file", help="parse a saved .html file instead of downloading")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.from_file:
        html, final_url = Path(args.from_file).read_text(encoding="utf-8", errors="replace"), args.url
    else:
        print(f"Downloading {args.url} ...")
        html, final_url = fetch(args.url)
        (out_dir / "page.html").write_text(html, encoding="utf-8")

    data = scrape(html, final_url)
    (out_dir / "page.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "page.md").write_text(to_markdown(data), encoding="utf-8")

    print(f"Title:    {data['title']}")
    print(f"Sections: {len(data['sections'])}")
    for s in data["sections"]:
        if s["heading"]:
            print(f"  {'  ' * max(s['level'] - 1, 0)}- {s['heading']} ({len(s['items'])} items)")
    print(f"Links:    {len(data['links'])}")
    saved = "page.json, page.md" if args.from_file else "page.html, page.json, page.md"
    print(f"Saved to: {out_dir.resolve()}  ({saved})")


if __name__ == "__main__":
    main()
