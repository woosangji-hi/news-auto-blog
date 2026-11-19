#!/usr/bin/env python3
"""네이버·티스토리 등에 '복사 → 붙여넣기'로 올릴 수 있는 발행 키트를 만든다.

입력
  naver/<stamp>.txt           : 본문 초안 ([제목]/[태그]/[본문]/[출처])
  naver/<stamp>.visuals.json  : 대표이미지 문구, 표, 그래프 데이터 (없으면 대표이미지만 생성)

출력 (site/kit/<stamp>/ → GitHub Pages로 배포되어 휴대폰·다른 PC에서도 열림)
  index.html     : 제목/태그/본문 복사 버튼, 이미지 개별 복사·저장 버튼
  cover.png      : 대표 이미지 (1080x1080, 직접 만든 이미지라 저작권 걱정 없음)
  chart-N.png    : 그래프
  table-N.png    : 표 이미지 (표 붙여넣기가 깨지는 에디터용 예비)

  python scripts/render_kit.py --naver naver/2026-11-19-0707.txt
  python scripts/render_kit.py --naver examples/sample-naver.txt --out site/kit/sample   # 예시
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_yaml  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# ── 색·글꼴 ────────────────────────────────────────────────
NAVY, INK, MUTED, LINE, PAPER = "#13294B", "#1F2937", "#6B7280", "#E5E7EB", "#FFFFFF"
ACCENT = "#E8A33D"
SERIES = ["#1F4E8C", "#E8A33D", "#2F9E7A", "#C2410C", "#7C3AED"]

FONT_CANDIDATES = {
    "regular": [str(ROOT / "fonts" / "NanumGothic-Regular.ttf"), "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "C:/Windows/Fonts/malgun.ttf",
                "/System/Library/Fonts/AppleSDGothicNeo.ttc"],
    "bold": [str(ROOT / "fonts" / "NanumGothic-Bold.ttf"), "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "C:/Windows/Fonts/malgunbd.ttf",
             "/System/Library/Fonts/AppleSDGothicNeo.ttc"],
}


def font_path(kind: str) -> str:
    for p in FONT_CANDIDATES[kind]:
        if Path(p).exists():
            return p
    raise SystemExit("한글 글꼴을 찾지 못했습니다. (리눅스: sudo apt-get install -y fonts-nanum)")


def setup_matplotlib():
    reg = font_path("regular")
    font_manager.fontManager.addfont(reg)
    font_manager.fontManager.addfont(font_path("bold"))
    name = font_manager.FontProperties(fname=reg).get_name()
    plt.rcParams.update({"font.family": name, "axes.unicode_minus": False})


# ── 초안 파싱 ──────────────────────────────────────────────
def parse_draft(text: str) -> dict:
    parts, key = {}, None
    for line in text.splitlines():
        m = re.fullmatch(r"\[(제목|태그|카테고리|본문|출처)\]\s*", line.strip())
        if m:
            key = m.group(1)
            parts[key] = []
            continue
        if key:
            parts[key].append(line)
    get = lambda k: "\n".join(parts.get(k, [])).strip()  # noqa: E731
    return {"title": get("제목"), "tags": get("태그"), "category": get("카테고리"),
            "body": get("본문"), "sources": get("출처")}


# ── 이미지 생성 ────────────────────────────────────────────
def wrap_ko(text: str, font, max_w: int, draw) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            # 단어 중간에서 자르지 않도록 마지막 공백에서 끊기
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.5:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def make_cover(out: Path, headline: str, sub: str, label: str, brand: str):
    W = H = 1080
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    bold, reg = font_path("bold"), font_path("regular")
    f_label, f_head = ImageFont.truetype(bold, 40), ImageFont.truetype(bold, 84)
    f_sub, f_brand = ImageFont.truetype(reg, 42), ImageFont.truetype(bold, 34)

    # 상단 라벨 칩
    pad = 22
    lw = d.textlength(label, font=f_label)
    d.rounded_rectangle((90, 110, 90 + lw + pad * 2, 110 + 72), radius=36, fill=ACCENT)
    d.text((90 + pad, 122), label, font=f_label, fill=NAVY)

    y = 260
    for line in wrap_ko(headline, f_head, W - 180, d)[:4]:
        d.text((90, y), line, font=f_head, fill=PAPER)
        y += 112
    y += 30
    d.rectangle((90, y, 210, y + 8), fill=ACCENT)
    y += 50
    for line in wrap_ko(sub, f_sub, W - 180, d)[:3]:
        d.text((90, y), line, font=f_sub, fill="#C9D3E3")
        y += 60
    d.text((90, H - 120), brand, font=f_brand, fill="#C9D3E3")
    img.save(out, optimize=True)


def make_chart(out: Path, spec: dict):
    labels = [str(x) for x in spec["labels"]]
    series = spec["series"]
    kind = spec.get("type", "bar")
    unit = spec.get("unit", "")
    fig, ax = plt.subplots(figsize=(10.8, 6.75), dpi=100)
    fig.patch.set_facecolor(PAPER)

    def fmt(v):
        return f"{v:,.2f}".rstrip("0").rstrip(".") + unit

    if kind == "line":
        for i, s in enumerate(series):
            c = SERIES[i % len(SERIES)]
            ax.plot(labels, s["values"], marker="o", lw=3, color=c, label=s.get("name", ""))
            ax.annotate(fmt(s["values"][-1]), (labels[-1], s["values"][-1]), textcoords="offset points",
                        xytext=(0, 12), ha="center", fontsize=14, color=c, fontweight="bold")
    elif kind == "hbar":
        vals = series[0]["values"]
        bars = ax.barh(labels[::-1], vals[::-1], color=SERIES[0], height=0.6)
        for b, v in zip(bars, vals[::-1]):
            ax.text(b.get_width(), b.get_y() + b.get_height() / 2, " " + fmt(v), va="center", fontsize=14)
    else:  # bar (여러 계열이면 묶음 막대)
        n = len(series)
        w = 0.8 / n
        for i, s in enumerate(series):
            xs = [j + (i - (n - 1) / 2) * w for j in range(len(labels))]
            bars = ax.bar(xs, s["values"], width=w * 0.9, color=SERIES[i % len(SERIES)], label=s.get("name", ""))
            for b, v in zip(bars, s["values"]):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt(v), ha="center", va="bottom", fontsize=13)
        ax.set_xticks(range(len(labels)), labels)

    ax.set_title(spec["title"], fontsize=22, fontweight="bold", color=INK, loc="left", pad=18)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(labelsize=13, colors=INK)
    ax.grid(axis="x" if kind == "hbar" else "y", color=LINE, lw=1)
    ax.set_axisbelow(True)
    if len(series) > 1 or (kind == "line" and series[0].get("name")):
        ax.legend(frameon=False, fontsize=13)
    note = spec.get("note", "")
    if note:
        fig.text(0.01, 0.01, note, fontsize=11, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out)
    plt.close(fig)


def make_table_png(out: Path, spec: dict):
    headers, rows = spec["headers"], spec["rows"]
    h = 1.2 + 0.55 * (len(rows) + 1)
    fig, ax = plt.subplots(figsize=(10.8, h), dpi=100)
    ax.axis("off")
    ax.set_title(spec["title"], fontsize=20, fontweight="bold", color=INK, loc="left")
    t = ax.table(cellText=[[str(c) for c in r] for r in rows], colLabels=headers, loc="center", cellLoc="center")
    t.auto_set_font_size(False)
    t.set_fontsize(14)
    t.scale(1, 2.0)
    for (r, _c), cell in t.get_celld().items():
        cell.set_edgecolor(LINE)
        if r == 0:
            cell.set_facecolor(NAVY)
            cell.set_text_props(color=PAPER, fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#F5F7FA")
    if spec.get("note"):
        fig.text(0.01, 0.02, spec["note"], fontsize=11, color=MUTED)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


# ── 붙여넣기용 HTML ────────────────────────────────────────
P_STYLE = "font-size:16px;line-height:1.8;margin:0 0 16px;"
H_STYLE = "font-size:19px;font-weight:bold;margin:28px 0 12px;"
TH = "border:1px solid #CBD5E1;background:#13294B;color:#fff;padding:8px 12px;font-weight:bold;"
TD = "border:1px solid #CBD5E1;padding:8px 12px;text-align:center;"


def html_table(spec: dict, ph: str = "") -> str:
    head = "".join(f'<th style="{TH}">{html.escape(str(h))}</th>' for h in spec["headers"])
    body = "".join("<tr>" + "".join(f'<td style="{TD}">{html.escape(str(c))}</td>' for c in r) + "</tr>"
                   for r in spec["rows"])
    note = f'<p style="font-size:13px;color:#6B7280;margin:6px 0 20px;">{html.escape(spec.get("note", ""))}</p>'
    return (f'<p style="{P_STYLE}"><b>{html.escape(spec["title"])}</b></p>'
            f'<table data-ph="{html.escape(ph)}" style="border-collapse:collapse;width:100%;margin:0 0 4px;"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table>{note}")


def img_tag(src: str, alt: str, ph: str = "") -> str:
    return (f'<p style="text-align:center;margin:0 0 20px;"><img src="{src}" alt="{html.escape(alt)}" '
            f'data-ph="{html.escape(ph or alt)}" style="max-width:100%;"></p>')


def body_html(body: str, assets: dict) -> tuple[str, set]:
    used, out = set(), []
    for para in re.split(r"\n\s*\n", body.strip()):
        line = para.strip()
        m = re.fullmatch(r"\[(대표이미지|표\d+|그래프\d+)\]", line)
        if m and m.group(1) in assets:
            used.add(m.group(1))
            out.append(assets[m.group(1)])
        elif line.startswith("▶"):
            out.append(f'<p style="{H_STYLE}">{html.escape(line)}</p>')
        elif line:
            out.append(f'<p style="{P_STYLE}">' + "<br>".join(html.escape(x) for x in line.splitlines()) + "</p>")
    return "\n".join(out), used


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>발행 키트 · __TITLE__</title>
<style>
:root{--bg:#F4F6F9;--card:#fff;--ink:#1F2937;--muted:#6B7280;--line:#E5E7EB;--navy:#13294B;--ok:#2F9E7A}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:20px 16px 80px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 18px;font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 14px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.k{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:.04em;margin:0 0 6px}
.v{font-size:16px;word-break:keep-all}
button,.btn{appearance:none;border:0;border-radius:8px;background:var(--navy);color:#fff;font:600 14px system-ui,sans-serif;padding:9px 14px;cursor:pointer;text-decoration:none;display:inline-block}
button.ghost,.btn.ghost{background:#fff;color:var(--navy);border:1px solid var(--navy)}
.done{background:var(--ok)!important;color:#fff!important}
.steps{margin:0;padding-left:20px;color:var(--muted);font-size:13px}
#post{background:#fff;border:1px dashed #94A3B8;border-radius:8px;padding:18px;margin-top:10px}
.imgs{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.imgs figure{margin:0;border:1px solid var(--line);border-radius:10px;padding:8px;background:#fff}
.imgs img{width:100%;display:block;border-radius:6px}.imgs figcaption{font-size:13px;margin:6px 0}
pre{white-space:pre-wrap;font:13px/1.6 ui-monospace,Consolas,monospace;margin:0}
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<p class="sub">__STAMP__ 발행 키트 · 이 페이지는 검색에 노출되지 않습니다.</p>

<div class="card"><ol class="steps">
<li>블로그 글쓰기 화면을 엽니다 (네이버 앱/PC, 티스토리 등).</li>
<li><b>제목 복사</b> → 제목 칸에 붙여넣기.</li>
<li><b>본문 전체 복사</b> → 본문에 붙여넣기. 그림·표가 같이 들어갑니다.</li>
<li>그림이 빠졌다면 아래 <b>이미지</b>에서 [복사] 후 그 자리에 붙여넣거나 [저장] 후 사진 첨부.</li>
<li>발행 설정에서 <b>카테고리</b>를 아래 표시된 메뉴로 고릅니다.</li>
<li>첫 문단에 내 생각 한두 줄을 더하고, <b>태그 복사</b> → 태그 칸에 붙여넣고 발행.</li>
</ol></div>

<div class="card"><p class="k">제목</p><div class="row"><span class="v" id="t">__TITLE__</span>
<button data-copy-text="t">제목 복사</button></div></div>

<div class="card"><p class="k">카테고리</p><span class="v"><b>__CATEGORY__</b></span></div>

<div class="card"><p class="k">태그</p><div class="row"><span class="v" id="tags">__TAGS__</span>
<button class="ghost" data-copy-text="tags">태그 복사</button></div></div>

<div class="card"><div class="row" style="justify-content:space-between"><p class="k" style="margin:0">본문 (그림·표 포함)</p>
<div class="row"><button id="copyPost">본문 전체 복사</button>
<button class="ghost" id="copyPlain">글자만 복사 (휴대폰)</button></div></div>
<p class="sub" style="margin:8px 0 0">휴대폰 블로그 앱에서는 그림이 같이 붙지 않을 수 있어요. 그때는 [글자만 복사] 후 아래 이미지를 저장해 [그래프1]·[표1] 자리에 첨부하세요.</p>
<div id="post">__BODY__</div></div>

<div class="card"><p class="k">이미지 (개별 복사·저장)</p><div class="imgs">__IMAGES__</div></div>

<div class="card"><p class="k">출처 (본문 맨 아래에 붙여넣기 권장)</p><pre id="src">__SOURCES__</pre>
<p style="margin:10px 0 0"><button class="ghost" data-copy-text="src">출처 복사</button></p></div>
</div>
<script>
function flash(b,msg){const o=b.textContent;b.textContent=msg;b.classList.add('done');setTimeout(()=>{b.textContent=o;b.classList.remove('done')},1600)}
function selectNode(el){const r=document.createRange();r.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(r)}
document.querySelectorAll('[data-copy-text]').forEach(b=>b.addEventListener('click',async()=>{
  const el=document.getElementById(b.dataset.copyText);
  try{await navigator.clipboard.writeText(el.innerText.trim());flash(b,'복사됨')}catch(e){selectNode(el);document.execCommand('copy');flash(b,'복사됨')}
}));
document.getElementById('copyPost').addEventListener('click',e=>{
  // 선택 후 복사: 브라우저가 서식·표·이미지 주소를 함께 클립보드에 넣는다
  selectNode(document.getElementById('post'));document.execCommand('copy');getSelection().removeAllRanges();flash(e.target,'복사됨 · 붙여넣기 하세요')
});
document.getElementById('copyPlain').addEventListener('click',async e=>{
  // 그림 자리는 [그래프1] 같은 표시로 남겨 휴대폰에서 사진을 넣을 위치를 알 수 있게 한다
  const clone=document.getElementById('post').cloneNode(true);
  clone.querySelectorAll('img').forEach(i=>i.replaceWith('['+(i.dataset.ph||i.alt)+']'));
  clone.querySelectorAll('table').forEach(t=>t.replaceWith('['+(t.dataset.ph||'표')+']'));
  const txt=[...clone.childNodes].map(n=>(n.textContent||'').trim()).filter(Boolean).join('\n\n');
  try{await navigator.clipboard.writeText(txt);flash(e.target,'복사됨')}catch(err){const ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();flash(e.target,'복사됨')}
});
document.querySelectorAll('[data-copy-img]').forEach(b=>b.addEventListener('click',async()=>{
  try{const blob=await (await fetch(b.dataset.copyImg)).blob();
    await navigator.clipboard.write([new ClipboardItem({[blob.type]:blob})]);flash(b,'복사됨')}
  catch(e){flash(b,'저장 버튼을 쓰세요')}
}));
</script></body></html>
"""


