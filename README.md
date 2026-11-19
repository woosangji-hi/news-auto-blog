# news-auto-blog

> **현재 운영 방식 (2026-11)**: 하루 4회차(08 오늘의 브리핑 / 12 시사 / 15 경제 / 18 일상), 회차마다 네이버판·티스토리판 초안 1편씩.
> 회차 정의는 `config/settings.yaml` 의 `slots`, 작성 규칙은 `CLAUDE.md`, 지시 템플릿은 `prompts/draft.md`. 초안은 `drafts/` 에 쌓입니다.
> 아래 설명 중 사이트 자동 발행은 `site_post: true` 일 때만 해당합니다.

하루 여러 번 경제·사회 뉴스를 모아 **Claude Code가 브리핑 글을 쓰고**, 자동 검증을 통과한 글만
**자체 사이트(GitHub Pages)에 자동 발행**합니다. 같은 회차에 **네이버 블로그용 초안**(사이트 글과
다른 문장·구성)을 만들어 텔레그램으로 보내 줍니다. 초안 발행은 직접 합니다.

> 네이버는 2020년에 블로그 글쓰기 API를 종료했습니다. 브라우저 자동화로 발행하면 계정 제재 위험이 커서,
> 네이버 쪽은 "초안 자동 생성 + 사람이 검토 후 발행" 구조로 설계했습니다.

---

## 구조

```
.github/workflows/
  news-brief.yml     # 하루 3회 실행 → 글 작성 → 커밋 → Pages 배포
  pages.yml          # 사이트를 직접 고쳐 push 했을 때 배포
CLAUDE.md            # Claude가 매번 따르는 편집 규칙 (문체·구성·금지사항) ← 가장 많이 고칠 파일
prompts/brief.md     # 회차별 작업 지시 템플릿
config/
  sources.yaml       # RSS 출처 목록
  settings.yaml      # 수집·검증 기준 (분량, 복제 허용치, 금지 표현 등)
scripts/
  pipeline.py        # 전체 실행 (이것만 돌리면 됨)
  collect.py         # RSS 수집·중복 제거
  validate.py        # 발행 전 자동 검사
  notify.py          # 네이버 초안 텔레그램 전송
  run_local.sh/.ps1  # 개인 서버 cron / Windows 작업 스케줄러용
site/                # Jekyll 사이트 (글은 site/_posts 에 쌓임)
naver/               # 네이버 블로그 초안 (.txt)
data/seen.json       # 이미 사용한 기사 기록 (중복 방지)
examples/            # 완성 글 예시 (가상 데이터)
tests/fixtures/      # 인터넷 없이 테스트하는 가상 RSS
```

## 동작 흐름

```
RSS 수집 ─▶ 새 기사 6건 미만이면 종료
   │
   ▼
Claude Code (claude -p, 헤드리스)
   ├─ site/_posts/YYYY-MM-DD-HHMM-<slot>-brief.md   (사이트 글)
   └─ naver/YYYY-MM-DD-HHMM.txt                      (네이버 초안)
   │
   ▼
validate.py ── 실패 ─▶ 오류 목록을 Claude에게 주고 1회 수정 ─▶ 그래도 실패면 rejected/ 로 격리, 발행 안 함
   │ 통과
   ▼
seen 기록 → 텔레그램으로 네이버 초안 전송 → git commit/push → GitHub Pages 배포
```

**검증 항목**: 프런트매터·분량·필수 소제목 / 출처 링크가 실제 수집 기사인지(지어낸 URL 차단) /
기사 제목·요약과 25자 이상 연속 일치하는지(복붙 차단) / 투자 권유성 표현 / 네이버 초안과 사이트 글의 유사도.

---

## 시작하기 (GitHub Actions — 서버 없이)

1. **새 GitHub 저장소**를 만들고 이 폴더 내용을 그대로 올립니다.
   ```bash
   git init && git add . && git commit -m "init" && git branch -M main
   git remote add origin https://github.com/<아이디>/<저장소>.git && git push -u origin main
   ```
   광고 수익 사이트라면 저장소는 Private이어도 됩니다 (Pages는 유료 플랜 필요 여부를 확인하세요. 무료 계정은 Public 저장소만 Pages 지원).

