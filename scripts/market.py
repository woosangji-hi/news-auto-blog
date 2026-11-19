#!/usr/bin/env python3
"""간밤 미국 증시·환율·금리 숫자를 받아 JSON으로 저장한다 (08:00 오늘의 브리핑용).

  python scripts/market.py --out data/raw/<stamp>-market.json

Yahoo Finance 차트 데이터(비공식)를 쓴다. 실패해도 종료 코드는 0이고 {"ok": false} 를 남긴다
→ 이 경우 브리핑은 기사에 나온 숫자만으로 쓴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KST  # noqa: E402

SYMBOLS = [
    ("^GSPC", "S&P500", ""),
    ("^IXIC", "나스닥", ""),
    ("^DJI", "다우", ""),
    ("^SOX", "필라델피아 반도체", ""),
    ("^TNX", "미 국채 10년물 금리", "%"),
    ("KRW=X", "원·달러 환율", "원"),
    ("CL=F", "WTI 유가", "달러"),
]
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=7d&interval=1d"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) news-auto-blog/1.0"


def fetch(sym: str) -> dict:
    r = requests.get(URL.format(sym=requests.utils.quote(sym)), headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    tz = dt.timezone(dt.timedelta(seconds=res["meta"].get("gmtoffset", 0)))
    closes = res["indicators"]["quote"][0]["close"]
    days = [(dt.datetime.fromtimestamp(ts, tz).date().isoformat(), c)
            for ts, c in zip(res["timestamp"], closes) if c is not None]
    if len(days) < 2:
        raise ValueError("데이터 부족")
    (d_prev, prev), (d_last, last) = days[-2], days[-1]
    return {"date": d_last, "close": round(last, 2), "prev_date": d_prev, "prev_close": round(prev, 2),
            "change": round(last - prev, 2), "change_pct": round((last - prev) / prev * 100, 2),
            "history": [{"date": d, "close": round(c, 2)} for d, c in days[-5:]]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {"ok": False, "fetched_at": dt.datetime.now(KST).isoformat(),
           "source": "Yahoo Finance (finance.yahoo.com)", "items": []}
    for sym, name, unit in SYMBOLS:
        try:
            out["items"].append({"symbol": sym, "name": name, "unit": unit, **fetch(sym)})
            print(f"[OK] {name}", file=sys.stderr)
        except Exception as ex:  # 하나 실패해도 나머지는 계속
            print(f"[WARN] {name} 시세 실패: {ex}", file=sys.stderr)
    out["ok"] = len(out["items"]) >= 3
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"시세 {len(out['items'])}건 → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
