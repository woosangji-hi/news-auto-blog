#!/usr/bin/env python3
"""전체 파이프라인: 수집 → Claude Code 작성 → 검증 → 기록 → 알림 → (선택) git push

GitHub Actions와 개인 서버(cron/작업 스케줄러) 모두 이 파일 하나만 실행하면 된다.

  python scripts/pipeline.py              # 한 회차 실행
  python scripts/pipeline.py --dry-run    # 수집만 하고 Claude는 호출하지 않음
  python scripts/pipeline.py --git-push   # 개인 서버에서: 결과를 커밋·푸시 (→ Pages 자동 배포)
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
SLOTS = [(10, "morning", "아침"), (15, "noon", "점심"), (24, "evening", "저녁")]


def run(cmd: list, **kw) -> int:
    print("$", " ".join(str(c) for c in cmd[:4]), "..." if len(cmd) > 4 else "", flush=True)
    return subprocess.run(cmd, cwd=ROOT, **kw).returncode


def slot_for(hour: int):
    for limit, en, ko in SLOTS:
        if hour < limit:
            return en, ko
    return SLOTS[-1][1:]


def recent_titles(n: int = 6) -> str:
    posts = sorted((ROOT / "site" / "_posts").glob("*.md"), reverse=True)[:n]
    lines = []
    for p in posts:
        for line in p.read_text(encoding="utf-8").splitlines()[:8]:
            if line.startswith("title:"):
                lines.append(f"- {p.name[:16]}: {line[6:].strip()}")
                break
    return "\n".join(lines) or "- (아직 없음)"


def render_prompt(values: dict) -> str:
    text = (ROOT / "prompts" / "brief.md").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def site_url_for(post_rel: str) -> str:
    cfg = load_yaml(ROOT / "site" / "_config.yml")
    base = (cfg.get("url") or "").rstrip("/") + (cfg.get("baseurl") or "")
    name = Path(post_rel).stem  # 2026-11-19-0707-morning-brief
    y, m, d, slug = name[:4], name[5:7], name[8:10], name[11:]
    return f"{base}/{y}/{m}/{d}/{slug}/"


def kit_url_for(stamp: str) -> str:
    cfg = load_yaml(ROOT / "site" / "_config.yml")
    base = (cfg.get("url") or "").rstrip("/") + (cfg.get("baseurl") or "")
    return f"{base}/kit/{stamp}/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--git-push", action="store_true")
    ap.add_argument("--skip-notify", action="store_true")
    ap.add_argument("--sources", default=str(ROOT / "config" / "sources.yaml"))
    args = ap.parse_args()

    cfg = settings()
    now = dt.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d-%H%M")
    slot_en, slot_ko = slot_for(now.hour)

    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    batch = raw_dir / f"{stamp}.json"

    # 1) 수집
    rc = run([PY, "scripts/collect.py", "fetch", "--out", batch, "--sources", args.sources])
    if rc == 3:
        print("새 기사가 부족해 종료합니다 (정상).")
        return 0
    if rc != 0:
        return rc
    if args.dry_run:
        print(f"[dry-run] 수집 결과: {batch}")
        return 0

    # 2) Claude Code 실행 (긴 프롬프트는 파일로 넘겨 Windows 명령줄 길이 제한을 피함)
    post_rel = f"site/_posts/{now:%Y-%m-%d}-{now:%H%M}-{slot_en}-brief.md"
    naver_rel = f"naver/{stamp}.txt"
    visuals_rel = f"naver/{stamp}.visuals.json"
    prompt_file = raw_dir / f"{stamp}-prompt.md"
    prompt_file.write_text(render_prompt({
        "NOW": now.strftime("%Y년 %m월 %d일 %H:%M"),
        "SLOT_KO": slot_ko,
        "BATCH_PATH": batch.relative_to(ROOT).as_posix(),
        "POST_PATH": post_rel,
        "NAVER_PATH": naver_rel,
        "VISUALS_PATH": visuals_rel,
        "DATE_FM": now.strftime("%Y-%m-%d %H:%M:00 +0900"),
        "RECENT_POSTS": recent_titles(),
    }), encoding="utf-8")

    claude = shutil.which("claude")
    if not claude:
        print("claude 명령을 찾을 수 없습니다. `npm install -g @anthropic-ai/claude-code` 로 설치하세요.")
        return 1
    cc = cfg["claude"]
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    def call_claude(instruction_file: Path, tag: str) -> int:
        cmd = [
            claude, "-p",
            f"{instruction_file.relative_to(ROOT).as_posix()} 파일을 읽고 그 지시를 그대로 수행하세요.",
            "--allowedTools", cc["allowed_tools"],
            "--max-turns", str(cc["max_turns"]),
            "--output-format", "json",
        ]
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
            print(f"Claude[{tag}] 완료: turns={res.get('num_turns')} cost=${res.get('total_cost_usd') or 0:.3f}")
        except Exception:
            print(f"Claude[{tag}] 로그: {log_path}")
        if rc != 0:
            print(f"Claude 실행 실패 (exit {rc}) — 로그 확인: {log_path}")
        return rc

    def validate() -> tuple[int, str]:
        r = subprocess.run([PY, "scripts/validate.py", "--post", post_rel, "--naver", naver_rel, "--batch", batch],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        print(r.stdout, r.stderr, sep="")
        return r.returncode, r.stdout

    rc = call_claude(prompt_file, "write")
    if rc != 0:
        return rc

    # 3) 검증 — 실패하면 오류 목록을 주고 고치게 한 뒤 재검증 (fix_retries 회)
    rc, report = validate()
    for i in range(int(cc.get("fix_retries", 1))):
        if rc == 0:
            break
        fix_file = raw_dir / f"{stamp}-fix{i + 1}.md"
        fix_file.write_text(
            "# 검증 실패 수정 지시\n\n"
            f"CLAUDE.md 규칙을 따라 `{post_rel}`, `{naver_rel}`, `{visuals_rel}` 를 고친다. 자료: `{batch.relative_to(ROOT).as_posix()}`\n"
            "아래 오류(✗)를 모두 해결하고, 고친 부분 외의 내용은 유지한다. 다른 파일은 건드리지 않는다.\n\n"
            f"```\n{report.strip()}\n```\n", encoding="utf-8")
        if call_claude(fix_file, f"fix{i + 1}") != 0:
            break
        rc, report = validate()

    if rc != 0:
        rej = ROOT / "rejected" / stamp
        rej.mkdir(parents=True, exist_ok=True)
        for rel in (post_rel, naver_rel, visuals_rel):
            p = ROOT / rel
            if p.exists():
                shutil.move(str(p), rej / p.name)
        shutil.copy(batch, rej / "batch.json")
        print(f"검증 실패 → 발행 중단. 결과물은 {rej.relative_to(ROOT)} 에 보관")
        return 1

    # 4) 사용한 기사 기록 (다음 회차 중복 방지)
    run([PY, "scripts/collect.py", "mark", "--batch", batch])

    # 5) 복붙용 발행 키트 (그림·표·그래프 포함). 실패해도 사이트 발행은 계속한다
    kit_url = ""
    if run([PY, "scripts/render_kit.py", "--naver", naver_rel]) == 0:
        kit_url = kit_url_for(stamp)
    else:
        print("발행 키트 생성 실패 — 텍스트 초안만 전송합니다")

    # 6) 네이버 초안 알림
    if not args.skip_notify:
        run([PY, "scripts/notify.py", "--file", naver_rel,
             "--header", f"📝 {now:%m/%d} {slot_ko} 브리핑 네이버 초안"
                         + (f"\n🖼 복붙 키트(그림·표 포함): {kit_url}" if kit_url else ""),
             "--site-url", site_url_for(post_rel)])

    # 7) (개인 서버용) 커밋·푸시
    if args.git_push:
        run(["git", "add", "site/_posts", "site/kit", "naver", "data/seen.json"])
        if run(["git", "diff", "--cached", "--quiet"]) != 0:
            run(["git", "commit", "-m", f"brief: {stamp}"])
            if run(["git", "push"]) != 0:
                return 1

    print(f"완료: {post_rel}, {naver_rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