2. **Secrets 등록** — 저장소 Settings → Secrets and variables → Actions
   | 이름 | 값 | 필수 |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | console.anthropic.com 에서 발급 | ✅ |
   | `TELEGRAM_BOT_TOKEN` | 텔레그램 @BotFather 로 봇 생성 후 토큰 | 선택 |
   | `TELEGRAM_CHAT_ID` | 봇에게 말을 건 뒤 `https://api.telegram.org/bot<토큰>/getUpdates` 에서 chat.id | 선택 |

   모델을 고정하려면 Variables 탭에 `CLAUDE_MODEL` 추가 (비우면 Claude Code 기본값).

3. **Pages 켜기** — Settings → Pages → Source: **GitHub Actions**

4. **Actions 쓰기 권한** — Settings → Actions → General → Workflow permissions: **Read and write**

5. **사이트 정보 수정** — `site/_config.yml` 의 `title`, `url`, `contact_email` 등.
   - 기본 주소는 `https://<아이디>.github.io/<저장소>/` 입니다. 이 경우 `baseurl: "/<저장소>"`.
   - 애드센스를 하려면 **자체 도메인** 연결을 권장합니다 (ads.txt가 도메인 루트에 있어야 함).
     Settings → Pages → Custom domain 입력 후, `url` 을 그 도메인으로, `baseurl: ""`.

6. **출처 확인** — `config/sources.yaml` 에서 `enabled: false` 항목은 주소를 확인한 뒤 켭니다.

7. **첫 실행** — Actions 탭 → `news-brief` → Run workflow
   - 먼저 `dry_run` 체크로 수집만 확인 → 아티팩트(`run-...`)의 `data/raw/*.json` 확인
   - 그다음 체크 해제하고 실제 실행 → `site/_posts` 에 글이 커밋되고 사이트에 배포됨

실행 시각은 `news-brief.yml` 의 cron (UTC 기준)에서 바꿉니다. 기본값은 KST 07:35 / 11:35 / 14:35 / 17:35 (각 회차 25분 전).

## 로컬에서 테스트 (인터넷·API 키 없이)

```bash
pip install -r requirements.txt
python scripts/pipeline.py --dry-run --sources tests/fixtures/sources.test.yaml   # 수집 테스트
python scripts/validate.py --post examples/sample-post.md --naver examples/sample-naver.txt \
       --batch data/raw/<방금 생성된 파일>.json                                       # 검증기 테스트
```
※ 예시 글은 파일명이 날짜 형식이 아니라 "date 불일치" 오류가 하나 나오는 게 정상입니다.

실제 글 생성까지 로컬에서 보려면: `npm install -g @anthropic-ai/claude-code`, `.env.example` → `.env` 복사 후
키 입력, `python scripts/pipeline.py --skip-notify`.

## 개인 서버/PC에서 돌리기 (선택)

GitHub Actions 대신 상시 켜진 PC에서 돌릴 수도 있습니다. 결과를 push 하면 `pages.yml` 이 배포합니다.
- 리눅스/맥: `scripts/run_local.sh` 를 crontab에 등록 (파일 상단 주석 참고)
- Windows: `scripts/run_local.ps1` 을 작업 스케줄러에 등록 (파일 상단 주석 참고)
- 이 경우 `news-brief.yml` 의 `schedule:` 블록은 지워서 중복 실행을 막으세요.

---

## 복붙 발행 키트 (그림·표·그래프 포함)

네이버·티스토리는 글쓰기 API가 없어 자동 발행 대신 **복사 → 붙여넣기**용 페이지를 매 회차 만듭니다.

- Claude가 `naver/<stamp>.visuals.json` 에 대표이미지 문구·그래프·표 데이터를 쓰고, 본문에 `[그래프1]` `[표1]` 자리표시를 넣음
- `scripts/render_kit.py` 가 `site/kit/<stamp>/` 에 대표 이미지(cover.png), 그래프·표 PNG, 붙여넣기 페이지(index.html)를 생성
- 사이트와 함께 배포되므로 `https://<도메인>/kit/<stamp>/` 를 휴대폰·다른 PC에서 열어 [본문 전체 복사] → 붙여넣기
- 키트 목록: `https://<도메인>/kit/` · 검색 노출 차단(noindex, robots.txt, sitemap 제외)
- 예시: `python scripts/render_kit.py --naver examples/sample-naver.txt --out site/kit/sample`

---

## 네이버 블로그 운영

1. 텔레그램으로 온 초안을 확인 → 길게 눌러 복사 → 네이버 블로그 앱/에디터에 붙여넣기
2. **직접 손보기**: 첫 문단에 본인 경험·의견 한두 줄, 이미지 1~3장(직접 만든 표·캡처), 소제목 서식
3. `[태그]` 줄을 태그 칸에 넣고 발행

