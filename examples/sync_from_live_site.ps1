# ==============================================================================
# Live-Site -> Open-Data Archive Synchronization Loop
# ==============================================================================
# Keeps `open-data-repo/` (https://github.com/tordieltor/nouinnsikt-open-data)
# continuously synchronized with the live NOUinnsikt Supabase database,
# curated JSON catalogs, and reusable pipeline scripts.
#
# Usage:
#   1. Run a single sync + forensic audit + git push:
#      .\examples\sync_from_live_site.ps1
#
#   2. Run a continuous background watch loop (e.g. every 60 minutes):
#      .\examples\sync_from_live_site.ps1 -Watch -IntervalMinutes 60
#
#   3. Also rebuild & upload >100 MB GitHub Release bundles when chunks change:
#      .\examples\sync_from_live_site.ps1 -IncludeReleases
# ==============================================================================

param(
    [switch]$Watch,
    [int]$IntervalMinutes = 60,
    [switch]$IncludeReleases,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$WorkspaceRoot = Resolve-Path (Join-Path $RepoRoot "..")
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$ExporterScript = Join-Path $WorkspaceRoot "pipeline\export_open_archive.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtualenv Python not found at $PythonExe"
}

$ArgsList = @($ExporterScript, "--repo-dir", $RepoRoot, "--sync")
if (-not $NoPush) {
    $ArgsList += "--push"
}
if ($IncludeReleases) {
    $ArgsList += "--sync-releases"
}
if ($Watch) {
    $ArgsList += @("--watch", "--interval-minutes", "$IntervalMinutes")
}

Write-Host "[NOUinnsikt Sync] Executing: $PythonExe $($ArgsList -join ' ')"
& $PythonExe @ArgsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
