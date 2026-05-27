<#
    copy_to_drive.ps1 — sync .f3z/.f3d source files from the local _sources/
    folder into the public-facing Google Drive folder so visitors of
    techcnc.ca/machining-examples can download them.

    Source:      G:\My Drive\Public_Tech_CNC_Data\Examples\_sources\
    Destination: H:\My Drive\TECHCNC\Public CNC Data\Examples\

    After Drive finishes syncing, open each file in drive.google.com, share
    "Anyone with the link → Viewer", copy the share URL, and paste it into
    examples/<slug>/meta.yaml as drive.url + drive.file_id.

    Usage (from anywhere):
        powershell -File "G:\My Drive\Public_Tech_CNC_Data\Examples\_scripts\copy_to_drive.ps1"
        powershell -File "...\copy_to_drive.ps1" -DryRun
        powershell -File "...\copy_to_drive.ps1" -Force         # overwrite if newer
#>

[CmdletBinding()]
param(
    [string]$Source      = (Join-Path (Split-Path -Parent $PSScriptRoot) '_sources'),
    [string]$Destination = 'H:\My Drive\TECHCNC\Public CNC Data\Examples',
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Source not found: $Source"
}
if (-not (Test-Path -LiteralPath $Destination)) {
    if ($DryRun) {
        Write-Host "[dry] would create $Destination"
    } else {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        Write-Host "Created $Destination"
    }
}

$patterns = @('*.f3d', '*.f3z')
$files = foreach ($p in $patterns) {
    Get-ChildItem -LiteralPath $Source -Filter $p -File -ErrorAction SilentlyContinue
}

if (-not $files) {
    Write-Warning "No .f3d / .f3z files in $Source"
    return
}

$copied = 0
$skipped = 0
$total = 0

foreach ($f in $files) {
    $total++
    $dst = Join-Path $Destination $f.Name
    $exists = Test-Path -LiteralPath $dst

    $action = 'copy'
    if ($exists -and -not $Force) {
        $srcWrite = $f.LastWriteTimeUtc
        $dstWrite = (Get-Item -LiteralPath $dst).LastWriteTimeUtc
        if ($dstWrite -ge $srcWrite) {
            $action = 'skip (dest newer or equal)'
        }
    }

    if ($action -ne 'copy') {
        Write-Host "[skip] $($f.Name) — $action"
        $skipped++
        continue
    }

    $sizeMb = [math]::Round($f.Length / 1MB, 1)
    if ($DryRun) {
        Write-Host "[dry] copy $($f.Name) ($sizeMb MB)"
    } else {
        Copy-Item -LiteralPath $f.FullName -Destination $dst -Force
        Write-Host "[ok]  $($f.Name) ($sizeMb MB)"
        $copied++
    }
}

Write-Host ""
Write-Host "Summary: $copied copied, $skipped skipped, $total total"
if ($copied -gt 0) {
    Write-Host ""
    Write-Host "Next: wait for Google Drive to upload, then for each file go to"
    Write-Host "  drive.google.com -> Public CNC Data\Examples\ -> right-click -> Share"
    Write-Host "  -> 'Anyone with the link, Viewer' -> Copy link"
    Write-Host "Paste link into examples\<slug>\meta.yaml under 'drive:'."
}
