#!/usr/bin/env python3
"""Firmament Voyage Global - daily insights feed.
Reads the RSS/Atom feeds in feeds.json (next to this file), keeps items relevant to
students, careers and young people, and writes a small JSON file for the website.
Only headlines, short excerpts and links are kept; every item links to its source.
Usage:  news.py OUTPUT.json        update the feed file
        news.py --check            show which feeds work (writes nothing)"""
import json, os, re, sys, html, socket, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (compatible; FVG-InsightsBot/1.0; +https://summitbrilliance.com)"
MAX_ITEMS, MAX_AGE_DAYS = 60, 60
KEYWORDS = {
 "uni": r"student|undergrad|graduate|admission|scholarship|career|job|employ|alumni|commencement|education|learning|teaching|campus|internship|young|youth|future of work|skills|AI\b|artificial intelligence|degree|course|summer",
 "talks": r"career|work|job|learn|education|student|young|youth|gen z|future|leader|success|skill|purpose|school|college|universit|graduate|mentor|confidence|ambition|AI\b|artificial intelligence|habit|focus|motivation|decision",
}
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/", "content": "http://purl.org/rss/1.0/modules/content/"}
socket.setdefaulttimeout(20)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8"})
    with urllib.request.urlopen(req) as r:
        return r.read(3_000_000), r.geturl()

def discover(page, base):
    txt = page.decode("utf-8", "ignore")
    for m in re.finditer(r"<link[^>]+>", txt, re.I):
        tag = m.group(0)
        if re.search(r"rel=[\"']?alternate", tag, re.I) and re.search(r"(rss|atom)\+xml", tag, re.I):
            h = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if h: return urllib.parse.urljoin(base, html.unescape(h.group(1)))
    return None

def clean(s, n=240):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"

def pdate(s):
    s = (s or "").strip()
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def txt(el, path):
    x = el.find(path, NS)
    return (x.text or "") if x is not None else ""

def parse(data):
    root = ET.fromstring(data)
    out = []
    if root.tag.endswith("feed"):  # Atom (YouTube etc.)
        for e in root.findall("a:entry", NS):
            link = ""
            for l in e.findall("a:link", NS):
                if l.get("rel", "alternate") == "alternate": link = l.get("href", ""); break
            thumb = e.find(".//media:thumbnail", NS)
            out.append({"title": txt(e, "a:title"), "link": link,
                        "date": txt(e, "a:published") or txt(e, "a:updated"),
                        "summary": txt(e, "a:summary") or txt(e, ".//media:description") or txt(e, "a:content"),
                        "image": thumb.get("url") if thumb is not None else ""})
    else:  # RSS 2.0
        for i in root.iter("item"):
            src = i.find("source")
            out.append({"title": txt(i, "title"), "link": txt(i, "link").strip(), "date": txt(i, "pubDate") or txt(i, "{http://purl.org/dc/elements/1.1/}date"),
                        "summary": txt(i, "description"), "image": "", "src": (src.text if src is not None else "")})
    return out

def fetch_feed(f):
    data, final = get(f["url"])
    head = data[:600].lstrip().lower()
    if head.startswith(b"<!doctype html") or b"<html" in head:
        feed = discover(data, final)
        if not feed: raise ValueError("no RSS feed found on page")
        data, final = get(feed)
    return parse(data), final

def run(check=False):
    cfg = json.load(open(os.path.join(HERE, "feeds.json"), encoding="utf-8"))
    now = datetime.now(timezone.utc); oldest = now - timedelta(days=MAX_AGE_DAYS)
    items, seen = [], set()
    for f in cfg["feeds"]:
        try:
            raw, used = fetch_feed(f)
        except Exception as e:
            print(f"FAIL  {f['name']:<30} {type(e).__name__}: {str(e)[:80]}"); continue
        kept = []
        for it in raw:
            title, link = clean(it["title"], 200), it["link"]
            if not title or not link.startswith(("http://", "https://")): continue
            d = pdate(it["date"])
            if d is None or d < oldest or d > now + timedelta(days=1): continue
            summary = clean(it["summary"])
            source = f["name"]
            if f["cat"] == "leaders":
                source = clean(it.get("src") or "", 60) or source
                if " - " in title: title, src2 = title.rsplit(" - ", 1); source = it.get("src") or src2
                summary = ""  # Google News descriptions are just link lists
            if f.get("filter") and not re.search(KEYWORDS.get(f["cat"], "."), title + " " + summary, re.I): continue
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen: continue
            seen.add(key)
            kept.append({"cat": f["cat"], "title": title, "link": link, "source": source, "date": d.astimezone(timezone.utc).isoformat(timespec="minutes"),
                         "summary": summary, "image": it.get("image", "") if "ytimg.com" in it.get("image", "") else ""})
        kept.sort(key=lambda x: x["date"], reverse=True)
        kept = kept[: f.get("max", 3)]
        print(f"OK    {f['name']:<30} {len(raw):>3} found, {len(kept)} kept   {used[:90]}")
        items += kept
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:MAX_ITEMS]
    print(f"TOTAL {len(items)} items  (uni {sum(i['cat']=='uni' for i in items)}, talks {sum(i['cat']=='talks' for i in items)}, leaders {sum(i['cat']=='leaders' for i in items)})")
    return {"updated": now.isoformat(timespec="minutes"), "items": items}

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    if sys.argv[1] == "--check":
        run(check=True); sys.exit(0)
    out = sys.argv[1]; data = run()
    if not data["items"]: sys.exit("no items - keeping the previous file")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(data, fh, ensure_ascii=False)
    os.chmod(tmp, 0o644); os.replace(tmp, out)
    print("written", out)
