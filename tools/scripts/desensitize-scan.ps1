#requires -Version 5.1
<#
.SYNOPSIS
    Scan files for content that must not leave the machine (desensitization gate).
.DESCRIPTION
    Detects user-profile paths, UNC paths, e-mail addresses, SteamID64, API tokens,
    private keys, hardcoded passwords, Chinese mobile numbers and the current user name.
    Exit 0 when clean, 1 when anything matches.
.EXAMPLE
    pwsh -File tools/scripts/desensitize-scan.ps1 -Path .\src
    pwsh -File tools/scripts/desensitize-scan.ps1 -Path .\docs -AllowDocPaths
#>
[CmdletBinding()]
param(
    [string[]]$Path = @('.\src', '.\docs', '.\tests'),
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$IncludePrivate
)
$ErrorActionPreference = 'Stop'

$patterns = [ordered]@{
    'user-profile-path' = '[A-Za-z]:\\Users\\[^\\]+'
    'appdata-path'      = '\\AppData\\'
    'unc-path'          = '\\\\[A-Za-z0-9._-]+\\'
    'email'             = '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    'steamid64'         = '\b7656119\d{10}\b'
    'github-token'      = '\bgh[pousr]_[A-Za-z0-9]{20,}'
    'generic-secret'    = '(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*["'']?[A-Za-z0-9_\-\.]{8,}'
    'private-key'       = '-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----'
    'bearer'            = '(?i)authorization\s*:\s*bearer\s+\S+'
    'cookie-jar'        = '(?i)(steamLoginSecure|cookie\s*[:=]\s*\S{20,})'
    'cn-mobile'         = '\b1[3-9]\d{9}\b'
}
$userName = $env:USERNAME
if ($userName -and $userName.Length -ge 3) {
    $patterns['current-username'] = '\\b' + [regex]::Escape($userName) + '\\b'
}

$roots = @()
foreach ($p in $Path) {
    $full = if ([IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $Root $p }
    if (Test-Path $full) { $roots += (Get-Item $full) }
}
if (-not $roots) { Write-Host '[scan] nothing to scan'; exit 0 }

$exclude = @('.git', 'node_modules', '__pycache__', 'tests\reports', 'src\data', '.venv')
$hits = New-Object System.Collections.Generic.List[object]
$scanned = 0

foreach ($r in $roots) {
    $files = if ($r.PSIsContainer) {
        Get-ChildItem $r.FullName -Recurse -File -Force -ErrorAction SilentlyContinue
    } else { @($r) }
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($Root.Length).TrimStart('\', '/')
        if (-not $IncludePrivate) {
            $skip = $false
            foreach ($ex in $exclude) { if ($rel -like "*$ex*") { $skip = $true; break } }
            if ($skip) { continue }
        }
        if ($f.Length -gt 2MB) { continue }
        $scanned++
        $lineNo = 0
        foreach ($line in [IO.File]::ReadLines($f.FullName)) {
            $lineNo++
            foreach ($k in $patterns.Keys) {
                if ($line -cmatch $patterns[$k]) {
                    $hits.Add([pscustomobject]@{ Pattern = $k; File = $rel; Line = $lineNo })
                    break
                }
            }
        }
    }
}

if ($hits.Count -eq 0) {
    Write-Host "[scan] clean: $scanned file(s) scanned, 0 hit(s)"
    exit 0
}
Write-Host "[scan] BLOCKED: $($hits.Count) hit(s) in $scanned file(s)"
$hits | Group-Object File | ForEach-Object {
    Write-Host ("  {0}" -f $_.Name)
    $_.Group | ForEach-Object { Write-Host ("    line {0}: {1}" -f $_.Line, $_.Pattern) }
}
exit 1
