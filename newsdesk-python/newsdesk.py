#!/usr/bin/env python3
"""
News desk: collects the stories from every source in sources.json and builds one web page.

    python newsdesk.py            build docs/index.html
    python newsdesk.py --open     build it and open it in your browser

On GitHub, .github/workflows/update-news.yml runs this every hour and publishes docs/ with
GitHub Pages. Stories are kept in data/archive.json between runs.

For each source the script tries, in order:
  1. The address as an RSS/Atom feed
  2. A feed the page advertises
  3. Reading the stories listed on the page: headline, date, summary and picture from each
     story's card, opening a story's own page only when its date or summary is missing
If all of that fails it tries the source's "fallback" links, if it has any.
Pages a site's robots.txt asks automated readers to avoid are skipped, requests to the same
website are spaced out, and story pages opened on earlier runs aren't opened again.

Options for each entry in sources.json:
    name      News company, shown in the "News company" filter (required)
    url       Feed or page to read (required)
    genre     One genre or a list, shown in the "Genre" filter
    region    "California", "US" or "International", shown in the "Region" filter
    section   Label shown in the update log, e.g. "Health"
    fallback  Backup link(s) to try when url fails
    more      Extra pages from the same site to read and add to this source
    method    "scrape" to skip feed detection, "json" for a JSON news list
    linkBase  For "json": address(es) to put in front of relative story links
    keywords  Keep only stories whose headline or summary contains one of these words
    enabled   false to turn the source off without deleting it
    debug     true to save each page read, and the stories picked from it, in debug/
"""
from __future__ import annotations

import argparse
import codecs
import html as htmlmod
import json
import math
import os
import re
import shutil
import threading
import time
import warnings
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import feedparser
import requests
from dateutil import parser as dateparser

warnings.filterwarnings("ignore", module="dateutil")

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"      # archive and other state, saved back to GitHub after each run
SITE_DIR = HERE / "docs"      # the published web page
LOG_DIR = HERE / "logs"
DEBUG_DIR = HERE / "debug"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PersonalNewsReader/1.0"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
TIMEOUT = 15          # seconds per request
MAX_PER_SOURCE = 100  # stories kept per source per run (feeds usually have 10-60)
MAX_LISTING = 60      # stories read from a news page that has no feed
MAX_ARTICLES = 15     # story pages opened per source to fill in a missing date or summary
ELLIPSIS = "\u2026"
ARCHIVE_VERSION = 2


def load_settings() -> dict:
    # settings.json: { "keepDays": 14, "parallel": 6, "politeSeconds": 1.5, "autoUpdateMinutes": 60 }
    settings = {"keepDays": 14, "parallel": 6, "politeSeconds": 1.5, "autoUpdateMinutes": 60}
    path = HERE / "settings.json"
    if path.exists():
        try:
            settings.update({k: v for k, v in json.loads(path.read_text("utf-8")).items() if v is not None})
        except (ValueError, OSError):
            print("settings.json could not be read; using the default settings.")
    return settings


SETTINGS = load_settings()
POLITE_SECONDS = float(SETTINGS["politeSeconds"])   # pause between requests to the same website

# Menu-style links to skip: matched against the link text, and separately against the address
JUNK_TEXT = re.compile(r"\b(newsletters?|subscribe|sign[ -]?up|log ?in|privacy policy|cookies?|terms of (use|service)|"
                       r"contact us|about us|donate|language access|site ?map)\b", re.I)
JUNK_PATH = re.compile(r"(newsletter|subscribe|sign-?up|login|privacy|cookie|/terms|/contact|careers|/jobs|donate|"
                       r"sitemap|language-?access)", re.I)
FILTER_LINK = re.compile(r"\(\s*\d[\d,]*\s*\)\s*$")   # "Malaria (338)"


class FetchError(Exception):
    """A website couldn't be reached or refused the request."""
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SourceError(Exception):
    """The page was read but couldn't be used."""


# ---------------------------------------------------------------- text and dates

TAG_RE = re.compile(r"<[^>]+>", re.S)
SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
WS_RE = re.compile(r"\s+")


def clean_text(text, limit: int = 320) -> str:
    """Strip HTML and extra spaces, and shorten to a readable length."""
    if not text or not str(text).strip():
        return ""
    text = str(text)
    for _ in range(2):   # some feeds escape their HTML twice
        text = SCRIPT_RE.sub(" ", text)
        text = TAG_RE.sub(" ", text)
        text = htmlmod.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
        text = cut.rstrip(",.;:") + ELLIPSIS
    return text


PROMO_RE = re.compile(r"\b(sign up|subscribe)( now)? (for|to) (the |our )?[\w&' -]{0,40}?(email|newsletter)s?\b[.:!]?", re.I)


def clean_summary(text) -> str:
    """Like clean_text, and removes newsletter promos that some feeds put inside summaries."""
    text = clean_text(text, 2000)
    text = PROMO_RE.sub(" ", text)
    text = re.sub(r"\b(read more|continue reading)[.:!]*\s*$", "", text, flags=re.I)
    return clean_text(WS_RE.sub(" ", text).strip())


TZINFOS = {"GMT": 0, "UTC": 0, "UT": 0, "Z": 0, "EST": -5 * 3600, "EDT": -4 * 3600, "CST": -6 * 3600,
           "CDT": -5 * 3600, "MST": -7 * 3600, "MDT": -6 * 3600, "PST": -8 * 3600, "PDT": -7 * 3600,
           "BST": 3600, "CET": 3600, "CEST": 7200}


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return utc_iso(datetime.now(timezone.utc))


