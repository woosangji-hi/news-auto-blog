#!/usr/bin/env python3
"""RSS 수집기.

사용법:
  python scripts/collect.py fetch --out data/raw/batch.json   # 새 기사 수집
  python scripts/collect.py mark  --batch data/raw/batch.json # 발행 성공 후 '본 기사'로 기록

종료 코드: 0 = 정상, 3 = 새 기사가 부족해 이번 회차 건너뜀
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
import sys
from pathlib import Path

import feedparser
import requests

from common import KST, ROOT, clean_text, load_yaml, norm_url, settings, url_key

SEEN_PATH = ROOT / "data" / "seen.json"
UA = "Mozilla/5.0 (compatible; news-auto-blog/1.0; +https://github.com/)"
EXIT_NOT_ENOUGH = 3


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8") or "{}")
    return {}


def save_seen(seen: dict) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def read_feed(url: str, timeout: int):
    local = url[7:] if url.startswith("file://") else url
    if not url.startswith("http") and Path(local).exists():
        return feedparser.parse(Path(local).read_bytes())
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return feedparser.parse(r.content)


def entry_time(e) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return dt.datetime.fromtimestamp(calendar.timegm(t), tz=dt.timezone.utc).astimezone(KST)
    return None


def title_key(title: str) -> str:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|<[^>]*>", "", title)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t)[:40]


def cmd_fetch(args) -> int:
    cfg = settings()["collect"]
    sources = load_yaml(Path(args.sources))["sources"]
    seen = load_seen()
    now = dt.datetime.now(KST)
    since = now - dt.timedelta(hours=args.window_hours or cfg["window_hours"])
    excludes = cfg.get("exclude_keywords", [])

    items, titles = [], set()
    for src in sources:
        if not src.get("enabled", True):
            continue
        try:
            feed = read_feed(src["url"], cfg["request_timeout"])
        except Exception as ex:  # 한 출처 실패가 전체를 멈추지 않도록
            log(f"[WARN] {src['name']} 수집 실패: {ex}")
            continue
        if feed.bozo and not feed.entries:
            log(f"[WARN] {src['name']} 파싱 실패: {feed.bozo_exception}")
            continue

        count = 0
        for e in feed.entries:
            link = e.get("link", "")
            title = clean_text(e.get("title", ""))
            if not link or not title:
                continue
            if any(k in title for k in excludes):
                continue
            published = entry_time(e)
            if published and published < since:
                continue
            key = url_key(link)
            tkey = title_key(title)
            if key in seen or tkey in titles:
                continue
            titles.add(tkey)
            summary = clean_text(e.get("summary", "") or e.get("description", ""))
            items.append({
                "id": key,
                "source": src["name"],
                "category": src.get("category", "economy"),
                "title": title,
                "link": link,
                "published": published.isoformat() if published else None,
                "summary": summary[:300],
            })
            count += 1
            if count >= cfg["max_per_source"]:
                break
        log(f"[OK] {src['name']}: {count}건")

    items.sort(key=lambda x: x["published"] or "", reverse=True)
    items = items[: cfg["max_items"]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "window_hours": args.window_hours or cfg["window_hours"],
        "count": len(items),
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"총 {len(items)}건 → {out}")

    if len(items) < cfg["min_items"]:
        log(f"새 기사 {len(items)}건 < 최소 {cfg['min_items']}건 → 이번 회차 건너뜀")
        return EXIT_NOT_ENOUGH
    return 0


def cmd_mark(args) -> int:
    cfg = settings()["collect"]
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    seen = load_seen()
    today = dt.date.today().isoformat()
    for it in batch["items"]:
        seen[it["id"]] = today
    cutoff = (dt.date.today() - dt.timedelta(days=cfg["seen_keep_days"])).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    save_seen(seen)
    log(f"seen 기록 {len(seen)}건 (보관 {cfg['seen_keep_days']}일)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--out", required=True)
    f.add_argument("--sources", default=str(ROOT / "config" / "sources.yaml"))
    f.add_argument("--window-hours", type=int, help="settings.yaml 의 window_hours 대신 사용")
    m = sub.add_parser("mark")
    m.add_argument("--batch", required=True)
    args = ap.parse_args()
    return cmd_fetch(args) if args.cmd == "fetch" else cmd_mark(args)


if __name__ == "__main__":
    sys.exit(main())