def build(naver_path: Path, out_dir: Path, visuals_path: Path | None = None) -> Path:
    setup_matplotlib()
    cfg = load_yaml(ROOT / "site" / "_config.yml")
    brand = cfg.get("title", "")
    draft = parse_draft(naver_path.read_text(encoding="utf-8"))
    visuals_path = visuals_path or naver_path.with_suffix(".visuals.json")
    vis = json.loads(visuals_path.read_text(encoding="utf-8")) if visuals_path.exists() else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = out_dir.name

    images = []  # (file, caption)
    assets = {}

    cover = vis.get("cover", {})
    make_cover(out_dir / "cover.png", cover.get("headline") or draft["title"], cover.get("sub", ""),
               cover.get("label") or draft.get("category") or "오늘의 경제", brand)
    images.append(("cover.png", "대표 이미지"))
    assets["대표이미지"] = img_tag("cover.png", "대표 이미지", "대표이미지")

    for i, spec in enumerate(vis.get("charts", []), 1):
        key = spec.get("id") or f"그래프{i}"
        fn = f"chart-{i}.png"
        make_chart(out_dir / fn, spec)
        images.append((fn, spec["title"]))
        assets[key] = img_tag(fn, spec["title"], key)

    for i, spec in enumerate(vis.get("tables", []), 1):
        key = spec.get("id") or f"표{i}"
        fn = f"table-{i}.png"
        make_table_png(out_dir / fn, spec)
        images.append((fn, spec["title"] + " (표 이미지)"))
        assets[key] = html_table(spec, key)

    body, used = body_html(draft["body"], assets)
    if "대표이미지" not in used:
        body = assets["대표이미지"] + "\n" + body
    for key, frag in assets.items():  # 본문에 자리표시가 없던 그래프·표는 맨 끝에 붙임
        if key not in used and key != "대표이미지":
            body += "\n" + frag

    imgs_html = "".join(
        f'<figure><img src="{fn}" alt="{html.escape(cap)}"><figcaption>{html.escape(cap)}</figcaption>'
        f'<div class="row"><button data-copy-img="{fn}">복사</button>'
        f'<a class="btn ghost" href="{fn}" download>저장</a></div></figure>'
        for fn, cap in images)

    page = (PAGE.replace("__TITLE__", html.escape(draft["title"]))
            .replace("__STAMP__", html.escape(stamp))
            .replace("__TAGS__", html.escape(draft["tags"]))
            .replace("__CATEGORY__", html.escape(draft["category"] or "오늘의 브리핑"))
            .replace("__SOURCES__", html.escape(draft["sources"]))
            .replace("__IMAGES__", imgs_html)
            .replace("__BODY__", body))
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    write_index(out_dir.parent)
    return out_dir / "index.html"


