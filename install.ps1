$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$repo   = if ($env:MEOW_REPO)   { $env:MEOW_REPO }   else { "OWNER/REPO" }
$branch = if ($env:MEOW_BRANCH) { $env:MEOW_BRANCH } else { "main" }
if ($repo -eq "OWNER/REPO") {
    Write-Host 'Укажите репозиторий: $env:MEOW_REPO="owner/repo"' -ForegroundColor Red
    return
}

$app = Join-Path $env:LOCALAPPDATA "MeowLauncher\app"
$tmp = Join-Path $env:TEMP ("meowlauncher-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $app, $tmp | Out-Null

try {
    $zip = Join-Path $tmp "src.zip"
    Write-Host "Скачиваю MeowLauncher" -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$repo/zip/refs/heads/$branch" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp -Force

    $src = Get-ChildItem -Path $tmp -Recurse -Directory -Filter "launcher" | Select-Object -First 1
    if (-not $src) { throw "В архиве нет папки launcher." }

    $pkg = Join-Path $app "meowlauncher"
    if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
    Copy-Item -Path (Join-Path $src.FullName "*") -Destination $app -Recurse -Force
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

$run = Join-Path $app "MeowLauncher.ps1"
Write-Host ""
Write-Host "Готово. Повторный запуск:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$run`""
Write-Host ""
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $run
