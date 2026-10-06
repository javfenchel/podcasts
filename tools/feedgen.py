#!/usr/bin/env python3
"""
feedgen.py -- dependency-free RSS + HTML writer shared by the laptop builder (podcast_kit.py)
and the hourly GitHub Actions job (tools/release.py).

Inputs, all inside the site repo:
  feeds.json             [{slug, title, description, author, category, url}, ...]   written by the builder
  <slug>/episodes.json   {episode_id: {file, title, description, guid, pubDate, duration, bytes, release?, ...}}

An episode whose `release` (ISO datetime with offset) is still in the future is left out of
feed.xml and listed under "Scheduled" on the feed's index page. Everything else is released.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
from pathlib import Path

CSS = ("body{font:16px/1.5 Georgia,serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#1b1b1b}"
       "code{background:#f2f2f2;padding:2px 6px;border-radius:4px}li{margin:.5rem 0}small{color:#666}"
       "h2{margin-top:2rem}")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def is_released(ep: dict, now: dt.datetime) -> bool:
    r = ep.get("release")
    return not r or parse_iso(r) <= now


def rfc2822(iso: str) -> str:
    return email.utils.format_datetime(parse_iso(iso))


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def local_str(iso: str) -> str:
    return parse_iso(iso).astimezone().strftime("%a %b %d, %Y %I:%M %p").replace(" 0", " ")


def _sorted(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda e: e["pubDate"], reverse=True)


def write_feed(feed: dict, meta: dict, site_dir: Path, now: dt.datetime) -> list[dict]:
    """Write <slug>/feed.xml. Returns the released items, newest first."""
    out_dir = site_dir / feed["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    items = _sorted([e for e in meta.values() if is_released(e, now)])
    cover = f"{feed['url']}/cover.png" if (out_dir / "cover.png").exists() else ""
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
         'xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
         "<channel>",
         f"<title>{html.escape(feed['title'])}</title>",
         f"<link>{feed['url']}/</link>",
         f"<description>{html.escape(feed['description'])}</description>",
         "<language>en-us</language>",
         f"<lastBuildDate>{email.utils.format_datetime(now)}</lastBuildDate>",
         f'<atom:link href="{feed["url"]}/feed.xml" rel="self" type="application/rss+xml"/>',
         f"<itunes:author>{html.escape(feed['author'])}</itunes:author>",
         f"<itunes:summary>{html.escape(feed['description'])}</itunes:summary>",
         "<itunes:explicit>false</itunes:explicit>",
         f'<itunes:category text="{feed["category"]}"/>',
         "<itunes:type>episodic</itunes:type>"]
    if cover:
        x.append(f'<itunes:image href="{cover}"/>')
        x.append(f"<image><url>{cover}</url><title>{html.escape(feed['title'])}</title><link>{feed['url']}/</link></image>")
    for e in items:
        url = f"{feed['url']}/episodes/{e['file']}"
        x.append("<item>")
        x.append(f"<title>{html.escape(e['title'])}</title>")
        x.append(f"<description>{html.escape(e['description'])}</description>")
        if e.get("link"):
            x.append(f"<link>{html.escape(e['link'])}</link>")
        x.append(f'<enclosure url="{url}" length="{e["bytes"]}" type="audio/mpeg"/>')
        x.append(f'<guid isPermaLink="false">{html.escape(e["guid"])}</guid>')
        x.append(f"<pubDate>{rfc2822(e['pubDate'])}</pubDate>")
        x.append(f"<itunes:duration>{hms(e['duration'])}</itunes:duration>")
        x.append("<itunes:episodeType>full</itunes:episodeType>")
        x.append("</item>")
    x.append("</channel></rss>")
    (out_dir / "feed.xml").write_text("\n".join(x) + "\n", encoding="utf-8")
    return items


def write_index(feed: dict, meta: dict, site_dir: Path, now: dt.datetime) -> None:
    out_dir = site_dir / feed["slug"]
    released = _sorted([e for e in meta.values() if is_released(e, now)])
    scheduled = sorted([e for e in meta.values() if not is_released(e, now)], key=lambda e: e["release"])
    rows = "\n".join(
        f'<li><a href="episodes/{e["file"]}">{html.escape(e["title"])}</a> '
        f'<small>{hms(e["duration"])}, {e["bytes"] / 1e6:.1f} MB, {e["pubDate"][:10]}</small></li>'
        for e in released)
    sched = ""
    if scheduled:
        sched = "<h2>Scheduled</h2><ul>" + "\n".join(
            f'<li>{html.escape(e["title"])} <small>releases {html.escape(local_str(e["release"]))}</small></li>'
            for e in scheduled) + "</ul>"
    (out_dir / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(feed['title'])}</title><style>{CSS}</style></head>
<body><p><a href="../">All feeds</a></p><h1>{html.escape(feed['title'])}</h1>
<p>{html.escape(feed['description'])}</p>
<p>Subscribe in a podcast app that accepts a feed URL (Pocket Casts, AntennaPod, Apple Podcasts, Overcast):<br>
<code>{feed['url']}/feed.xml</code></p>
<ul>{rows}</ul>
{sched}
</body></html>
""", encoding="utf-8")


def write_root_index(feeds: list[dict], metas: dict[str, dict], site_dir: Path, now: dt.datetime) -> None:
    cards = []
    for f in feeds:
        meta = metas.get(f["slug"], {})
        n = sum(1 for e in meta.values() if is_released(e, now))
        s = len(meta) - n
        extra = f", {s} scheduled" if s else ""
        cards.append(f'<h2><a href="{f["slug"]}/">{html.escape(f["title"])}</a> '
                     f'<small>{n} episode{"s" if n != 1 else ""}{extra}</small></h2>'
                     f"<p>{html.escape(f['description'])}</p><p><code>{f['url']}/feed.xml</code></p>")
    (site_dir / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Podcast feeds</title><style>{CSS}</style></head>
<body><h1>Podcast feeds</h1>
<p>Private-use feeds. Add a feed URL to Pocket Casts or AntennaPod.</p>
{"".join(cards)}
</body></html>
""", encoding="utf-8")
    (site_dir / ".nojekyll").touch()


def _guids_in(feed_xml: Path) -> set[str]:
    if not feed_xml.exists():
        return set()
    return set(re.findall(r"<guid[^>]*>([^<]+)</guid>", feed_xml.read_text(encoding="utf-8")))


def regenerate(site_dir: Path, now: dt.datetime | None = None) -> dict[str, list[str]]:
    """Rewrite every feed from feeds.json + <slug>/episodes.json. Returns {slug: [titles newly released]}."""
    now = now or now_utc()
    feeds = json.loads((site_dir / "feeds.json").read_text(encoding="utf-8"))
    metas: dict[str, dict] = {}
    newly: dict[str, list[str]] = {}
    for f in feeds:
        p = site_dir / f["slug"] / "episodes.json"
        meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        metas[f["slug"]] = meta
        before = _guids_in(site_dir / f["slug"] / "feed.xml")
        items = write_feed(f, meta, site_dir, now)
        write_index(f, meta, site_dir, now)
        newly[f["slug"]] = [e["title"] for e in items if html.escape(e["guid"]) not in before and e["guid"] not in before]
    write_root_index(feeds, metas, site_dir, now)
    return newly