def to_iso(value) -> str | None:
    """Any date from a feed or page as ISO-8601 UTC. A date with no time ("14 October 2026") is
    stored at 12:00 UTC so it stays on the right calendar day in US time zones."""
    if value is None or value == "":
        return None
    if isinstance(value, time.struct_time):
        return utc_iso(datetime(*value[:6], tzinfo=timezone.utc))
    if isinstance(value, datetime):
        return utc_iso(value if value.tzinfo else value.replace(tzinfo=timezone.utc))
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = dateparser.parse(s, tzinfos=TZINFOS, default=datetime(datetime.now().year, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return None
    if not re.search(r"\d:\d", s):
        return dt.strftime("%Y-%m-%dT12:00:00Z")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return utc_iso(dt)


def get_listing_date(text: str) -> str | None:
    """"October 15" has no year: assume this year, or last year if that would be in the future."""
    found = to_iso(text)
    if not found:
        return None
    dt = datetime.strptime(found[:10], "%Y-%m-%d")
    if not re.search(r"\d{4}", text) and dt > datetime.utcnow() + timedelta(days=2):
        dt -= timedelta(days=366 if dt.month > 2 and (dt.year % 4 == 0) else 365)
    return dt.strftime("%Y-%m-%dT12:00:00Z")


def get_ago_date(count: int, unit: str) -> str:
    unit = unit.lower()
    span = timedelta(minutes=count) if unit.startswith("m") else timedelta(hours=count) if unit.startswith("h") else timedelta(days=count)
    return utc_iso(datetime.now(timezone.utc) - span)


MONTHS = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
          r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?")
DATE_PATTERNS = [
    ("full", re.compile(rf"\b(?:{MONTHS})\.?\s+\d{{1,2}},?\s+20\d{{2}}\b", re.I)),
    ("full", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTHS})\.?,?\s+20\d{{2}}\b", re.I)),
    ("full", re.compile(r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/20\d{2}\b", re.I)),
    ("ago", re.compile(r"\b(\d{1,3})\s*(mins?|minutes?|hrs?|hours?|days?)\s+ago\b", re.I)),
    ("noyear", re.compile(rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}\b(?!,?\s*\d)", re.I)),
    ("noyear", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTHS})\b(?!\.?,?\s*\d)", re.I)),
]


def find_dates(text: str) -> list[dict]:
    """Every written date in plain text, with its position: "September 15, 2026", "15 Sept 2026",
    "09/15/2026", "Oct 15" (no year) and "3 hrs ago"."""
    found = []
    latest = utc_iso(datetime.now(timezone.utc) + timedelta(days=1))
    for kind, rx in DATE_PATTERNS:
        for m in rx.finditer(text):
            plain = re.sub(r"(?i)\bsept\b", "Sep", m.group(0)).replace(".", "")
            if kind == "ago":
                found_iso = get_ago_date(int(m.group(1)), m.group(2))
            elif kind == "noyear":
                found_iso = get_listing_date(plain)
            else:
                found_iso = to_iso(plain)
            if found_iso and found_iso <= latest:
                found.append({"kind": kind, "index": m.start(), "length": len(m.group(0)), "iso": found_iso})
    return sorted(found, key=lambda d: d["index"])


def find_date_in_url(url: str) -> str | None:
    """e.g. /2026/09/15/story or /2026-09-15-story"""
    m = re.search(r"/(20\d{2})[/-](0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])(?:[/-]|$)", url)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}T12:00:00Z" if m else None


def find_date_in_text(page: str) -> str | None:
    """A full written date near the top of a story page ("By A. Writer | September 15, 2026")."""
    start = -1
    for tag in ("<h1", "<article", "<main"):
        start = page.lower().find(tag)
        if start >= 0:
            break
    if start < 0:
        return None
    text = clean_text(page[start:start + 6000], 3000)
    full = [d for d in find_dates(text) if d["kind"] == "full"]
    return full[0]["iso"][:10] + "T12:00:00Z" if full else None


# ---------------------------------------------------------------- HTML helpers

ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def get_attrs(tag: str) -> dict:
    return {m.group(1).lower(): htmlmod.unescape(m.group(2) or m.group(3) or m.group(4) or "") for m in ATTR_RE.finditer(tag)}


def get_metas(page: str) -> dict:
    metas = {}
    for m in re.finditer(r"<meta\b[^>]*>", page, re.I | re.S):
        a = get_attrs(m.group(0))
        key = a.get("property") or a.get("name") or a.get("itemprop")
        if key and a.get("content") and key.lower() not in metas:
            metas[key.lower()] = a["content"]
    return metas


def pick(d: dict, keys) -> str | None:
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def host_name(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def site_family(url: str) -> str:
    """news.ox.ac.uk and globalhealth.ox.ac.uk are both "ox.ac.uk"."""
    parts = host_name(url).split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"ac", "co", "gov", "org", "com", "net", "edu", "nhs"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else ".".join(parts)


TRACKING = {"fbclid", "gclid", "cmp", "ref", "smid", "smtyp"}


def remove_tracking(url: str) -> str:
    """Remove utm_ and similar tracking parameters but keep real ones like ?id=123."""
    p = urlparse(url)
    base = urlunparse(p._replace(query="", fragment=""))
    if not p.query:
        return base
    keep = [part for part in p.query.split("&")
            if part and not (part.split("=")[0].lower().startswith("utm_") or part.split("=")[0].lower() in TRACKING)]
    return base + ("?" + "&".join(keep) if keep else "")


# ---------------------------------------------------------------- fetching, politely

_clock_lock = threading.Lock()
HOST_CLOCK: dict[str, float] = {}    # website -> time its next request may start
CRAWL_DELAYS: dict[str, float] = {}  # website -> delay its robots.txt asks for, in seconds
_local = threading.local()


def wait_for_turn(url: str) -> None:
    """Requests to the same website are spaced out so sites don't mistake the script for an attack."""
    site = (urlparse(url).hostname or "").lower()
    gap = max(POLITE_SECONDS, CRAWL_DELAYS.get(site, 0))
    with _clock_lock:
        now = time.monotonic()
        slot = max(HOST_CLOCK.get(site, now), now)
        HOST_CLOCK[site] = slot + gap
    wait = slot - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(HEADERS)
    return _local.session


def _short(error: Exception) -> str:
    text = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
    return text if len(text) <= 90 else text[:90] + ELLIPSIS


def _get(url: str) -> requests.Response:
    wait_for_turn(url)
    try:
        r = _session().get(url, timeout=TIMEOUT)
    except requests.Timeout:
        raise FetchError("the site took too long to answer") from None
    except requests.exceptions.SSLError:
        raise FetchError("the secure connection failed") from None
    except requests.ConnectionError:
        raise FetchError("could not connect") from None
    except requests.RequestException as e:
        raise FetchError(_short(e)) from None
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code}", r.status_code)
    return r


def get_page(url: str) -> tuple[str, str, bytes]:
    """Returns (text, content type, raw bytes). "Too many requests" or "busy": waits and tries once more."""
    try:
        r = _get(url)
    except FetchError as e:
        if e.status not in (429, 503):
            raise
        time.sleep(8)
        r = _get(url)
    raw = r.content
    ctype = r.headers.get("Content-Type", "")
    encoding = "utf-8"
    m = re.search(r"""(?:charset|encoding)\s*=\s*["']?([\w-]+)""", f"{ctype} {raw[:2048].decode('ascii', 'ignore')}", re.I)
    if m:
        try:
            codecs.lookup(m.group(1))
            encoding = m.group(1)
        except LookupError:
            pass
    return raw.decode(encoding, errors="replace"), ctype, raw


# ---------------------------------------------------------------- robots.txt

_robots_lock = threading.Lock()
ROBOTS: dict[str, list] = {}         # website -> rules
ROBOTS_FETCHED: dict[str, str] = {}  # website -> when its robots.txt was read (kept for a day)


def read_robots(text: str) -> list[dict]:
    """Rules from robots.txt that apply to all readers (User-agent: *)."""
    rules, applies, in_agents = [], False, False
    for line in text.splitlines():
        line = re.sub(r"#.*", "", line).strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not in_agents:
                applies = False
            if value == "*" or re.search("personalnewsreader", value, re.I):
                applies = True
            in_agents = True
            continue
        in_agents = False
        if applies and key == "crawl-delay":
            try:
                rules.append({"crawlDelay": min(float(value), 30.0)})
            except ValueError:
                pass
            continue
        if applies and value and key in ("allow", "disallow"):
            rx = "^" + re.escape(value).replace(r"\*", ".*")
            if rx.endswith(r"\$"):
                rx = rx[:-2] + "$"
            rules.append({"allow": key == "allow", "regex": rx, "length": len(value)})
    return rules


def robots_allowed(url: str) -> bool:
    u = urlparse(url)
    root = f"{u.scheme}://{u.netloc}"
    with _robots_lock:
        known = root in ROBOTS
    if not known:
        try:
            rules = read_robots(get_page(root + "/robots.txt")[0])
        except Exception:
            rules = []   # no robots.txt means no restrictions
        with _robots_lock:
            ROBOTS[root] = rules
            ROBOTS_FETCHED[root] = now_iso()
    rules = ROBOTS[root]
    for r in rules:
        if "crawlDelay" in r:
            CRAWL_DELAYS[(u.hostname or "").lower()] = r["crawlDelay"]
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    best = None
    for r in rules:   # the longest matching rule wins
        if "crawlDelay" in r:
            continue
        if re.match(r["regex"], path, re.I) and (best is None or r["length"] > best["length"]):
            best = r
    return best is None or best["allow"]


# ---------------------------------------------------------------- feeds and JSON lists

def parse_feed(raw: bytes) -> list[dict]:
    parsed = feedparser.parse(raw)
    items = []
    for e in parsed.entries:
        if len(items) >= MAX_PER_SOURCE:
            break
        title = clean_text(e.get("title"), 300)
        link = e.get("link")
        if not link and re.match(r"https?://", e.get("id", "") or ""):
            link = e.get("id")
        if not link or not title:
            continue
        body = e.get("summary") or e.get("description")
        if not body and e.get("content"):
            body = e["content"][0].get("value")
        image = None
        for key in ("media_thumbnail", "media_content"):
            media = e.get(key)
            if media and media[0].get("url"):
                image = media[0]["url"]
                break
        if not image:
            for enc in e.get("enclosures") or []:
                if (enc.get("type") or "").startswith("image"):
                    image = enc.get("href") or enc.get("url")
                    break
        items.append({
            "title": title,
            "link": link,
            "summary": clean_summary(body),
            # The date as written comes first, so a date with no time stays on its calendar day
            "date": to_iso(e.get("published") or e.get("updated")) or to_iso(e.get("published_parsed") or e.get("updated_parsed")),
            "image": image,
            "tags": [t.get("term") for t in (e.get("tags") or []) if t.get("term")][:5],
        })
    return items


def find_feed_link(page: str, base: str) -> str | None:
    for m in re.finditer(r"<link\b[^>]*>", page, re.I | re.S):
        a = get_attrs(m.group(0))
        if re.search("alternate", a.get("rel", ""), re.I) and re.search("rss|atom", a.get("type", ""), re.I) and a.get("href"):
            return urljoin(base, a["href"])
    return None


def parse_json_list(text: str, link_bases: list[str]) -> list[dict]:
    """News lists in JSON, such as WHO's site data: { "value": [ { Title, ItemDefaultUrl, PublicationDateAndTime, NewsType } ] }"""
    data = json.loads(text)
    rows = data["value"] if isinstance(data, dict) and "value" in data else data
    rows = [r for r in (rows if isinstance(rows, list) else [rows])
            if isinstance(r, dict) and r.get("Title") and r.get("ItemDefaultUrl")][:MAX_PER_SOURCE]
    if not rows:
        return []
    # Item addresses can be relative ("/16-10-2026-story"). Use the first base address that opens a real story.
    base = None
    first = str(rows[0]["ItemDefaultUrl"])
    if not re.match(r"https?://", first, re.I):
        for b in link_bases:
            if read_article(b.rstrip("/") + "/" + first.lstrip("/"), ""):
                base = b
                break
        if not base:
            raise SourceError("Could not work out the story links from the site data")
    items = []
    for r in rows:
        u = str(r["ItemDefaultUrl"])
        items.append({
            "title": clean_text(str(r["Title"]), 300),
            "link": u if re.match(r"https?://", u, re.I) else base.rstrip("/") + "/" + u.lstrip("/"),
            "summary": "",
            "date": to_iso(r.get("PublicationDateAndTime")),
            "image": None,
            "tags": [str(r["NewsType"])] if r.get("NewsType") else [],
        })
    # The list has no summaries or pictures: read them from the stories' pages (once; then remembered)
    opened = 0
    for item in items:
        art = KNOWN.get(item["link"])
        if not art:
            if opened >= MAX_ARTICLES:
                continue
            opened += 1
            art = read_article(item["link"], item["title"])
        if art:
            item["summary"] = art.get("summary") or item["summary"]
            item["image"] = art.get("image") or item["image"]
    return items


# ---------------------------------------------------------------- story pages

def read_article(url: str, link_text: str) -> dict | None:
    if not robots_allowed(url):
        return None
    try:
        page = get_page(url)[0]
    except Exception:
        return None
    meta = get_metas(page)
    date = pick(meta, ["article:published_time", "og:published_time", "parsely-pub-date", "pubdate",
                       "publishdate", "date", "dc.date", "datepublished"])
    if not date:
        m = re.search(r"""<time\b[^>]*\bdatetime\s*=\s*["']([^"']+)""", page, re.I | re.S)
        date = m.group(1) if m else None
    if not date:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
        date = m.group(1) if m else None
    date = date or find_date_in_url(url) or find_date_in_text(page)

    title = pick(meta, ["og:title", "twitter:title"])
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = m.group(1) if m else link_text
    summary = pick(meta, ["og:description", "description", "twitter:description"])
    if not summary:
        start = max(page.lower().find("<article"), 0)
        m = re.search(r"<p\b[^>]*>(.*?)</p>", page[start:], re.I | re.S)
        summary = m.group(1) if m else ""
    section = pick(meta, ["article:section"])
    return {
        "siteName": pick(meta, ["og:site_name", "application-name"]),
        "title": clean_text(title or link_text, 300),
        "link": url,
        "summary": clean_summary(summary),
        "date": to_iso(date),
        "image": pick(meta, ["og:image", "twitter:image"]),
        "tags": [section] if section else [],
    }


# ---------------------------------------------------------------- list pages

A_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.I | re.S)
HEADING_RE = re.compile(r"<h[2-4]\b[^>]*>(.*?)</h[2-4]>", re.I | re.S)
JS_URL_RE = re.compile(r"""['"]((?:https?://|/|\.\.?/)?[\w./~-]+\.(?:cfm|aspx?|html?|php|jsp)(?:\?[^'"]*)?)['"]""")
ONCLICK_RE = re.compile(r"<(tr|li|div|td)\b([^>]*\bonclick\s*=[^>]*)>(.*?)</\1>", re.I | re.S)


def get_link_candidates(page: str, headings_only: bool = False) -> list[dict]:
    """Story links on a page, each with the position of its headline.
    A link counts as a headline if it sits inside <h2>-<h4>, or wraps one (common for whole-card links).
    Links opened by JavaScript (onclick="location='detail.cfm?id=1'") are included too."""
    headings = list(HEADING_RE.finditer(page))
    anchors = list(A_RE.finditer(page))
    found = []
    for m in anchors:
        a = get_attrs(m.group(1))
        href = a.get("href")
        if not href or re.match(r"(javascript:|#)", href, re.I):
            j = JS_URL_RE.search(f"{href or ''} {a.get('onclick', '')}")
            if not j:
                continue
            href = j.group(1)
        if re.match(r"(mailto|tel):", href, re.I):
            continue
        h = HEADING_RE.search(m.group(2))
        if h:   # the link wraps a headline
            start = m.start(2) + h.start()
            found.append({"href": href, "text": h.group(1), "start": start, "end": start + len(h.group(0))})
            continue
        in_heading = any(hd.start() <= m.start() < hd.end() for hd in headings)
        if headings_only and not in_heading:
            continue
        found.append({"href": href, "text": m.group(2), "start": m.start(), "end": m.end()})

    # Headlines with no link of their own (the link is on the picture or a "Read more" button):
    # use the nearest link in the same story card
    for hd in headings:
        if re.search(r"<a\b", hd.group(0), re.I):
            continue
        if any(m.start() < hd.start() and m.end() >= hd.end() for m in anchors):
            continue   # already inside a whole-card link
        best, best_dist = None, 1500
        for m in anchors:
            if m.end() <= hd.start():
                dist = hd.start() - m.end()
            elif m.start() >= hd.end():
                dist = m.start() - hd.end()
            else:
                continue
            if dist >= best_dist:
                continue
            href = get_attrs(m.group(1)).get("href")
            if href and not re.match(r"(javascript:|#|mailto:|tel:)", href, re.I):
                best, best_dist = href, dist
        if best:
            found.append({"href": best, "text": hd.group(1), "start": hd.start(), "end": hd.end()})

    if not headings_only:
        for m in ONCLICK_RE.finditer(page):
            j = JS_URL_RE.search(get_attrs(m.group(2)).get("onclick", ""))
            if j:
                found.append({"href": j.group(1), "text": m.group(3), "start": m.start(), "end": m.end()})
    return found


LIST_DATE_RE = re.compile(r"^((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)\s+(.*)$")


def select_headlines(candidates: list[dict], base: str) -> list[dict]:
    """Keeps story links: drops menus, duplicates, other websites, filter links and short or top-level links."""
    site = site_family(base)
    base_path = urlparse(base).path.rstrip("/")
    seen, picked = set(), []
    for c in candidates:
        try:
            absolute = urljoin(base, htmlmod.unescape(c["href"]).strip())
        except ValueError:
            continue
        u = urlparse(absolute)
        if u.scheme not in ("http", "https"):
            continue
        href = remove_tracking(absolute)
        text = clean_text(c["text"], 300)
        # Listing rows often start with the date ("October 15  Heat advisory..."): use it as the date
        list_date = None
        d = LIST_DATE_RE.match(text)
        if d:
            list_date, text = get_listing_date(d.group(1)), d.group(2)
        if site_family(href) != site or href in seen or len(text) < 25 or href == base:
            continue
        if JUNK_TEXT.search(text) or JUNK_PATH.search(u.path):
            continue
        # Filter links on list pages: "Malaria (338)", or the list itself with ?page= or ?f= added
        if FILTER_LINK.search(text) or (u.query and u.path.rstrip("/") == base_path):
            continue
        path = u.path.strip("/")
        if len(path.split("/")) < 2 and not re.search(r"\d", path) and not u.query:
            continue
        seen.add(href)
        picked.append({"href": href, "text": text, "listDate": list_date, "start": c["start"], "end": c["end"]})
        if len(picked) >= MAX_LISTING:
            break
    return sorted(picked, key=lambda x: x["start"])


TIME_ATTR_RE = re.compile(r"""<time\b[^>]*\bdatetime\s*=\s*["']([^"']+)""", re.I | re.S)
IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)


