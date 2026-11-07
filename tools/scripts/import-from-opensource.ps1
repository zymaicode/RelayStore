#requires -Version 5.1
<#
.SYNOPSIS
    Copy a file out of the read-only open-source partition, with provenance header.
.EXAMPLE
    pwsh -File tools/scripts/import-from-opensource.ps1 -Repo ManifestHub-trionine -Path src/utils/foo.js -Target src/py/steam_research/vendor_ref/foo.js
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$srcRoot = Join-Path $Root "opensource/$Repo"
if (-not (Test-Path $srcRoot)) { throw "repo not found in opensource: $Repo" }

$src = Join-Path $srcRoot $Path
if (-not (Test-Path $src)) { throw "file not found: $Path (repo $Repo)" }
$dst = if ([IO.Path]::IsPathRooted($Target)) { $Target } else { Join-Path $Root $Target }

$allowed = @((Join-Path $Root 'src'), (Join-Path $Root 'tools'))
$ok = $false
foreach ($a in $allowed) { if ($dst.StartsWith($a, [StringComparison]::OrdinalIgnoreCase)) { $ok = $true } }
if (-not $ok) { throw "target must be inside src/ or tools/: $dst" }
if ((Test-Path $dst) -and -not $Force) { throw "target exists (use -Force): $dst" }

$commit = 'unknown'
Push-Location $srcRoot
try { $commit = (& git rev-parse --short HEAD 2>$null) } catch { } finally { Pop-Location }

New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
$header = @"
# source: $Repo@$commit
# path:   $Path
# copied: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# note:   copied out of read-only opensource/ ; do not import it back
"@
$body = Get-Content $src -Raw
Set-Content -Path $dst -Value ($header + [Environment]::NewLine + $body) -Encoding UTF8
Write-Host "[import] $Repo/$Path -> $Target (commit $commit)"
exit 0
