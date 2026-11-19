#!/usr/bin/env python3
"""블로그 초안을 텔레그램으로 보낸다 — 휴대폰에서 그대로 복사·저장해 발행하기 좋게 나눠서 보낸다.

순서: ① 안내(플랫폼·카테고리·키트 링크) ② 제목 ③ 본문(길면 여러 개) ④ 태그 ⑤ 출처 ⑥ 사진 묶음
휴대폰에서: 메시지를 길게 눌러 복사 → 블로그 앱에 붙여넣기 / 사진은 눌러서 저장 → 본문의 [표1]·[그래프1] 자리에 첨부.
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없으면 조용히 건너뛴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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


def sections(text: str) -> dict:
    parts, key = {}, None
    for line in text.splitlines():
        m = re.fullmatch(r"\[(제목|태그|카테고리|본문|출처)\]\s*", line.strip())
        if m:
            key = m.group(1)
            parts[key] = []
        elif key:
            parts[key].append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--platform", default="네이버")
    ap.add_argument("--category", default="")
    ap.add_argument("--slot", default="")
    ap.add_argument("--kit-dir", default="")
    ap.add_argument("--kit-url", default="")
    args = ap.parse_args()

    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[notify] 텔레그램 설정 없음 → 건너뜀")
        return 0
    api = f"https://api.telegram.org/bot{token}"

    def send(text: str):
        if not text.strip():
            return
        requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"},
                      timeout=20).raise_for_status()

    s = sections(Path(args.file).read_text(encoding="utf-8"))
    head = f"📝 [{args.platform}] {args.slot} · 카테고리: {args.category or s.get('카테고리', '')}"
    if args.kit_url:
        head += f"\n🖼 PC용 복붙 페이지(그림·표 포함): {args.kit_url}"
    head += "\n\n아래 메시지를 차례로 길게 눌러 복사하세요. 사진은 맨 끝에 있어요."
    send(head)
    send(s.get("제목", ""))
    for part in chunks(s.get("본문", "")):
        send(part)
    send(s.get("태그", ""))
    if s.get("출처"):
        send("출처\n" + s["출처"])

    kit = Path(args.kit_dir) if args.kit_dir else None
    if kit and kit.is_dir():
        imgs = sorted(kit.glob("*.png"), key=lambda p: (not p.name.startswith("cover"), p.name))[:10]
        if imgs:
            media, files = [], {}
            for i, p in enumerate(imgs):
                key = f"f{i}"
                cap = "대표 이미지" if p.name.startswith("cover") else \
                    p.stem.replace("chart-", "그래프").replace("table-", "표")
                media.append({"type": "photo", "media": f"attach://{key}", "caption": cap})
                files[key] = (p.name, p.read_bytes(), "image/png")
            requests.post(f"{api}/sendMediaGroup",
                          data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)},
                          files=files, timeout=60).raise_for_status()
    print(f"[notify] 텔레그램 전송 완료: {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
