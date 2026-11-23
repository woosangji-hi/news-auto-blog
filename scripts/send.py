#!/usr/bin/env python3
"""pipeline.py --outbox 로 남긴 알림을 정해진 시각(send_at)까지 기다렸다가 텔레그램으로 보낸다.

GitHub 예약 실행은 수십 분씩 늦게 시작하는 일이 잦아서, 회차를 일찍 시작해 글·그림·배포를 끝내 두고
알림만 정해진 시각(예: 08:10)에 보낸다. 이미 그 시각이 지났으면 바로 보낸다.

  python scripts/send.py --outbox outbox.json [--max-wait-min 110]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KST, ROOT  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outbox", required=True)
    ap.add_argument("--max-wait-min", type=int, default=110)
    args = ap.parse_args()

    box = Path(args.outbox)
    if not box.exists():
        print("[send] 보낼 알림 없음")
        return 0
    data = json.loads(box.read_text(encoding="utf-8"))
    target = dt.datetime.fromisoformat(data["send_at"])
    wait = (target - dt.datetime.now(KST)).total_seconds()
    if wait > 0:
        wait = min(wait, args.max_wait_min * 60)
        print(f"[send] {target:%H:%M} 까지 {wait / 60:.0f}분 대기", flush=True)
        time.sleep(wait)
    else:
        print(f"[send] 목표 시각 {target:%H:%M} 보다 {-wait / 60:.0f}분 늦음 → 바로 전송", flush=True)

    rc = 0
    for m in data["messages"]:
        rc |= subprocess.run([sys.executable, "scripts/notify.py", *m], cwd=ROOT).returncode
    print(f"[send] {dt.datetime.now(KST):%H:%M:%S} 전송 끝 ({len(data['messages'])}건)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
