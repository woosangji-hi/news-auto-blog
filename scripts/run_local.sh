#!/usr/bin/env bash
# 개인 서버(리눅스/맥) cron 용 실행 스크립트
# crontab -e 에 추가 (서버 시간이 KST 라면):
#   7 7,12,18 * * * /path/to/news-auto-blog/scripts/run_local.sh >> /path/to/news-auto-blog/logs/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
export TZ=Asia/Seoul
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"   # claude, node 경로
[ -d .venv ] && source .venv/bin/activate
mkdir -p logs
git pull --rebase --quiet
python scripts/pipeline.py --git-push
