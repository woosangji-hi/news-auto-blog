# 텔레그램 봇 연결 (한 번만 실행)
# 1) 봇 토큰을 입력받고  2) 봇에게 보낸 메시지에서 내 채팅 ID를 찾아
# 3) GitHub 저장소 비밀값(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)에 저장한 뒤  4) 시험 메시지를 보냅니다.
# 토큰은 화면에 표시되지 않고, 이 PC에 파일로 저장되지도 않습니다.
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "woosangji-hi/news-auto-blog"

Write-Host ""
Write-Host "1) BotFather 가 준 봇 토큰을 붙여넣고 Enter (화면에 안 보여도 정상)" -ForegroundColor Cyan
$sec = Read-Host -AsSecureString "토큰"
$token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if (-not ($token -match '^\d+:[A-Za-z0-9_-]{30,}$')) { Write-Host "토큰 형식이 아닙니다. 다시 실행해 주세요." -ForegroundColor Red; exit 1 }

try { $me = Invoke-RestMethod "https://api.telegram.org/bot$token/getMe" }
catch { Write-Host "토큰이 맞지 않습니다. BotFather 에서 다시 복사해 주세요." -ForegroundColor Red; exit 1 }
Write-Host ("   봇 확인: @" + $me.result.username) -ForegroundColor Green

Write-Host ""
Write-Host ("2) 휴대폰 텔레그램에서 @" + $me.result.username + " 을 열고 [시작] 또는 아무 메시지(예: 안녕)를 보내세요.") -ForegroundColor Cyan
Write-Host "   보냈으면 여기서 Enter" -ForegroundColor Cyan
[void](Read-Host)

$chatId = $null
for ($i = 0; $i -lt 6 -and -not $chatId; $i++) {
    $upd = Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates"
    $msg = $upd.result | Where-Object { $_.message -and $_.message.chat.type -eq "private" } | Select-Object -Last 1
    if ($msg) { $chatId = [string]$msg.message.chat.id } else { Start-Sleep -Seconds 5 }
}
if (-not $chatId) { Write-Host "봇에게 온 메시지를 찾지 못했습니다. 봇에게 메시지를 보낸 뒤 다시 실행해 주세요." -ForegroundColor Red; exit 1 }
Write-Host "   채팅 ID 확인 완료" -ForegroundColor Green

Write-Host ""
Write-Host "3) GitHub 저장소에 저장 중..." -ForegroundColor Cyan
& $gh secret set TELEGRAM_BOT_TOKEN --body $token -R $repo
& $gh secret set TELEGRAM_CHAT_ID --body $chatId -R $repo

$text = "✅ 연결 완료! 매일 08·12·15·18시 무렵 네이버·티스토리 초안이 이 채팅으로 옵니다."
Invoke-RestMethod -Method Post "https://api.telegram.org/bot$token/sendMessage" -Body @{ chat_id = $chatId; text = $text } | Out-Null
Write-Host "4) 시험 메시지를 보냈습니다. 휴대폰을 확인하세요. 이 창은 닫아도 됩니다." -ForegroundColor Green
