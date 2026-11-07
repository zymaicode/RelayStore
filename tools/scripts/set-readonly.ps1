#requires -Version 5.1
<#
.SYNOPSIS
    Make the open-source partition read-only (or unlock it).
.DESCRIPTION
    Default: set the ReadOnly attribute on every file/dir under opensource,
    write a .readonly marker, and deny write/create via ACL for the current user.
    -Unlock removes the ACL deny, the attributes and the marker.
.EXAMPLE
    pwsh -File tools/scripts/set-readonly.ps1
    pwsh -File tools/scripts/set-readonly.ps1 -Unlock
#>
[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$Unlock,
    [switch]$Strict
)
$ErrorActionPreference = 'Stop'
$target = Join-Path $Root 'opensource'
if (-not (Test-Path $target)) { throw "opensource partition not found: $target" }

$sid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value

if ($Unlock) {
    & icacls $target /remove:d "${sid}" /T /C /Q 2>&1 | Out-Null
    Get-ChildItem $target -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $_.Attributes = $_.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
    }
    Remove-Item (Join-Path $target '.readonly') -Force -ErrorAction SilentlyContinue
    Write-Host '[unlock] opensource is writable again'
    exit 0
}

$count = 0
Get-ChildItem $target -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
    if (-not $_.Attributes.ToString().Contains('ReadOnly')) {
        $_.Attributes = $_.Attributes -bor [IO.FileAttributes]::ReadOnly
        $count++
    }
}
if ($Strict) {
    & icacls $target /deny "${sid}:(OI)(CI)(WD,AD,WEA,WA)" /T /C /Q 2>&1 | Out-Null
}
@"
opensource partition is READ-ONLY
created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
rule:    see CLAUDE.md section 2 and opensource/README.md
unlock:  pwsh -File tools/scripts/set-readonly.ps1 -Unlock
"@ | Set-Content -Path (Join-Path $target '.readonly') -Encoding UTF8

Write-Host "[readonly] $count object(s) marked; strict=$Strict; marker written"
exit 0