권장 사항
- 하루 1~2편만 발행 (자동 생성분 전부 올리지 않기). 같은 시각에 기계적으로 올리지 않기.
- 사이트 글을 그대로 옮기지 않기 — 검증기가 유사도 0.35 이상이면 막지만, 편집 과정에서 사이트 문장을 다시 붙이지 않도록 주의.
- 본문에 사이트 링크를 매번 넣는 것보다, 프로필·하단 고정 글에서 안내하는 편이 안전합니다.

## 수익화 체크리스트

- [ ] 자체 도메인 연결 + `site/_config.yml` 의 `url` 수정
- [ ] 소개(`about.md`)·개인정보처리방침(`privacy.md`) 내용 채우기, 시행일 수정
- [ ] 글 20~30편 이상 쌓인 뒤 애드센스 신청 → 승인 후 `adsense_client` 입력, `ads.txt` 주석 해제
- [ ] Google Search Console, **네이버 서치어드바이저**에 사이트 등록 → `sitemap.xml`, `feed.xml` 제출
      (소유 확인 메타태그는 `_config.yml` 의 `*_site_verification` 에 입력)
- [ ] 네이버 블로그 애드포스트 신청 (블로그 쪽 수익)
- [ ] 반응이 생기면 뉴스레터(스티비 등)로 구독자 확보 — 같은 글을 이메일로 재활용

> 단순 요약 나열은 검색엔진의 "대량 생성 콘텐츠" 정책에 걸리거나 애드센스 승인이 어려울 수 있습니다.
> `CLAUDE.md` 의 "무슨 일 / 왜 중요한가 / 체크포인트" 구조와 "오늘의 숫자" 해설이 차별점입니다.
> 여기에 본인 관점(예: 자영업자·투자자 시각)을 규칙으로 더 넣을수록 좋아집니다.

---

## 자주 고치는 곳

| 하고 싶은 것 | 고칠 파일 |
|---|---|
| 문체·글 구성·금지사항 | `CLAUDE.md` |
| 회차별 지시(이슈 개수, 선정 기준) | `prompts/brief.md` |
| 실행 시각 | `.github/workflows/news-brief.yml` cron |
| 출처 추가/제거 | `config/sources.yaml` |
| 분량·복제 허용치·금지 표현 | `config/settings.yaml` |
| 사이트 디자인 | `site/_layouts`, `site/assets/css/style.css` |

## 비용과 주의사항

- **API 비용**: 회차당 Claude 호출 1~2번(수정 포함). `settings.yaml` 의 `max_turns` 로 상한을 걸어 두고,
  Anthropic Console의 사용량 한도(Spend limit)도 설정하세요. 각 실행 로그에 회차 비용이 찍힙니다.
- **저작권**: RSS는 기사 발굴용으로만 쓰고, 본문은 새 문장으로 작성합니다. 각 언론사 RSS 이용약관을 확인하세요.
  원문 기사의 저작권은 언론사에 있으며, 글마다 출처 링크를 남깁니다.
- **정확성**: 자동 검증은 형식·출처·복제를 잡지만 사실 오류를 완벽히 잡지는 못합니다.
  초기 2주 정도는 발행된 글을 매일 훑어보고 `CLAUDE.md` 규칙을 다듬으세요.
- **투자 정보**: 특정 종목 매수·매도 권유는 금지 규칙과 검증기로 막아 두었습니다. 규칙을 완화하지 마세요.

## 문제 해결

| 증상 | 확인 |
|---|---|
| "새 기사가 부족해 종료" 반복 | `sources.yaml` 주소가 살아 있는지, `settings.yaml` 의 `window_hours`/`min_items` |
| 검증 실패로 발행 안 됨 | Actions 실행 → Artifacts `run-...` → `rejected/` 와 `logs/` 확인 |
| 글은 커밋됐는데 사이트에 안 보임 | Settings → Pages 소스가 "GitHub Actions"인지, `deploy` 잡 로그 |
| CSS가 깨짐 | `_config.yml` 의 `baseurl` (프로젝트 페이지면 "/저장소이름") |
| push 권한 오류 | Settings → Actions → Workflow permissions: Read and write |
| 예약 실행이 늦음 | GitHub 예약 실행은 혼잡 시 지연될 수 있음 (정상) |
