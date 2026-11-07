#requires -Version 5.1
<#
.SYNOPSIS
    Build a desensitized snapshot of the project into the local version repo (backup/vcs).
.DESCRIPTION
    Verifies no remote, copies src/docs/tests + root docs to a staging area,
    runs the desensitization scan (aborts on any hit), mirrors into backup/vcs and commits.
.EXAMPLE
    pwsh -File tools/scripts/backup-snapshot.ps1 -Message "chore: baseline"
    pwsh -File tools/scripts/backup-snapshot.ps1 -Message "feat: acf parser" -Tag v0.1.0
#>
[CmdletBinding()]
param(
    [string]$Message = '',
    [string]$Tag = '',
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'
$repo = Join-Path $Root 'backup/vcs'
$staging = Join-Path $Root 'src/data/tmp/backup-staging'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'

if (-not (Test-Path (Join-Path $repo '.git'))) {
    git init -b main $repo | Out-Null
    & git -C $repo config user.name 'steam-research'
    & git -C $repo config user.email 'backup@local.invalid'
    Write-Host "[backup] initialized local repo at $repo"
}
$hooks = Join-Path $Root 'tools/hooks'
if (Test-Path $hooks) { & git -C $repo config core.hooksPath $hooks }
$remotes = & git -C $repo remote 2>&1
if ($remotes) { throw "backup/vcs must have NO remote, found: $remotes" }

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staging | Out-Null
foreach ($d in @('src', 'docs', 'tests')) {
    $from = Join-Path $Root $d
    if (-not (Test-Path $from)) { continue }
    & robocopy $from (Join-Path $staging $d) /MIR /NFL /NDL /NJH /NJS /NP /XD '.git' 'cache' 'reports' 'out' 'tmp' 'data' '__pycache__' 'node_modules' '.venv' /XF '*.pyc' '*.log' | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $d (code $LASTEXITCODE)" }
}
foreach ($f in @('CLAUDE.md', 'AGENT.md', '.gitignore')) {
    $from = Join-Path $Root $f
    if (Test-Path $from) { Copy-Item $from (Join-Path $staging $f) -Force }
}
if (Test-Path (Join-Path $staging 'tests/reports')) { Remove-Item (Join-Path $staging 'tests/reports') -Recurse -Force }

Write-Host '[backup] scanning staging for sensitive content...'
$scan = Join-Path $Root 'tools/scripts/desensitize-scan.ps1'
& $scan -Root $staging -Path '.'
if ($LASTEXITCODE -ne 0) {
    Write-Host '[backup] ABORTED: desensitization scan failed; nothing was committed'
    exit 1
}

foreach ($item in Get-ChildItem $staging -Force) {
    $dest = Join-Path $repo $item.Name
    if ($item.PSIsContainer) {
        & robocopy $item.FullName $dest /MIR /NFL /NDL /NJH /NJS /NP /XD '.git' | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy into repo failed for $($item.Name) (code $LASTEXITCODE)" }
    } else {
        Copy-Item $item.FullName $dest -Force
    }
}
if (-not $Message) { $Message = "chore(backup): snapshot $stamp" }
& git -C $repo add -A | Out-Null
$status = & git -C $repo status --porcelain
if (-not $status) {
    Write-Host '[backup] no change since last snapshot'
} else {
    & git -C $repo commit -m $Message 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
    Write-Host "[backup] committed: $Message"
}
if ($Tag) {
    & git -C $repo tag -a $Tag -m "snapshot $stamp" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "[backup] tagged $Tag" }
}
& git -C $repo log --oneline -1
exit 0
