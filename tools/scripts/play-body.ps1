#requires -Version 5.1
<#
.SYNOPSIS
    Launch a body that lives outside D:\Steam (L3/L4 evidence helper).
.DESCRIPTION
    Steam games built on steam_api require the Steam client to be running and to hold
    an authorized session, otherwise the engine shows "Steam is not running" and never
    reaches the main menu. This script optionally starts the client first (-StartSteam),
    waits for it, then launches the body executable and reports process metrics.
.EXAMPLE
    pwsh -File tools/scripts/play-body.ps1 -AppId 550 -BodyDir src/data/body/550 -DryRun
.EXAMPLE
    pwsh -File tools/scripts/play-body.ps1 -AppId 550 -StartSteam -Seconds 600
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int]$AppId,
    [string]$BodyDir = "",
    [string]$ExeName = "",
    [switch]$StartSteam,
    [int]$Seconds = 30,
    [switch]$DryRun,
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'

if (-not $BodyDir) { $BodyDir = Join-Path $Root ("src/data/body/" + $AppId) }
$body = if ([IO.Path]::IsPathRooted($BodyDir)) { [IO.Path]::GetFullPath($BodyDir) } else { [IO.Path]::GetFullPath((Join-Path $Root $BodyDir)) }
if (-not (Test-Path $body)) { throw "body dir not found: $body" }

if (-not $ExeName) {
    $candidate = Get-ChildItem $body -Filter '*.exe' -File | Where-Object { $_.Name -notlike '*crash*' } | Select-Object -First 1
    if (-not $candidate) { throw "no exe found in $body" }
    $ExeName = $candidate.Name
}
$exe = Join-Path $body $ExeName
if (-not (Test-Path $exe)) { throw "exe not found: $exe" }

$steamExe = 'D:\Steam\steam.exe'
$steamRunning = [bool](Get-Process steam -ErrorAction SilentlyContinue)

if ($DryRun) {
    Write-Host ("[play] steam running: " + $steamRunning)
    Write-Host ("[play] start steam: " + [bool]$StartSteam)
    Write-Host ("[play] exe: " + $exe)
    Write-Host ("[play] duration: " + $Seconds + "s")
    exit 0
}

if (-not $steamRunning) {
    if (-not $StartSteam) {
        throw "Steam client is not running. steam_api games abort with 'Steam is not running'. Re-run with -StartSteam (writes to D:\Steam, needs your explicit OK)."
    }
    if (-not (Test-Path $steamExe)) { throw "steam.exe not found at $steamExe" }
    Write-Host "[play] starting Steam client..." -ForegroundColor Cyan
    Start-Process -FilePath $steamExe | Out-Null
    $waited = 0
    while ($waited -lt 90 -and -not (Get-Process steam -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 3; $waited += 3
    }
    Write-Host "[play] steam up after ${waited}s"
}

$appidFile = Join-Path $body 'steam_appid.txt'
if (-not (Test-Path $appidFile)) { Set-Content -Path $appidFile -Value $AppId -Encoding ASCII }

$reports = Join-Path $Root 'tests/reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$log = Join-Path $reports ("play-" + $AppId + "-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".log")

Write-Host "[play] launching $exe" -ForegroundColor Cyan
$proc = Start-Process -FilePath $exe -WorkingDirectory $body -PassThru
"start $(Get-Date -Format o) pid=$($proc.Id)" | Out-File $log -Encoding UTF8

$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 10
    $proc.Refresh()
    if ($proc.HasExited) {
        "exited code=$($proc.ExitCode) at $(Get-Date -Format o)" | Out-File $log -Append -Encoding UTF8
        Write-Host ("[play] process exited: code=" + $proc.ExitCode) -ForegroundColor Yellow
        exit $proc.ExitCode
    }
    $state = "alive cpu=$([math]::Round($proc.CPU,1))s ws=$([math]::Round($proc.WorkingSet64/1MB,0))MB title=$($proc.MainWindowTitle)"
    "$(Get-Date -Format o) $state" | Out-File $log -Append -Encoding UTF8
    Write-Host ("[play] " + $state)
}

$proc.Refresh()
$blocked = $proc.MainWindowTitle -match 'Error|error'
Write-Host ("[play] result: alive=" + (-not $proc.HasExited) + " title=" + $proc.MainWindowTitle)
if ($blocked) { Write-Host "[play] WARNING: error dialog detected - game likely did not reach the main menu" -ForegroundColor Red }
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force; Write-Host "[play] closed" }
Write-Host ("[play] log: " + $log)
if ($blocked) { exit 3 }
exit 0
