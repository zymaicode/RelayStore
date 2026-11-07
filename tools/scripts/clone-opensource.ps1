#requires -Version 5.1
<#
.SYNOPSIS
    Clone the project's read-only open-source corpus into .\opensource.
.DESCRIPTION
    Every repository is cloned as a shallow snapshot (--depth 1) because the
    opensource partition is a reference shelf, not a development area.
    Re-running the script skips repositories that are already present.
.NOTES
    Partition: opensource (read-only). Never edit inside the cloned trees.
    Copy what you need out to src\ or tools\ instead.
#>
[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$Force
)

$ErrorActionPreference = 'Continue'
$ospath = Join-Path $Root 'opensource'
$logPath = Join-Path $ospath '_clone-log.txt'

$repos = @(
    @{ Name = 'ManifestHub-fylsdy';                 Url = 'https://github.com/fylsdy/ManifestHub.git';                  Role = '清单库-活跃主力（个人收集+Fork）' },
    @{ Name = 'ManifestHub3-steamtools-games';      Url = 'https://github.com/steamtools-games/ManifestHub3.git';       Role = '清单库-官方重建数据层（纯 JSON）' },
    @{ Name = 'ManifestHub-SteamAutoCracks';        Url = 'https://github.com/SteamAutoCracks/ManifestHub.git';         Role = '清单库-元老级仓库（已降级）' },
    @{ Name = 'ManifestHub2-SSMGAlt';               Url = 'https://github.com/SSMGAlt/ManifestHub2.git';                Role = '清单库-冻结分支快照（旧版回退）' },
    @{ Name = 'lua-manifest-updater';               Url = 'https://github.com/fairy-root/lua-manifest-updater.git';     Role = '工具-更新 Lua 中的 manifest ID' },
    @{ Name = 'LuaTools-madoiscool';                Url = 'https://github.com/madoiscool/LuaTools.git';                 Role = '工具-Windows 桌面客户端' },
    @{ Name = 'ManifestHub-trionine';               Url = 'https://github.com/trionine/ManifestHub.git';                Role = 'Web 前端-查询/下载界面' }
)

function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}

if (-not (Test-Path $ospath)) { New-Item -ItemType Directory -Force -Path $ospath | Out-Null }
Write-Log "=== clone run start (root=$Root) ==="

foreach ($repo in $repos) {
    $dest = Join-Path $ospath $repo.Name
    if ((Test-Path $dest) -and -not $Force) {
        Write-Log "SKIP  $($repo.Name) (already present)"
        continue
    }
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Write-Log "CLONE $($repo.Name) <- $($repo.Url)"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $out = & git -c core.longpaths=true -c core.autocrlf=false clone --depth 1 --single-branch --no-tags $repo.Url $dest 2>&1
        $code = $LASTEXITCODE
        $sw.Stop()
        if ($code -eq 0) {
            $sizeMB = [math]::Round(((Get-ChildItem $dest -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB), 1)
            Write-Log ("OK    {0}  ({1} MB, {2:N1}s)" -f $repo.Name, $sizeMB, $sw.Elapsed.TotalSeconds)
        } else {
            Write-Log ("FAIL  {0}  exit={1}  {2}" -f $repo.Name, $code, ($out -join ' | '))
        }
    } catch {
        $sw.Stop()
        Write-Log ("FAIL  {0}  {1}" -f $repo.Name, $_.Exception.Message)
    }
}

# --- 非 git 资源（脚本 / API / 文档）直接抓取到 references ---
$refDir = Join-Path $ospath 'references'
if (-not (Test-Path $refDir)) { New-Item -ItemType Directory -Force -Path $refDir | Out-Null }
$assets = @(
    @{ Name = 'manifests.ps1'; Url = 'https://luatools.vercel.app/manifests.ps1'; Note = 'LuaTools 静态清单脚本（GitHub -> Morrenus 自动回退）' }
)
foreach ($a in $assets) {
    $target = Join-Path $refDir $a.Name
    if ((Test-Path $target) -and -not $Force) { Write-Log "SKIP  ref:$($a.Name) (already present)"; continue }
    try {
        Invoke-WebRequest -Uri $a.Url -OutFile $target -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop
        $sz = (Get-Item $target).Length
        Write-Log ("OK    ref:{0}  ({1} bytes)  {2}" -f $a.Name, $sz, $a.Note)
    } catch {
        Write-Log ("FAIL  ref:{0}  {1}" -f $a.Name, $_.Exception.Message)
    }
}

Write-Log "=== clone run end ==="
