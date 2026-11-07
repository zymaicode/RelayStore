#requires -Version 5.1
<#
.SYNOPSIS
    Merge gate: green tests + fresh report + ARD task not pending.
.EXAMPLE
    pwsh -File tools/scripts/gate-check.ps1 -TaskId M1-T01
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TaskId,
    [ValidateSet('all', 'unit', 'integration', 'contract', 'e2e', 'compatibility', 'security')]
    [string]$Area = 'all',
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'
$fail = @()

$ard = Join-Path $Root 'docs/ARD.md'
if (-not (Test-Path $ard)) {
    $fail += "ARD missing: $ard"
} else {
    $hit = Select-String -Path $ard -Pattern ([regex]::Escape($TaskId)) | Select-Object -First 1
    if (-not $hit) {
        $fail += "task $TaskId not found in ARD.md"
    } elseif ($hit.Line -match '\|\s*pending\s*\|') {
        $fail += "task $TaskId is still pending in ARD.md"
    }
}

$run = Join-Path $Root 'tools/scripts/run-tests.ps1'
& $run -Area $Area -Root $Root
if ($LASTEXITCODE -ne 0) { $fail += "tests failed (area=$Area, exit=$LASTEXITCODE)" }

$reports = Join-Path $Root 'tests/reports'
$fresh = Get-ChildItem $reports -Filter "test-report-$Area-*.txt" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-10) } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $fresh) { $fail += 'no fresh test report in tests/reports' }

if ($fail.Count -gt 0) {
    Write-Host '[gate] BLOCKED'
    $fail | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "[gate] PASS: $TaskId (report $(Split-Path $fresh.FullName -Leaf), ARD updated)"
exit 0
