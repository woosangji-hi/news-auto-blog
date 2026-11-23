#!/usr/bin/env python3
"""회차별 파이프라인: 수집 → Claude Code 초안 작성 → 검증 → 복붙 키트 → 알림 → (선택) git push

회차는 config/settings.yaml 의 slots 에 정의되어 있다. 실행 시각(한국 시간)으로 회차를 고르거나 --slot 으로 지정한다.

  python scripts/pipeline.py                      # 지금 시각에 맞는 회차 실행
  python scripts/pipeline.py --slot brief         # 08시 오늘의 브리핑 회차를 지금 실행
  python scripts/pipeline.py --slot noon --dry-run   # 수집만
  python scripts/pipeline.py --git-push           # 개인 서버에서: 결과를 커밋·푸시
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KST, ROOT, load_yaml, settings  # noqa: E402

try:  # 로컬 실행 시 .env 자동 로드 (없어도 됨)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PY = sys.executable
PLATFORM_KO = {"naver": "네이버", "tistory": "티스토리"}
SLOT_TITLE = {"brief": "08시 오늘의 브리핑", "noon": "12시 시사", "afternoon": "15시 경제", "evening": "18시 일상"}

TOPIC_RULES = {
    "us_brief": "- 간밤 미국 증시 마감을 다룬다. 시세 파일 숫자를 중심으로, 기사에서 움직임의 이유를 찾는다.",
    "시사": "- 오늘 올라온 정책·제도·사회 이슈 중 생활 영향이 큰 것 1~2개를 고른다 (사건사고·정치 공방 제외).",
    "경제": "- 금리·물가·환율·부동산·기업·고용 중 오늘 가장 중요한 경제 이슈 1~2개를 고른다.",
    "일상": "- 기사 중 생활 밀착 정보(지원금·혜택 신청, 절약, 장바구니 물가, 세금·공과금 일정 등)를 골라 생활 정보형으로 쓴다.\n"
            "- 블로그 주인의 경험을 지어내지 않는다. 생활 정보 기사가 없으면 경제·사회 기사 중 생활 영향이 큰 것을 생활 관점으로 풀어 쓴다.",
}


def run(cmd: list, **kw) -> int:
    print("$", " ".join(str(c) for c in cmd[:4]), "..." if len(cmd) > 4 else "", flush=True)
    return subprocess.run(cmd, cwd=ROOT, **kw).returncode


def pick_slot(slots: dict, hour: int) -> str | None:
    for name, s in slots.items():
        lo, hi = s["hours"]
        if lo <= hour < hi:
            return name
    return None


def recent_titles(n: int = 8) -> str:
    files = sorted((ROOT / "drafts").glob("*.txt"), reverse=True)[:n]
    lines = []
    for p in files:
        txt = p.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(txt):
            if line.strip() == "[제목]" and i + 1 < len(txt):
                lines.append(f"- {p.stem}: {txt[i + 1].strip()}")
                break
    return "\n".join(lines) or "- (아직 없음)"


def base_url() -> str:
    cfg = load_yaml(ROOT / "site" / "_config.yml")
    return (cfg.get("url") or "").rstrip("/") + (cfg.get("baseurl") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="auto")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--git-push", action="store_true")
    ap.add_argument("--skip-notify", action="store_true")
    ap.add_argument("--sources", help="출처 파일 강제 지정 (테스트용)")
    ap.add_argument("--outbox", help="알림을 바로 보내지 않고 이 파일에 남김 (GitHub Actions: 배포 후 정해진 시각에 send.py 로 전송)")
    args = ap.parse_args()

    cfg = settings()
    slots = cfg["slots"]
    now = dt.datetime.now(KST)
    slot_name = pick_slot(slots, now.hour) if args.slot == "auto" else args.slot
    if slot_name not in slots:
        print(f"이 시각({now:%H:%M})에 해당하는 회차가 없습니다. --slot 으로 지정하세요: {', '.join(slots)}")
        return 0
    slot = slots[slot_name]
    kind = slot["kind"]
    stamp = now.strftime("%Y-%m-%d-%H%M")
    print(f"== {SLOT_TITLE.get(slot_name, slot_name)} 회차 ({stamp})")
    if now.weekday() in slot.get("skip_weekdays", []) and args.slot == "auto":
        print(f"{'월화수목금토일'[now.weekday()]}요일은 이 회차를 쉽니다 (settings.yaml skip_weekdays).")
        return 0
    weekly = kind == "us_brief" and now.weekday() == 0  # 월요일: 이번 주 주요 일정 추가

    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    batch = raw_dir / f"{stamp}.json"

    # 1) 수집
    sources = args.sources or str(ROOT / slot["sources"])
    rc = run([PY, "scripts/collect.py", "fetch", "--out", batch, "--sources", sources])
    if rc == 3:
        print("새 기사가 부족해 종료합니다 (정상).")
        return 0
    if rc != 0:
        return rc
    market = None
    if kind == "us_brief":
        market = raw_dir / f"{stamp}-market.json"
        run([PY, "scripts/market.py", "--out", market])
    calendar = None
    if weekly:
        calendar = raw_dir / f"{stamp}-calendar.json"
        run([PY, "scripts/calendar_week.py", "--out", calendar])
        # 이번 주 일정 기사(지난 3일치)를 기사 목록에 합쳐서, 한국 일정도 출처 링크와 함께 확인할 수 있게 한다
        week_batch = raw_dir / f"{stamp}-week.json"
        run([PY, "scripts/collect.py", "fetch", "--out", week_batch, "--window-hours", "72",
             "--sources", str(ROOT / "config" / "sources_week.yaml")])
        if week_batch.exists():
            main_b = json.loads(batch.read_text(encoding="utf-8"))
            have = {i["id"] for i in main_b["items"]}
            extra = [i for i in json.loads(week_batch.read_text(encoding="utf-8"))["items"] if i["id"] not in have]
            main_b["items"] += extra
            main_b["count"] = len(main_b["items"])
            batch.write_text(json.dumps(main_b, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"이번 주 일정 기사 {len(extra)}건 추가")
    if args.dry_run:
        print(f"[dry-run] 수집 결과: {batch}")
        return 0

    # 2) 초안 목록
    drafts = []  # (rel_path, platform, category)
    for o in slot["outputs"]:
        rel = f"drafts/{stamp}-{o['platform']}.txt"
        drafts.append((rel, o["platform"], o["category"]))
    post_rel = f"site/_posts/{now:%Y-%m-%d}-{now:%H%M}-{slot_name}-brief.md" if cfg.get("site_post") else None

    limits = cfg.get("drafts", {}).get(kind, {})
    draft_list = "\n".join(
        f"- `{rel}` — **{PLATFORM_KO[p]}판**, 카테고리 `{c}` (시각자료: `{rel[:-4]}.visuals.json`)"
        for rel, p, c in drafts)
    if post_rel:
        draft_list += f"\n- `{post_rel}` — 자체 사이트 글 (CLAUDE.md 사이트 글 형식, date: {now:%Y-%m-%d %H:%M:00 +0900})"
    topic_rule = TOPIC_RULES["us_brief"] if kind == "us_brief" else TOPIC_RULES.get(drafts[0][2], "")
    market_line = (f"- 시세 파일: `{market.relative_to(ROOT).as_posix()}` (ok=false 면 시세 없이 기사 숫자만 사용. "
                   "출처 표기: Yahoo Finance)") if market else ""
    if calendar:
        market_line += (
            f"\n- **월요일 특별 구성** — 이번 주 경제 일정 파일: `{calendar.relative_to(ROOT).as_posix()}` (한국 시간, ★★★/★★ 중요도)\n"
            "  - 두 초안 모두 평소 브리핑(금요일 미국장 마감)은 6~8줄로 줄이고, `▶ 이번 주 주요 일정` 소제목을 추가한다.\n"
            "  - `[표2]` = 이번 주 주요 일정표. 열: 날짜(요일) | 시간(한국) | 국가 | 발표 | 중요도. 시간순 정렬, 최대 15행.\n"
            "    미국 지표 이름은 한국어로 (예: Core PCE Price Index m/m → 근원 PCE 물가지수(전월비), Prelim GDP q/q → GDP 속보치(전분기비)).\n"
            "  - 한국 일정(금통위, 수출입동향, 소비자물가, 주요 기업 실적·행사 등)은 기사 목록의 '이번주 주요 일정' 기사를 WebFetch로 열어\n"
            "    **기사에서 확인된 것만** 넣는다. 날짜·시간이 기사에 없으면 시간은 '미정'. 중요도는 금통위·물가·수출입 ★★★, 그 밖 ★★.\n"
            "  - 표 note: `출처: Forex Factory 경제 캘린더, <확인한 언론사>`. 본문에 ★★★ 일정 2~3개를 한 줄씩 왜 중요한지 설명.\n"
            "  - 일정 파일 ok=false 면 기사에서 확인된 일정만으로 표를 만들고, 그것도 없으면 일정 표는 뺀다.")

    prompt = (ROOT / "prompts" / "draft.md").read_text(encoding="utf-8")
    for k, v in {
        "NOW": now.strftime("%Y년 %m월 %d일 %H:%M"),
        "SLOT_TITLE": SLOT_TITLE.get(slot_name, slot_name),
        "BATCH_PATH": batch.relative_to(ROOT).as_posix(),
        "MARKET_LINE": market_line,
        "RECENT_TITLES": recent_titles(),
        "TOPIC_RULE": topic_rule,
        "DRAFT_LIST": draft_list,
        "MIN_CHARS": limits.get("min_chars", 800),
        "MAX_CHARS": limits.get("max_chars", 4000),
        "MIN_SOURCES": limits.get("min_sources", 2),
    }.items():
        prompt = prompt.replace("{{" + k + "}}", str(v))
    prompt_file = raw_dir / f"{stamp}-prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    claude = shutil.which("claude")
    if not claude:
        print("claude 명령을 찾을 수 없습니다. `npm install -g @anthropic-ai/claude-code` 로 설치하세요.")
        return 1
    cc = cfg["claude"]
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    total_cost = 0.0

    def call_claude(instruction_file: Path, tag: str) -> int:
        nonlocal total_cost
        cmd = [claude, "-p",
               f"{instruction_file.relative_to(ROOT).as_posix()} 파일을 읽고 그 지시를 그대로 수행하세요.",
               "--allowedTools", cc["allowed_tools"], "--max-turns", str(cc["max_turns"]),
               "--output-format", "json"]
        model = os.getenv("CLAUDE_MODEL") or cc.get("model")
        if model:
            cmd += ["--model", model]
        log_path = log_dir / f"claude-{stamp}-{tag}.json"
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                rc = run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=cc["timeout_minutes"] * 60)
        except subprocess.TimeoutExpired:
            print(f"Claude 실행 시간 초과 ({cc['timeout_minutes']}분)")
            return 1
        try:
            res = json.loads(log_path.read_text(encoding="utf-8"))
            cost = float(res.get("total_cost_usd") or 0)
            total_cost += cost
            print(f"Claude[{tag}] 완료: turns={res.get('num_turns')} cost=${cost:.3f}")
        except Exception:
            print(f"Claude[{tag}] 로그: {log_path}")
        if rc != 0:
            print(f"Claude 실행 실패 (exit {rc}) — 로그 확인: {log_path}")
        return rc

    report_json = raw_dir / f"{stamp}-validate.json"

    def validate() -> tuple[int, str, list]:
        cmd = [PY, "scripts/validate.py", "--batch", batch, "--report-json", report_json]
        if post_rel:
            cmd += ["--post", post_rel]
        for rel, _p, c in drafts:
            cmd += ["--draft", f"{rel}|{c}|{kind}"]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        print(r.stdout, r.stderr, sep="")
        failed = json.loads(report_json.read_text(encoding="utf-8")).get("failed", []) if report_json.exists() else []
        return r.returncode, r.stdout, failed

    if call_claude(prompt_file, "write") != 0:
        return 1

    # 3) 검증 — 실패하면 오류 목록을 주고 고치게 한 뒤 재검증
    rc, report, failed = validate()
    for i in range(int(cc.get("fix_retries", 1))):
        if rc == 0:
            break
        fix_file = raw_dir / f"{stamp}-fix{i + 1}.md"
        targets = ", ".join(f"`{f}`" for f in failed)
        fix_file.write_text(
            "# 검증 실패 수정 지시\n\n"
            f"CLAUDE.md 규칙과 `{prompt_file.relative_to(ROOT).as_posix()}` 지시를 따라 {targets} "
            "(와 같은 이름의 .visuals.json)를 고친다.\n"
            f"자료: `{batch.relative_to(ROOT).as_posix()}`\n"
            "아래 오류(✗)를 모두 해결하고, 고친 부분 외의 내용은 유지한다. 다른 파일은 건드리지 않는다.\n\n"
            f"```\n{report.strip()}\n```\n", encoding="utf-8")
        if call_claude(fix_file, f"fix{i + 1}") != 0:
            break
        rc, report, failed = validate()

    # 실패한 초안만 격리하고, 통과한 초안은 계속 진행
    rej = ROOT / "rejected" / stamp
    for f in failed:
        for p in (ROOT / f, (ROOT / f).with_suffix(".visuals.json")):
            if p.exists():
                rej.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), rej / p.name)
    passed = [d for d in drafts if d[0] not in failed]
    if failed:
        shutil.copy(batch, rej / "batch.json")
        print(f"검증 실패 {len(failed)}건 → {rej.relative_to(ROOT)} 에 보관")
    if not passed and not (post_rel and post_rel not in failed):
        print(f"통과한 초안이 없어 발행 중단. 이번 회차 비용 ${total_cost:.3f}")
        return 1

    # 4) 사용한 기사 기록 (다음 회차 중복 방지)
    run([PY, "scripts/collect.py", "mark", "--batch", batch])

    # 5) 복붙 키트 + 6) 알림 (--outbox 를 주면 바로 보내지 않고 목록만 남김 → send.py 가 정해진 시각에 전송)
    messages = []
    for rel, platform, category in passed:
        stem = Path(rel).stem
        kit_url = ""
        if run([PY, "scripts/render_kit.py", "--naver", rel]) == 0:
            kit_url = f"{base_url()}/kit/{stem}/"
        else:
            print(f"발행 키트 생성 실패 — {rel} 은 텍스트만 전송합니다")
        messages.append(["--file", rel, "--platform", PLATFORM_KO[platform], "--category", category,
                         "--slot", SLOT_TITLE.get(slot_name, slot_name),
                         "--kit-dir", f"site/kit/{stem}", "--kit-url", kit_url])
    send_at = slot.get("send_at")  # "08:10"
    send_at_iso = (now.replace(hour=int(send_at[:2]), minute=int(send_at[3:]), second=0, microsecond=0).isoformat()
                   if send_at else now.isoformat())
    if args.outbox:
        Path(args.outbox).write_text(json.dumps({"send_at": send_at_iso, "messages": messages}, ensure_ascii=False),
                                     encoding="utf-8")
        print(f"알림 {len(messages)}건 대기 → {send_at_iso} 에 전송 ({args.outbox})")
    elif not args.skip_notify:
        for m in messages:
            run([PY, "scripts/notify.py", *m])

    # 7) (개인 서버용) 커밋·푸시
    if args.git_push:
        run(["git", "add", "site/_posts", "site/kit", "drafts", "data/seen.json"])
        if run(["git", "diff", "--cached", "--quiet"]) != 0:
            run(["git", "commit", "-m", f"{slot_name}: {stamp}"])
            if run(["git", "push"]) != 0:
                return 1

    print(f"완료: {', '.join(d[0] for d in passed)} · 이번 회차 비용 ${total_cost:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
