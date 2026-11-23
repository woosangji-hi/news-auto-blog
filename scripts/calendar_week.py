#!/usr/bin/env python3
"""이번 주 주요 경제 지표 발표 일정 (월요일 오늘의 브리핑용).

  python scripts/calendar_week.py --out data/raw/<stamp>-calendar.json

- 미국(및 주요국) 지표: Forex Factory 주간 캘린더(JSON). 시간은 한국 시간으로 바꾼다.
  중요도 High → ★★★, Medium → ★★ (Low 는 뺀다).
- 한국 일정은 여기서 받지 않는다. 월요일 회차에서 "이번주 주요 금융일정" 기사(sources_week.yaml)를 함께 수집해
  Claude가 기사로 확인한 것만 넣는다.
실패해도 종료 코드는 0, {"ok": false} 를 남긴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KST  # noqa: E402

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) news-auto-blog/1.0"
STARS = {"High": "★★★", "Medium": "★★"}
COUNTRY_KO = {"USD": "미국", "CNY": "중국", "JPY": "일본", "EUR": "유로존"}
WEEKDAY_KO = "월화수목금토일"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {"ok": False, "source": "Forex Factory 경제 캘린더 (forexfactory.com)",
           "timezone": "한국 시간(KST)", "events": []}
    try:
        for attempt in range(4):  # 요청 제한(429)이 걸리면 잠시 쉬었다 재시도
            r = requests.get(URL, headers={"User-Agent": UA}, timeout=20)
            if r.status_code != 429:
                break
            print("[WARN] 경제 캘린더 요청 제한 → 45초 후 재시도", file=sys.stderr)
            time.sleep(45)
        r.raise_for_status()
        for e in r.json():
            country, impact = e.get("country"), e.get("impact")
            # 미국은 High·Medium, 중국·일본·유로존은 High 만
            if not (country == "USD" and impact in STARS) and not (country in COUNTRY_KO and impact == "High"):
                continue
            when = dt.datetime.fromisoformat(e["date"]).astimezone(KST)
            all_day = "T00:00:00" in e["date"]  # 미국 시간 자정 = 시간 미정/종일 일정
            out["events"].append({
                "date": when.date().isoformat(),
                "weekday": WEEKDAY_KO[when.weekday()],
                "time_kst": "미정/종일" if all_day else when.strftime("%H:%M"),
                "country": COUNTRY_KO[country],
                "title_en": e.get("title", ""),
                "importance": STARS[impact],
                "forecast": e.get("forecast") or None,
                "previous": e.get("previous") or None,
            })
        out["events"].sort(key=lambda x: (x["date"], x["time_kst"]))
        out["ok"] = True
        print(f"[OK] 이번 주 일정 {len(out['events'])}건", file=sys.stderr)
    except Exception as ex:
        print(f"[WARN] 경제 캘린더 실패: {ex}", file=sys.stderr)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