def get_card_info(before: str, after: str, base: str, link: str) -> dict:
    """Date, summary and picture for one story on a list page. before and after are the parts of
    the page just before and just after its headline, up to the next story. When there is a choice,
    whatever sits closest to the headline wins."""
    info = {"date": None, "summary": "", "image": None}

    # Date: a machine-readable <time datetime="...">, else a written date
    tb, ta = list(TIME_ATTR_RE.finditer(before)), list(TIME_ATTR_RE.finditer(after))
    best, dist = None, math.inf
    if tb:
        best, dist = tb[-1].group(1), len(before) - tb[-1].start()
    if ta and ta[0].start() < dist:
        best = ta[0].group(1)
    if best:
        info["date"] = to_iso(best)
    if not info["date"]:
        text_before, text_after = clean_text(before, 100000), clean_text(after, 100000)
        db, da = find_dates(text_before), find_dates(text_after)
        dist = math.inf
        if db:
            last = db[-1]
            info["date"], dist = last["iso"], len(text_before) - (last["index"] + last["length"])
        if da and da[0]["index"] < dist:
            info["date"] = da[0]["iso"]

    # Summary: the first real paragraph after the headline, before the next heading
    # or a link to a different story
    cut = len(after)
    h = re.search(r"<h[1-6]\b", after, re.I)
    if h:
        cut = h.start()
    own_path = urlparse(link).path.rstrip("/")
    for m in re.finditer(r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)""", after, re.I | re.S):
        if m.start() >= cut:
            break
        try:
            path = urlparse(urljoin(base, htmlmod.unescape(m.group(1)))).path.rstrip("/")
        except ValueError:
            continue
        if own_path and path != own_path:
            cut = m.start()
            break
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", after[:cut], re.I | re.S):
        t = clean_summary(m.group(1))
        lead = next((d for d in find_dates(t) if d["index"] == 0), None)
        if lead:   # "September 25, 2026 * The treaty..." -> "The treaty..."
            t = re.sub(r"^\s*[-|:\u2022\u00b7]+\s*", "", t[lead["length"]:]).strip()
        if len(t) >= 40:
            info["summary"] = t
            break

    # Picture: the nearest <img>, skipping tiny inline placeholders and logos
    images = [(len(before) - m.start(), m.group(0)) for m in IMG_RE.finditer(before)]
    images += [(m.start(), m.group(0)) for m in IMG_RE.finditer(after)]
    for _, tag in sorted(images, key=lambda x: x[0]):
        a = get_attrs(tag)
        src = pick(a, ["data-src", "data-original", "src"])
        if (not src or src.startswith("data:")) and a.get("srcset"):
            src = re.split(r"[\s,]+", a["srcset"].strip())[0]
        if not src or src.startswith("data:") or re.search(r"\.svg(\?|$)|logo|placeholder|spacer|pixel", src, re.I):
            continue
        info["image"] = urljoin(base, src)
        break
    return info


def scrape_listing(page: str, base: str) -> list[dict]:
    # Where to look, best first: the page's main content area (minus menus; story cards there often
    # have their own small <header>, which must stay), then the page without its header, footer,
    # menus and sidebars, then the whole page
    areas = []
    main = re.search(r"<main\b.*?</main>", page, re.I | re.S)
    if main:
        areas.append(re.sub(r"<nav\b.*?</nav>", " ", main.group(0), flags=re.I | re.S))
    areas.append(re.sub(r"<(nav|header|footer|aside)\b.*?</\1>", " ", page, flags=re.I | re.S))
    areas.append(page)

    # Prefer headline links (3 or more); otherwise use all links
    src, links = None, []
    for headings_only in (True, False):
        for area in areas:
            links = select_headlines(get_link_candidates(area, headings_only), base)
            if len(links) >= 3:
                src = area
                break
        if src is not None:
            break
    if src is None:
        src = areas[-1]
        links = select_headlines(get_link_candidates(src, True), base) or select_headlines(get_link_candidates(src), base)

    # Read each story's card on the list page: the part between the previous and next headline
    items = []
    for i, l in enumerate(links):
        start = links[i - 1]["end"] if i > 0 else 0
        end = links[i + 1]["start"] if i < len(links) - 1 else len(src)
        start = min(l["start"], max(start, l["start"] - 3000))
        end = max(l["end"], min(end, l["end"] + 3000))
        card = get_card_info(src[start:l["start"]], src[l["end"]:end], base, l["href"])
        items.append({"title": l["text"], "link": l["href"], "summary": card["summary"],
                      "date": card["date"] or l["listDate"], "image": card["image"], "tags": []})

    # Open story pages only where the list page had no date or summary (undated ones first),
    # reusing what earlier runs found
    opened = 0
    for item in [x for x in items if not x["date"]] + [x for x in items if x["date"] and not x["summary"]]:
        art = KNOWN.get(item["link"])
        if not art:
            if opened >= MAX_ARTICLES:
                continue
            opened += 1
            art = read_article(item["link"], item["title"])
            if not art:
                continue
        item["date"] = item["date"] or art.get("date")
        item["summary"] = item["summary"] or art.get("summary") or ""
        item["image"] = item["image"] or art.get("image")
        if art.get("tags"):
            item["tags"] = list(art["tags"])

    # Some sites give every page the same description (e.g. the agency's motto): drop repeats,
    # and anything matching the list page's own description
    tagline = clean_summary(pick(get_metas(page), ["og:description", "description", "twitter:description"]))
    counts: dict[str, int] = {}
    for item in items:
        if tagline and item["summary"] == tagline:
            item["summary"] = ""
        if item["summary"]:
            counts[item["summary"]] = counts.get(item["summary"], 0) + 1
    for item in items:
        if item["summary"] and counts[item["summary"]] > 1:
            item["summary"] = ""

    # When most stories have a date, the undated ones are usually promos or menu pages
    dated = sum(1 for x in items if x["date"])
    if dated >= math.ceil(len(items) / 2):
        return [x for x in items if x["date"]]
    return items


# ---------------------------------------------------------------- one source

def save_debug(name: str, text: str) -> None:
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        (DEBUG_DIR / re.sub(r"[^\w .-]", "", name)).write_text(text, "utf-8")
    except OSError:
        pass


def items_from_url(url: str, method: str, label: str, link_bases: list[str], save_copy: bool = False) -> dict:
    page_text = None
    try:
        if not re.search(r"(rss|feed|atom|\.xml)", url, re.I) and not robots_allowed(url):
            return {"error": "Skipped - the site asks automated readers not to visit this page", "method": None, "items": []}
        text, ctype, raw = get_page(url)
        page_text = text
        head = text[:500].lstrip("\ufeff \r\n\t").lower()
        is_feed = bool(re.search(r"xml|rss|atom", ctype, re.I)) or head.startswith("<?xml") or "<rss" in head or "<feed" in head

        if method == "json":
            items = parse_json_list(text, link_bases)
            result = {"error": None if items else "The site data had no stories", "method": "site data", "items": items}
        else:
            items, how = [], None
            if method != "scrape" and is_feed:
                try:
                    items, how = parse_feed(raw), "feed"
                except Exception:
                    items = []
            if not items and method != "scrape":
                feed_url = find_feed_link(text, url)
                if feed_url:
                    try:
                        items, how = parse_feed(get_page(feed_url)[2]), "feed (auto-detected)"
                    except Exception:
                        items = []
            if not items:
                items, how = scrape_listing(text, url), "scrape"
            if items:
                result = {"error": None, "method": how, "items": items}
            else:
                save_debug(f"{label}.html", text)
                result = {"error": "No articles found on this page (copy saved in the debug folder)", "method": how, "items": []}
    except FetchError as e:
        if e.status in (401, 403, 429):
            why = f"HTTP {e.status} - the site blocks automated readers"
        else:
            why = f"HTTP {e.status}" if e.status else str(e)
        result = {"error": f"Couldn't reach the site ({why})", "method": None, "items": []}
    except SourceError as e:
        result = {"error": str(e), "method": None, "items": []}
    except Exception as e:   # one broken page must not stop the run
        result = {"error": f"Unexpected problem: {_short(e)}", "method": None, "items": []}

    if save_copy and page_text:
        # Diagnostic copy: the page as the script received it, and the stories it picked
        tag = " " + re.sub(r"\W", "", urlparse(url).query) if urlparse(url).query else ""
        save_debug(f"{label}{tag}.html", page_text)
        lines = [f"Address: {url}",
                 f"Result: {result['error'] or str(len(result['items'])) + ' stories via ' + str(result['method'])}", ""]
        lines += [f"{i.get('date')} | {i['title']} | {i['link']} | {i.get('summary') or ''}" for i in result["items"]]
        save_debug(f"{label}{tag} picks.txt", "\n".join(lines))
    return result


def main_items(src: dict) -> dict:
    method = src.get("method") or "auto"
    bases = [str(b) for b in as_list(src.get("linkBase"))]
    result = None
    for url in [src["url"]] + as_list(src.get("fallback")):
        # The source's method applies to its main link; backup links are detected automatically
        result = items_from_url(url, method if url == src["url"] else "auto", src["name"], bases, bool(src.get("debug")))
        if not result["error"]:
            if url != src["url"]:
                result["method"] += " from backup link"
            return result
    return result


def source_items(src: dict) -> dict:
    result = main_items(src)
    extra = as_list(src.get("more"))
    if result["error"] or not extra:
        return result
    # "more": extra pages from the same site, read and added to this source's stories
    seen = {i["link"] for i in result["items"]}
    pages, notes = 1, []
    for url in extra:
        r = items_from_url(url, "auto", src["name"], [], bool(src.get("debug")))
        if r["error"]:
            notes.append(f"{url} - {r['error']}")
            continue
        pages += 1
        for i in r["items"]:
            if i["link"] not in seen:
                seen.add(i["link"])
                result["items"].append(i)
    result["method"] += f" ({pages} of {len(extra) + 1} pages)"
    result["pageNotes"] = notes
    return result


def as_list(value) -> list:
    if value is None or value == "":
        return []
    return [v for v in (value if isinstance(value, list) else [value]) if v]


# ---------------------------------------------------------------- the run

KNOWN: dict[str, dict] = {}   # stories already in the archive: their pages aren't opened again


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the news desk page.")
    ap.add_argument("--sources", default=HERE / "sources.json", type=Path)
    ap.add_argument("--open", action="store_true", help="open the page when done")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    SITE_DIR.mkdir(exist_ok=True)
    archive_path, backup_path = DATA_DIR / "archive.json", DATA_DIR / "archive.backup.json"
    health_path, robots_path = DATA_DIR / "source-health.json", DATA_DIR / "robots-cache.json"
    log: list[str] = []

    def say(text: str) -> None:
        print(text, flush=True)
        log.append(f"{datetime.now():%H:%M:%S}  {text}")

    sources = [s for s in json.loads(args.sources.read_text("utf-8")) if s.get("enabled", True) is not False]

    # ---- archive: stories from earlier runs (falls back to the backup copy if the file is damaged)
    archive: dict[str, dict] = {}
    archive_read_ok = False
    for path in (archive_path, backup_path):
        if not path.exists():
            continue
        try:
            saved = read_json(path, {})
            if isinstance(saved, dict) and saved.get("version") == ARCHIVE_VERSION:
                for a in saved.get("articles", []):
                    if a.get("link"):
                        a["firstSeen"], a["date"] = to_iso(a.get("firstSeen")), to_iso(a.get("date"))
                        archive[a["link"]] = a
            archive_read_ok = path == archive_path
            if path == backup_path:
                say("archive.json could not be read, so the backup copy was used.")
            break
        except (ValueError, OSError):
            say(f"{path.name} could not be read.")
    for link, a in archive.items():
        KNOWN[link] = {"date": a.get("date"), "summary": a.get("summary") or "", "image": a.get("image"),
                       "tags": [t for t in a.get("tags") or [] if t]}

    # ---- robots.txt rules saved on earlier runs (re-read after a day)
    try:
        day_ago = utc_iso(datetime.now(timezone.utc) - timedelta(days=1))
        for root, entry in read_json(robots_path, {}).items():
            fetched = to_iso(entry.get("fetched"))
            if fetched and fetched >= day_ago:
                ROBOTS[root], ROBOTS_FETCHED[root] = entry.get("rules", []), fetched
    except (ValueError, OSError, AttributeError):
        pass

    # ---- source health: how each source did on recent runs
    health: dict[str, dict] = {}
    try:
        health = {k: {"counts": [int(c) for c in v.get("counts", [])], "lastOk": to_iso(v.get("lastOk"))}
                  for k, v in read_json(health_path, {}).items()}
    except (ValueError, OSError, AttributeError):
        say("source-health.json could not be read; source history starts fresh.")

    # ---- fetch every source, several at the same time
    started = datetime.now(timezone.utc)
    started_iso = utc_iso(started)
    workers = max(1, int(SETTINGS["parallel"]))
    say(f"Fetching {len(sources)} sources, {workers} at a time.")
    results: list[dict | None] = [None] * len(sources)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(source_items, s): n for n, s in enumerate(sources)}
        for done, future in enumerate(as_completed(futures), 1):
            n = futures[future]
            try:
                results[n] = future.result()
            except Exception as e:
                results[n] = {"error": f"Unexpected problem: {_short(e)}", "method": None, "items": []}
            print(f"  {done} of {len(sources)} sources done", end="\r", flush=True)
    print(" " * 40, end="\r")

    # ---- combine the results, in the order of sources.json
    source_info, health_report = [], []
    this_run: dict[str, dict] = {}
    this_run_titles: set[str] = set()
    scraped_ok: set[str] = set()   # news companies whose pages were read successfully this run
    for src, r in zip(sources, results):
        label = src["name"] + (f" ({src['section']})" if src.get("section") else "")
        genres = [g for g in as_list(src.get("genre"))]
        # "keywords": keep only stories whose headline or summary mentions one of them
        keyword_rx = None
        if src.get("keywords"):
            keyword_rx = re.compile(r"\b(" + "|".join(re.escape(str(k)) for k in as_list(src["keywords"])) + ")", re.I)
        kept = new = 0
        for item in r["items"]:
            # Headlines from news aggregators end with the source's name ("... - Reuters")
            item["title"] = re.sub(r"\s+[-|]\s+" + re.escape(src["name"]) + r"\s*$", "", item["title"])
            # A summary that starts by repeating the headline keeps only the rest
            if item.get("summary") and item["summary"].lower().startswith(item["title"].lower()):
                rest = item["summary"][len(item["title"]):].lstrip(" .:-,")
                item["summary"] = rest if len(rest) >= 25 else ""
            if keyword_rx and not keyword_rx.search(f"{item['title']} {item.get('summary') or ''}"):
                continue
            # The same story can come from two places (the site's feed and Google News): keep one
            title_key = src["name"] + "|" + re.sub(r"[^a-z0-9]", "", item["title"].lower())
            if title_key in this_run_titles:
                continue
            this_run_titles.add(title_key)
            kept += 1
            if item["link"] in this_run:   # same story listed in two sections
                first = this_run[item["link"]]
                first["genre"] = sorted(set(first["genre"]) | set(genres))
                continue
            old = archive.get(item["link"])
            item.update(source=src["name"], genre=genres, region=src.get("region") or "",
                        firstSeen=(old or {}).get("firstSeen") or started_iso)
            item.pop("siteName", None)
            this_run[item["link"]] = item
            new += 0 if old else 1
            archive[item["link"]] = item
        if not r["error"] and "scrape" in (r["method"] or ""):
            scraped_ok.add(src["name"])

        # Source health: compare with this source's recent runs
        h = health.get(label, {"counts": [], "lastOk": None})
        previous = list(h["counts"])
        usual = sorted(previous)[len(previous) // 2] if len(previous) >= 3 else None
        if r["error"]:
            status = "fail"
            if h["lastOk"]:
                when = datetime.strptime(h["lastOk"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
                message = f"{r['error']}. Last worked {when:%b %d, %Y %I:%M %p}."
            else:
                message = f"{r['error']}. It hasn't worked yet."
            say(f"FAILED  {label} - {r['error']}")
        else:
            h["counts"], h["lastOk"] = (previous + [kept])[-10:], started_iso
            status, message = "ok", ""
            if kept == 0:
                status, message = "warn", "Found no stories this time. The site may have changed."
            elif usual and usual >= 5 and kept < 0.3 * usual:
                status, message = "warn", f"Found {kept} stories; usually about {usual}. The site may have changed."
            count = f"{kept} of {len(r['items'])} stories match the keywords" if keyword_rx else f"{len(r['items'])} stories"
            say(f"OK      {label} - {count} via {r['method']} ({new} new)")
            notes = r.get("pageNotes") or []
            for note in notes:
                say(f"        Page not read: {note}")
            if notes and status == "ok":
                status, message = "warn", f"{len(notes)} of its extra pages couldn't be read: {notes[0].split(' - ', 1)[-1]}"
            if status == "warn":
                say(f"        Check this source: {message}")
        health[label] = h
        health_report.append({"label": label, "name": src["name"], "status": status, "message": message,
                              "count": kept, "usual": usual, "lastOk": h["lastOk"], "url": src["url"]})
        source_info.append({"name": src["name"], "section": src.get("section"), "genre": genres,
                            "region": src.get("region") or "", "url": src["url"], "error": r["error"], "method": r["method"]})

    # ---- clean the archive: undated items from a page that no longer lists them, and filter links
    removed = 0
    for link in list(archive):
        a = archive[link]
        stale = a.get("source") in scraped_ok and link not in this_run and not a.get("date")
        if stale or FILTER_LINK.search(str(a.get("title") or "")):
            del archive[link]
            removed += 1
    if removed:
        say(f"Removed {removed} outdated entries from the archive.")

    # ---- save: archive (keeping a backup of the previous one), robots.txt rules, source health, the page, the log
    cutoff = utc_iso(started - timedelta(days=int(SETTINGS["keepDays"])))
    articles = sorted((a for a in archive.values() if (a.get("firstSeen") or "") >= cutoff),
                      key=lambda a: (a.get("date") or "", a.get("firstSeen") or ""), reverse=True)
    if archive_read_ok:
        shutil.copyfile(archive_path, backup_path)
    write_json(archive_path, {"version": ARCHIVE_VERSION, "articles": articles})
    write_json(robots_path, {k: {"fetched": ROBOTS_FETCHED[k], "rules": v} for k, v in ROBOTS.items() if k in ROBOTS_FETCHED})
    write_json(health_path, health, indent=2)

    repo = os.environ.get("GITHUB_REPOSITORY")   # "owner/name" when running on GitHub
    workflow = os.environ.get("NEWSDESK_WORKFLOW", "update-news.yml")
    config = {
        "actionsUrl": f"https://github.com/{repo}/actions/workflows/{workflow}" if repo else None,
        "updateEveryMinutes": int(SETTINGS["autoUpdateMinutes"]),
    }
    data = {"generated": started_iso, "sources": source_info, "health": health_report, "articles": articles}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = (HERE / "template.html").read_text("utf-8")
    page = template.replace("/*__DATA__*/null", payload).replace("/*__CONFIG__*/null", json.dumps(config))
    (SITE_DIR / "index.html").write_text(page, "utf-8")
    next_update = started + timedelta(minutes=int(SETTINGS["autoUpdateMinutes"]))
    write_json(SITE_DIR / "status.json", {"generated": started_iso, "nextUpdate": utc_iso(next_update)})
    (SITE_DIR / ".nojekyll").write_text("", "utf-8")

    failed = sum(1 for h in health_report if h["status"] == "fail")
    warned = sum(1 for h in health_report if h["status"] == "warn")
    say(f"Wrote {len(articles)} stories to {SITE_DIR / 'index.html'}. {failed} sources failed, {warned} need a check.")
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with open(LOG_DIR / f"update-{datetime.now():%Y-%m-%d}.log", "a", encoding="utf-8") as f:
            f.write("\n".join(log) + "\n\n")
        for old in LOG_DIR.glob("update-*.log"):
            if old.stat().st_mtime < time.time() - 30 * 86400:
                old.unlink()
    except OSError:
        pass
    if args.open:
        webbrowser.open((SITE_DIR / "index.html").as_uri())


def write_json(path: Path, data, indent=None) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")), "utf-8")


if __name__ == "__main__":
    main()
