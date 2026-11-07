#requires -Version 5.1
<#
.SYNOPSIS
    Project environment and partition self-check.
#>
[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Continue'
$problems = @()
function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    $tag = if ($Ok) { '[ok]  ' } else { '[FAIL]' }
    Write-Host ("{0} {1} {2}" -f $tag, $Name, $Detail)
    if (-not $Ok) { $script:problems += $Name }
}

Write-Host "project root: $Root"
foreach ($d in @('src', 'tests', 'tools', 'opensource', 'backup/vcs', 'backup/private', 'memory', 'docs')) {
    Check "partition $d" (Test-Path (Join-Path $Root $d))
}
foreach ($f in @('CLAUDE.md', 'AGENT.md', 'docs/PRD.md', 'docs/TRD.md', 'docs/ARD.md', 'memory/index.md')) {
    Check "doc $f" (Test-Path (Join-Path $Root $f))
}

$git = Get-Command git -ErrorAction SilentlyContinue
Check 'git' ([bool]$git) $(if ($git) { (git --version) } else { '' })
$py = Get-Command python -ErrorAction SilentlyContinue
Check 'python' ([bool]$py) $(if ($py) { (python --version 2>&1) } else { '' })
$node = Get-Command node -ErrorAction SilentlyContinue
Check 'node (optional)' $true $(if ($node) { (node --version) } else { 'not installed' })

$os = Join-Path $Root 'opensource'
$repos = Get-ChildItem $os -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'references' }
Check 'opensource snapshots >= 6' ($repos.Count -ge 6) "$($repos.Count) repo(s)"
Check 'opensource readonly marker' (Test-Path (Join-Path $os '.readonly'))

$vcs = Join-Path $Root 'backup/vcs'
if (Test-Path (Join-Path $vcs '.git')) {
    $remotes = (& git -C $vcs remote 2>&1)
    Check 'backup/vcs has no remote' ([string]::IsNullOrWhiteSpace(($remotes -join ''))) ($remotes -join ' ')
    $log = (& git -C $vcs log --oneline -1 2>&1)
    Check 'backup/vcs has commits' (-not [string]::IsNullOrWhiteSpace(($log -join ''))) ($log -join ' ')
} else {
    Check 'backup/vcs is a git repo' $false
}

$drive = Get-PSDrive -Name ($Root.Substring(0, 1)) -ErrorAction SilentlyContinue
if ($drive) { Check 'disk free > 5GB' ($drive.Free -gt 5GB) ("{0:N1} GB free" -f ($drive.Free / 1GB)) }

Write-Host ''
if ($problems.Count -eq 0) { Write-Host '[env] all checks passed'; exit 0 }
Write-Host "[env] $($problems.Count) problem(s): $($problems -join ', ')"
exit 1
