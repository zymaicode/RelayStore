#requires -Version 5.1
<#
.SYNOPSIS
    Download a game body with Valve steamcmd into an independent directory (never D:\Steam).
.DESCRIPTION
    Uses the downloaded steamcmd.exe from tools/bin. The account password / Steam Guard code are
    typed by the human into the console - the script never stores or echoes credentials.
.PARAMETER AppId
    Steam appid to install (e.g. 550 for Left 4 Dead 2).
.PARAMETER OutDir
    Target directory. Defaults to src/data/body/<appid> (git ignored).
.PARAMETER Account
    Steam login name. Omit with -Anonymous for keyless/public apps.
.EXAMPLE
    pwsh -File tools/scripts/steam-download.ps1 -AppId 550 -Account your_login
.EXAMPLE
    pwsh -File tools/scripts/steam-download.ps1 -AppId 550 -Account your_login -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int]$AppId,
    [string]$OutDir = "",
    [string]$Account = "",
    [switch]$Anonymous,
    [switch]$NoValidate,
    [switch]$DryRun,
    # Opt-in: pipe output to a log file. NOTE: piping buffers the native console,
    # so the interactive password / Steam Guard prompt becomes invisible. Leave it off
    # unless credentials are not needed.
    [string]$LogFile = "",
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'

$exe = Join-Path $Root 'tools/bin/steamcmd.exe'
if (-not (Test-Path $exe)) {
    throw "steamcmd.exe not found at $exe - download it first (see memory/experience/20261106-steamcmd-official-route.md)"
}

if (-not $OutDir) { $OutDir = Join-Path $Root ("src/data/body/" + $AppId) }
$outFull = [IO.Path]::GetFullPath($OutDir)

# Hard guard (D-016): never write inside the real Steam client or its library.
$forbidden = @('D:\Steam', 'C:\Program Files (x86)\Steam')
foreach ($bad in $forbidden) {
    if ($outFull.StartsWith($bad, [StringComparison]::OrdinalIgnoreCase)) {
        throw "refusing to install into $outFull (inside $bad); pick an independent directory"
    }
}

New-Item -ItemType Directory -Force -Path $outFull | Out-Null

$loginArgs = if ($Anonymous) { @('+login', 'anonymous') } elseif ($Account) { @('+login', $Account) } else { throw 'pass -Account <login> or -Anonymous' }
$validateArgs = if ($NoValidate) { @() } else { @('validate') }

$steamArgs = @(
    '+force_install_dir', $outFull
) + $loginArgs + @(
    '+app_update', $AppId
) + $validateArgs + @('+quit')

if ($DryRun) {
    Write-Host ("[steamcmd] " + $exe + " " + ($steamArgs -join ' '))
    Write-Host "[steamcmd] target: $outFull"
    exit 0
}

$reports = Join-Path $Root 'tests/reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$log = if ($LogFile) { $LogFile } else { "" }

Write-Host "[steamcmd] installing appid $AppId into $outFull" -ForegroundColor Cyan
Write-Host "[steamcmd] password / Steam Guard prompts are answered by you in this console" -ForegroundColor DarkGray
if ($log) { Write-Host "[steamcmd] output is piped to $log (interactive prompts may not render)" -ForegroundColor Yellow }

$code = 1
try {
    if ($log) {
        & $exe @steamArgs 2>&1 | Tee-Object -FilePath $log
    } else {
        # Let steamcmd own the console: piping hides its prompts and progress bar.
        & $exe @steamArgs
    }
    $code = $LASTEXITCODE
} finally {
    $acf = Get-ChildItem -Path (Join-Path $outFull 'steamapps') -Filter "appmanifest_$AppId.acf" -ErrorAction SilentlyContinue | Select-Object -First 1
    $bytes = (Get-ChildItem -Path $outFull -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0 }
    Write-Host ""
    Write-Host "[steamcmd] exit=$code  log=$log"
    Write-Host ("[steamcmd] bytes on disk: {0:N0} ({1:N1} GB)" -f $bytes, ($bytes / 1GB))
    if ($acf) { Write-Host ("[steamcmd] manifest: " + $acf.FullName) } else { Write-Host "[steamcmd] no appmanifest written (login failed or app not owned)" -ForegroundColor Yellow }
}
exit $code