def write_index(kit_root: Path):
    """site/kit/index.html — 지금까지 만든 키트 목록 (최신순)"""
    items = []
    for d in sorted((p for p in kit_root.iterdir() if (p / "index.html").exists()), reverse=True):
        m = re.search(r"<title>발행 키트 · (.*?)</title>", (d / "index.html").read_text(encoding="utf-8"))
        items.append(f'<li><a href="{d.name}/">{d.name}</a> — {m.group(1) if m else ""}</li>')
    (kit_root / "index.html").write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">'
        '<title>발행 키트 목록</title><style>body{font:16px/1.8 system-ui,"Malgun Gothic",sans-serif;'
        'max-width:760px;margin:0 auto;padding:20px 16px;color:#1F2937}a{color:#13294B;font-weight:600}</style>'
        f'</head><body><h1>발행 키트 목록</h1><ul>{"".join(items[:200])}</ul></body></html>', encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naver", required=True, help="naver/<stamp>.txt")
    ap.add_argument("--visuals", help="기본값: 같은 이름의 .visuals.json")
    ap.add_argument("--out", help="기본값: site/kit/<stamp>")
    args = ap.parse_args()
    naver = Path(args.naver)
    out = Path(args.out) if args.out else ROOT / "site" / "kit" / naver.stem
    page = build(naver, out, Path(args.visuals) if args.visuals else None)
    print(f"[kit] 생성 완료: {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
