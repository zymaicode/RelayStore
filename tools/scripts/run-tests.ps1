#requires -Version 5.1
<#
.SYNOPSIS
    Run the test suite and drop a report into tests/reports/.
.EXAMPLE
    pwsh -File tools/scripts/run-tests.ps1 -All
    pwsh -File tools/scripts/run-tests.ps1 -Area unit
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'unit', 'integration', 'contract', 'e2e', 'compatibility', 'security')]
    [string]$Area = 'all',
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'
$reports = Join-Path $Root 'tests/reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$report = Join-Path $reports "test-report-$Area-$stamp.txt"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Host '[test] python not found'; exit 2 }
$target = if ($Area -eq 'all') { Join-Path $Root 'tests' } else { Join-Path $Root "tests/$Area" }
if (-not (Test-Path $target)) { Write-Host "[test] no such area: $Area"; exit 2 }

$hasPytest = $false
& python -c 'import pytest' 2>$null
if ($LASTEXITCODE -eq 0) { $hasPytest = $true }

$env:PYTHONPATH = (Join-Path $Root 'src/py') + [IO.Path]::PathSeparator + $env:PYTHONPATH
Push-Location $Root
$code = 1
try {
    "test run: area=$Area at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $report -Encoding UTF8
    if ($hasPytest) {
        $pytestArgs = @('-m', 'pytest', $target, '-q', '--color=no')
        $out = & python @pytestArgs 2>&1
        $code = $LASTEXITCODE
    } else {
        Write-Host '[test] pytest not installed; falling back to unittest discovery'
        $out = & python -m unittest discover -s $target -t $Root -p 'test_*.py' -v 2>&1
        $code = $LASTEXITCODE
        # 0 tests is a gate failure, not a pass: an empty suite must never satisfy the gate.
        if (($out -join "`n") -match 'Ran 0 tests') {
            Write-Host '[test] no tests collected under the given area'
            $code = 3
        }
    }
    $out | Out-File $report -Append -Encoding UTF8
    Write-Host ("[test] {0} | exit={1} | report={2}" -f $Area, $code, (Split-Path $report -Leaf))
    ($out | Select-Object -Last 15) | ForEach-Object { Write-Host $_ }
} finally { Pop-Location }
exit $code