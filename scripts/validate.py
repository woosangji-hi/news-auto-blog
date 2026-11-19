#!/usr/bin/env python3
"""Claude가 쓴 글을 발행 전에 기계적으로 검사한다.

검사 항목
  - 프런트매터 필수 항목·길이
  - 본문 분량, 필수 소제목
  - 출처 링크가 실제 수집한 기사에서 왔는지 (지어낸 링크 차단)
  - 기사 제목·요약 문장을 그대로 베꼈는지 (저작권)
  - 투자 권유성 금지 표현
  - 네이버 초안이 사이트 글과 너무 비슷한지 (유사문서 방지)

종료 코드 0 = 통과, 1 = 실패
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from common import norm_url, settings, squash

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


class Report:
    def __init__(self, name: str):
        self.name, self.errors, self.warnings = name, [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def print(self):
        status = "통과" if not self.errors else "실패"
        print(f"\n[{self.name}] {status}")
        for e in self.errors:
            print(f"  ✗ {e}")
        for w in self.warnings:
            print(f"  ! {w}")


def char_count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def split_sources(body: str, heading: str):
    idx = body.find(heading)
    return (body, "") if idx < 0 else (body[:idx], body[idx:])


def longest_overlap(a: str, b: str) -> int:
    if not a or not b:
        return 0
    m = SequenceMatcher(None, a, b, autojunk=False)
    return m.find_longest_match(0, len(a), 0, len(b)).size


def shingles(text: str, n: int = 8) -> set:
    s = squash(text)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def jaccard(a: str, b: str) -> float:
    A, B = shingles(a), shingles(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def check_links(rep: Report, text: str, sources_part: str, batch_urls: set, extra: list, min_sources: int):
    def allowed(u: str) -> bool:
        host = urlsplit(u).netloc.lower()
        return norm_url(u) in batch_urls or any(host.endswith(d) for d in extra)

    for u in URL_RE.findall(text):
        if not allowed(u):
            rep.err(f"수집 목록에 없는 링크: {u}")
    n = len({norm_url(u) for u in URL_RE.findall(sources_part)})
    if n < min_sources:
        rep.err(f"출처 링크 {n}개 < 최소 {min_sources}개")


def check_copy(rep: Report, body: str, items: list, limit: int):
    b = squash(body)
    for it in items:
        for field in ("title", "summary"):
            size = longest_overlap(b, squash(it.get(field, "")))
            if size >= limit:
                rep.err(f"기사 {field} 문장과 {size}자 연속 일치 → 다시 써야 함 ({it['source']}: {it['title'][:30]})")
                break


def check_banned(rep: Report, text: str, phrases: list):
    for p in phrases:
        if p in text:
            rep.err(f"금지 표현 포함: '{p}'")


def validate_post(path: Path, batch: dict, cfg: dict) -> tuple[Report, str]:
    rep = Report(f"사이트 글 {path.name}")
    pc = cfg["post"]
    if not path.exists():
        rep.err("파일이 없음")
        return rep, ""
    raw = path.read_text(encoding="utf-8")
    m = FM_RE.match(raw)
    if not m:
        rep.err("프런트매터(--- ... ---)가 없음")
        return rep, raw
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as ex:
        rep.err(f"프런트매터 YAML 오류: {ex}")
        return rep, m.group(2)
    body = m.group(2)

    for key in ("layout", "title", "date", "description", "categories"):
        if not fm.get(key):
            rep.err(f"프런트매터 '{key}' 누락")
    t_min, t_max = pc["title_len"]
    if fm.get("title") and not t_min <= len(str(fm["title"])) <= t_max:
        rep.err(f"제목 길이 {len(str(fm['title']))}자 (허용 {t_min}~{t_max})")
    d_min, d_max = pc["description_len"]
    if fm.get("description") and not d_min <= len(str(fm["description"])) <= d_max:
        rep.warn(f"description 길이 {len(str(fm['description']))}자 (권장 {d_min}~{d_max})")
    if fm.get("date") and not str(fm["date"]).startswith(path.name[:10]):
        rep.err(f"date({fm['date']})가 파일명 날짜({path.name[:10]})와 다름")

    for h in pc["required_headings"]:
        if h not in body:
            rep.err(f"필수 소제목 누락: {h}")

    main_part, sources_part = split_sources(body, "## 출처")
    n = char_count(main_part)
    if not pc["min_chars"] <= n <= pc["max_chars"]:
        rep.err(f"본문 {n}자 (허용 {pc['min_chars']}~{pc['max_chars']})")

    urls = {norm_url(i["link"]) for i in batch["items"]}
    check_links(rep, body, sources_part, urls, cfg.get("allowed_extra_domains", []), pc["min_sources"])
    check_copy(rep, main_part, batch["items"], cfg["max_copy_chars"])
    check_banned(rep, raw, cfg.get("banned_phrases", []))
    return rep, main_part


def validate_naver(path: Path, batch: dict, cfg: dict, post_main: str) -> Report:
    rep = Report(f"네이버 초안 {path.name}")
    nc = cfg["naver"]
    if not path.exists():
        rep.err("파일이 없음")
        return rep
    raw = path.read_text(encoding="utf-8")
    for tag in ("[제목]", "[태그]", "[본문]", "[출처]"):
        if tag not in raw:
            rep.err(f"구역 표시 누락: {tag}")
    cats = nc.get("categories") or []
    if cats:
        m = re.search(r"\[카테고리\]\s*\n\s*(.+)", raw)
        if not m:
            rep.err("구역 표시 누락: [카테고리]")
        elif m.group(1).strip() not in cats:
            rep.err(f"카테고리 '{m.group(1).strip()}' 는 허용 목록 {cats} 에 없음")
    body = raw.split("[본문]", 1)[-1].split("[출처]", 1)[0]
    body = re.sub(r"^\[(?:대표이미지|표\d+|그래프\d+)\]\s*$", "", body, flags=re.M)
    sources_part = raw.split("[출처]", 1)[-1] if "[출처]" in raw else ""

    n = char_count(body)
    if not nc["min_chars"] <= n <= nc["max_chars"]:
        rep.err(f"본문 {n}자 (허용 {nc['min_chars']}~{nc['max_chars']})")
    if post_main:
        sim = jaccard(body, post_main)
        if sim > nc["max_similarity_to_post"]:
            rep.err(f"사이트 글과 유사도 {sim:.2f} > {nc['max_similarity_to_post']} (네이버 유사문서 위험)")
        else:
            rep.warn(f"사이트 글과 유사도 {sim:.2f}")

    urls = {norm_url(i["link"]) for i in batch["items"]}
    check_links(rep, raw, sources_part, urls, cfg.get("allowed_extra_domains", []), 2)
    check_copy(rep, body, batch["items"], cfg["max_copy_chars"])
    check_banned(rep, raw, cfg.get("banned_phrases", []))
    return rep


PLACEHOLDER_RE = re.compile(r"^\[((?:표|그래프)\d+)\]\s*$", re.M)


def validate_visuals(path: Path, naver_raw: str) -> Report:
    rep = Report(f"시각자료 {path.name}")
    if not path.exists():
        rep.warn("시각자료 파일 없음 → 대표 이미지만 만들어짐")
        return rep
    try:
        vis = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        rep.err(f"JSON 형식 오류: {ex}")
        return rep
    ids = set()
    for c in vis.get("charts", []):
        cid = c.get("id", "?")
        ids.add(cid)
        labels, series = c.get("labels") or [], c.get("series") or []
        if c.get("type", "bar") not in ("bar", "line", "hbar"):
            rep.err(f"{cid}: type 은 bar/line/hbar 중 하나")
        if len(labels) < 2 or not series:
            rep.err(f"{cid}: labels 2개 이상, series 1개 이상 필요")
        for s in series:
            vals = s.get("values") or []
            if len(vals) != len(labels):
                rep.err(f"{cid}: values 개수({len(vals)})가 labels 개수({len(labels)})와 다름")
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                rep.err(f"{cid}: values 는 숫자만")
        if not str(c.get("note", "")).startswith("출처"):
            rep.err(f"{cid}: note 는 '출처:' 로 시작해야 함")
    for tb in vis.get("tables", []):
        tid = tb.get("id", "?")
        ids.add(tid)
        width = len(tb.get("headers") or [])
        if not width or not tb.get("rows"):
            rep.err(f"{tid}: headers 와 rows 가 필요")
        for r in tb.get("rows") or []:
            if len(r) != width:
                rep.err(f"{tid}: 행의 칸 수({len(r)})가 headers({width})와 다름")
        if not str(tb.get("note", "")).startswith("출처"):
            rep.err(f"{tid}: note 는 '출처:' 로 시작해야 함")
    for ph in PLACEHOLDER_RE.findall(naver_raw):
        if ph not in ids:
            rep.err(f"본문 자리표시 [{ph}] 에 해당하는 시각자료가 없음")
    for i in ids - set(PLACEHOLDER_RE.findall(naver_raw)):
        rep.warn(f"{i} 가 본문에 자리표시 없이 맨 끝에 붙음")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", required=True)
    ap.add_argument("--naver", required=True)
    ap.add_argument("--batch", required=True)
    args = ap.parse_args()

    cfg = settings()["validate"]
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    post_rep, post_main = validate_post(Path(args.post), batch, cfg)
    naver_rep = validate_naver(Path(args.naver), batch, cfg, post_main)
    naver_path = Path(args.naver)
    vis_rep = validate_visuals(naver_path.with_suffix(".visuals.json"),
                               naver_path.read_text(encoding="utf-8") if naver_path.exists() else "")
    post_rep.print()
    naver_rep.print()
    vis_rep.print()
    return 1 if (post_rep.errors or naver_rep.errors or vis_rep.errors) else 0


if __name__ == "__main__":
    sys.exit(main())
