$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Console]::InputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$env:PYTHONUTF8 = "1"

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $here "MeowLauncher.py"
$base   = Join-Path $env:LOCALAPPDATA "MeowLauncher"
$embed  = Join-Path $base "python"
if (-not (Test-Path $script)) {
    Write-Host "Рядом со скриптом нет MeowLauncher.py." -ForegroundColor Red
    exit 1
}

function Test-Py([string]$exe, [string[]]$pre = @()) {
    try {
        $o = & $exe @pre -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
        return ([int]("$o".Trim()) -ge 308)
    } catch { return $false }
}

function Find-Python {
    $cands = @(
        @((Join-Path $embed "python.exe"), @()),
        @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"), @()),
        @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"), @()),
        @("py", @("-3")),
        @("python", @()),
        @("python3", @())
    )
    foreach ($c in $cands) {
        $exe = $c[0]; $pre = $c[1]
        if (($exe -like "*\*") -and -not (Test-Path $exe)) { continue }
        if ($exe -like "*WindowsApps*") { continue }
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            if (Test-Py $exe $pre) { return ,@($exe, $pre) }
        }
    }
    return $null
}

$py = Find-Python

if (-not $py -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "Python не найден. Пробую winget (установка для текущего пользователя)..." -ForegroundColor Cyan
    try {
        winget install -e --id Python.Python.3.12 --scope user --silent `
            --accept-package-agreements --accept-source-agreements | Out-Host
    } catch {}
    $py = Find-Python
}

if (-not $py) {
    Write-Host "Скачиваю портативный Python (без установки, без админа)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $embed | Out-Null
    $zip = Join-Path $base "python-embed.zip"
    $url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $embed -Force
    Remove-Item $zip -Force
    $py = Find-Python
}

if (-not $py) {
    Write-Host "Не удалось получить Python. Установите Python 3.8+ вручную." -ForegroundColor Red
    exit 1
}

$exe = $py[0]
$pre = @($py[1])
& $exe @pre $script @args
exit $LASTEXITCODE
