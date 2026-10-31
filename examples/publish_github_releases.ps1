# ==============================================================================
# Manual Release Upload Helper — NOUinnsikt Open Raw-Data Archive
# ==============================================================================
# Run ONLY when you are ready to create the public GitHub Releases and upload
# the >100 MB bulk archives generated in `release-staging/`.
#
# Prerequisite steps from the parent NOU-guru workspace:
#   ..\.venv\Scripts\python.exe ..\pipeline\export_open_archive.py --release-markdown --release-chunks --release-sqlite --release-podcasts --release-covers --audit
# ==============================================================================

param(
    [string]$Repo = "tordieltor/nouinnsikt-open-data"
)

$ErrorActionPreference = "Stop"
$StagingDir = Join-Path $PSScriptRoot "..\release-staging"

if (-not (Test-Path $StagingDir)) {
    Write-Error "release-staging directory not found at $StagingDir. Run export_open_archive.py --release-* first."
}

Write-Host "Creating GitHub Release v1.0.0-data on $Repo ..."
$AllowedExtensions = @(".xz", ".gz", ".npz", ".tar")
$DataAssets = Get-ChildItem -Path $StagingDir -File | Where-Object { ($AllowedExtensions -contains $_.Extension) -and ($_.Length -lt 2100000000) }
if ($DataAssets.Count -gt 0) {
    $AssetPaths = $DataAssets | ForEach-Object { $_.FullName }
    gh release create "v1.0.0-data" @AssetPaths `
        --repo $Repo `
        --title "NOUinnsikt Open Raw-Data Archive v1.0.0 (Fulltext, SQLite FTS5 & Embeddings)" `
        --notes "Complete bulk fulltext Markdown reports (1,741 NOUs), 653,941 semantic text chunks, portable SQLite FTS5 database, and 768-dimensional vector embeddings (1972-2026). Licensed under NLOD 2.0 / CC BY 4.0."
}
