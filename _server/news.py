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
MAX_ITEMS, MAX_AGE_DAYS = 80, 45
KEYWORDS = {
 "uni": r"student|undergrad|graduate|admission|scholarship|career|job|employ|alumni|commencement|education|learning|teaching|campus|internship|young|youth|future of work|skills|AI\b|artificial intelligence|degree|course|summer|visa|international|ranking|QS\b|study abroad|tuition|fees|enrol|applicant",
"people": (r"Jamie Dimon|Dimon\b|Jensen Huang|Nvidia CEO|Elon Musk|Musk\b|Donald Trump|Trump\b|Sam Altman|Satya Nadella|Tim Cook|Warren Buffett|Mark Zuckerberg",
            r"\bsays\b|\bsaid\b|interview|advice|tells|told|Gen Z|young|youth|career|graduates?|students?|college|universit|success|lesson|future|predict|warns|thinks|believes|view|vision|habit|work ethic|hiring|jobs?\b|AI\b|skills?"),
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
            img = ""
            for tag in ("media:content", "media:thumbnail", ".//media:content", ".//media:thumbnail"):
                x = i.find(tag, NS)
                if x is not None and x.get("url") and (x.get("medium", "image") == "image" or re.search(r"\.(jpe?g|png|webp)", x.get("url"), re.I)):
                    img = x.get("url"); break
            enc = i.find("enclosure")
            if not img and enc is not None and (enc.get("type") or "").startswith("image"): img = enc.get("url", "")
            body = txt(i, "description") + txt(i, "content:encoded")
            if not img:
                m = re.search(r"<img[^>]+src=[\"']([^\"']+)", html.unescape(body), re.I)
                if m: img = m.group(1)
            out.append({"title": txt(i, "title"), "link": txt(i, "link").strip(), "date": txt(i, "pubDate") or txt(i, "{http://purl.org/dc/elements/1.1/}date"),
                        "summary": txt(i, "description"), "image": img, "src": (src.text if src is not None else ""),
                        "site": (src.get("url", "") if src is not None else "")})
    return out

def fetch_feed(f):
    data, final = get(f["url"])
    head = data[:600].lstrip().lower()
    if head.startswith(b"<!doctype html") or b"<html" in head:
        feed = discover(data, final)
        if not feed: raise ValueError("no RSS feed found on page")
        data, final = get(feed)
    return parse(data), final

SKIP_IMG = re.compile(r"\.svg|^data:|logo|icon|sprite|avatar|pixel|spacer|blank|placeholder|badge|button|\.gif", re.I)

def first_img(page, base):
    """The first real photo inside the article (not logos, icons or tracking pixels)."""
    m = re.search(r"<article\b.*?</article>", page, re.S | re.I) or re.search(r"<main\b.*?</main>", page, re.S | re.I)
    for t in re.finditer(r"<img\b[^>]*>", m.group(0) if m else page, re.I):
        tag = t.group(0)
        src = re.search(r'\bdata-src=["\']([^"\']+)', tag, re.I) or re.search(r'\bsrc=["\']([^"\']+)', tag, re.I)
        if not src: continue
        u = urllib.parse.urljoin(base, html.unescape(src.group(1)).strip())
        if not u.startswith("https://") or SKIP_IMG.search(u): continue
        if any(int(x) < 200 for x in re.findall(r'\b(?:width|height)=["\']?(\d+)', tag)): continue
        return u
    return ""

def og_image(url, first=True):
    """Cover image of a page: its og:image / twitter:image, else (if first) the first photo in the article."""
    if "news.google.com" in url or not url.startswith("https://"): return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=10) as r:
            page = r.read(600_000).decode("utf-8", "ignore"); base = r.geturl()
    except Exception:
        return ""
    for pat in (r'<meta[^>]+(?:property|name)=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, page, re.I)
        if m:
            u = urllib.parse.urljoin(base, html.unescape(m.group(1)).strip())
            if u.startswith("https://"): return u
    return first_img(page, base) if first else ""

IMG_DIR = "/opt/fvg-news/img"
TR_CACHE = "/opt/fvg-news/translations.json"

def translate(text, lang, cache):
    """Machine-translate English text to zh-TW / zh-CN (free Google endpoint). Falls back to ''."""
    if not text: return ""
    key = lang + "|" + text
    if key in cache: return cache[key]
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&dt=t&tl=" + lang + "&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    except Exception:
        return ""
    if out: cache[key] = out
    return out

def cache_image(url):
    """Save a cover image on our own server so it always loads; return its local path."""
    import hashlib
    if not url.startswith("https://"): return ""
    name = hashlib.sha1(url.encode()).hexdigest()[:20]
    try:
        os.makedirs(IMG_DIR, exist_ok=True)
        for ext in (".jpg", ".png", ".webp", ".gif"):
            if os.path.exists(os.path.join(IMG_DIR, name + ext)): return "/news-img/" + name + ext
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = (r.headers.get("Content-Type") or "").lower(); data = r.read(4_000_001)
        if not ctype.startswith("image/") or len(data) > 4_000_000 or len(data) < 1000: return ""
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ctype.split(";")[0], ".jpg")
        path = os.path.join(IMG_DIR, name + ext)
        with open(path + ".tmp", "wb") as fh: fh.write(data)
        os.chmod(path + ".tmp", 0o644); os.replace(path + ".tmp", path)
        return "/news-img/" + name + ext
    except Exception:
        return ""

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
            site = ""
            if "news.google.com" in f["url"]:
                source = clean(it.get("src") or "", 60) or source
                if " - " in title: title, src2 = title.rsplit(" - ", 1); source = it.get("src") or src2
                summary = ""  # Google News descriptions are just link lists
                site = (it.get("site") or "").replace("http://", "https://", 1)
            pats = KEYWORDS.get(f.get("kw", f["cat"]), ".")
            if f.get("filter") and not all(re.search(p, title + " " + summary, re.I) for p in ((pats,) if isinstance(pats, str) else pats)): continue
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen: continue
            seen.add(key)
            kept.append({"cat": f["cat"], "title": title, "link": link, "source": source, "date": d.astimezone(timezone.utc).isoformat(timespec="minutes"),
                         "summary": summary, "image": it.get("image", "") if (it.get("image") or "").startswith("https://") else "", "site": site})
        kept.sort(key=lambda x: x["date"], reverse=True)
        kept = kept[: f.get("max", 3)]
        print(f"OK    {f['name']:<30} {len(raw):>3} found, {len(kept)} kept   {used[:90]}")
        items += kept
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:MAX_ITEMS]
    site_img = {}
    for it in items:
        site = it.pop("site", "")
        if not it["image"]: it["image"] = og_image(it["link"])          # the article's own image
        if not it["image"] and site.startswith("https://"):              # Google News: the publisher's site image
            if site not in site_img: site_img[site] = og_image(site, first=False)
            it["image"] = site_img[site]
            if it["image"]: it["img_from"] = "site"
        if it["image"]: it["credit"] = it["source"]
        if it["image"] and not check:
            local = cache_image(it["image"])
            if local: it["image"] = local
    if not check:
        try: cache = json.load(open(TR_CACHE, encoding="utf-8"))
        except Exception: cache = {}
        done = 0
        for it in items:
            for suf, lang in (("_zh", "zh-TW"), ("_cn", "zh-CN")):
                it["title" + suf] = translate(it["title"], lang, cache)
                it["summary" + suf] = translate(it["summary"], lang, cache)
            done += bool(it["title_zh"])
        keep = {k: v for k, v in cache.items() if any(k.endswith("|" + it["title"]) or k.endswith("|" + it["summary"]) for it in items)}
        try:
            os.makedirs(os.path.dirname(TR_CACHE), exist_ok=True)
            json.dump(keep, open(TR_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception: pass
        print(f"CHINESE {done}/{len(items)} items translated")
    print(f"IMAGES {sum(1 for i in items if i['image'])}/{len(items)} have a cover image")
    print(f"TOTAL {len(items)} items  (uni {sum(i['cat']=='uni' for i in items)}, news {sum(i['cat']=='news' for i in items)}, leaders {sum(i['cat']=='leaders' for i in items)})")
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
