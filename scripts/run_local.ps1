# 개인 PC/서버(Windows) 작업 스케줄러 용 실행 스크립트
# 작업 스케줄러 → 기본 작업 만들기 → 매일 07:07 (12:07, 18:07 트리거 추가)
#   프로그램: powershell.exe
#   인수:     -ExecutionPolicy Bypass -File "C:\path\to\news-auto-blog\scripts\run_local.ps1"
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = "logs\run-$(Get-Date -Format yyyy-MM-dd).log"

if (Test-Path ".venv\Scripts\Activate.ps1") { . .\.venv\Scripts\Activate.ps1 }
git pull --rebase --quiet *>> $log
python scripts\pipeline.py --git-push *>> $log
exit $LASTEXITCODE
