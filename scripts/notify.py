#!/usr/bin/env python3
"""네이버 블로그 초안을 텔레그램으로 보낸다.

휴대폰 텔레그램에서 메시지를 길게 눌러 복사 → 네이버 블로그 앱에 붙여넣기.
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없으면 조용히 건너뛴다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LIMIT = 3900  # 텔레그램 메시지 한도 4096자보다 여유 있게


def chunks(text: str, size: int = LIMIT):
    buf = ""
    for para in text.split("\n"):
        if len(buf) + len(para) + 1 > size and buf:
            yield buf
            buf = ""
        buf += para + "\n"
    if buf.strip():
        yield buf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--header", default="📝 네이버 블로그 초안")
    ap.add_argument("--site-url", default="")
    args = ap.parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[notify] 텔레그램 설정 없음 → 건너뜀")
        return 0

    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    api = f"https://api.telegram.org/bot{token}"

    header = args.header + (f"\n사이트: {args.site_url}" if args.site_url else "")
    requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": header}, timeout=20).raise_for_status()
    for part in chunks(text):
        requests.post(
            f"{api}/sendMessage",
            data={"chat_id": chat, "text": part, "disable_web_page_preview": "true"},
            timeout=20,
        ).raise_for_status()
    with open(path, "rb") as f:
        requests.post(
            f"{api}/sendDocument",
            data={"chat_id": chat},
            files={"document": (path.name, f, "text/plain")},
            timeout=30,
        ).raise_for_status()
    print("[notify] 텔레그램 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
