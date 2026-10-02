# Clean-C-Models: free space on C: by moving stray model files (.gguf) to D:
#
#   1. Finds every .gguf on C: that is NOT in this repo (and not in Windows / Program Files).
#   2. Checks whether D: already has it (same file name and same size, anywhere on D:).
#   3. Shows the list grouped by folder, with sizes, and asks before doing anything.
#   4. On Y: copies the ones D: does not have to D:\Available\Models\FromC\<original path>,
#      checks the copy is complete (same size), and only then deletes the file from C:.
#
# Nothing is deleted unless a complete copy exists on D:. A report is written to
# runtime\clean-c-models-<time>.csv either way.
#
#   Clean-C-Models.bat          scan, show, ask, then copy + delete
#   Clean-C-Models.bat check    scan and show only
param([string]$Mode = 'all')
$ErrorActionPreference = 'Stop'

$Repo    = Split-Path -Parent $PSScriptRoot
$DestRoot = 'D:\Available\Models\FromC'
$Skip = @('C:\Windows', 'C:\Program Files', 'C:\Program Files (x86)', 'C:\ProgramData\Microsoft',
          'C:\$Recycle.Bin', 'C:\System Volume Information', $Repo)

function GB($b) { '{0,7:N1} GB' -f ($b / 1GB) }
function Skipped($path) { foreach ($s in $Skip) { if ($path.StartsWith($s + '\', 'OrdinalIgnoreCase')) { return $true } }; return $false }

if (-not (Test-Path 'D:\')) { Write-Host "Can't find the D: drive." -ForegroundColor Red; exit 1 }

Write-Host 'Searching C: for .gguf files (a few minutes) ...'
$found = @()
Get-ChildItem -LiteralPath 'C:\' -Directory -Force -ErrorAction SilentlyContinue | Where-Object { -not (Skipped ($_.FullName + '\x')) -and -not ($Skip -contains $_.FullName) } | ForEach-Object {
    Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force -Filter *.gguf -ErrorAction SilentlyContinue
} | ForEach-Object {
    if (Skipped $_.FullName) { return }
    # Hugging Face / tool caches keep .gguf names as links to blobs: deleting a link frees nothing
    if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { return }
    $found += $_
}

Write-Host 'Indexing the model files already on D: ...'
$onD = @{}
Get-ChildItem -LiteralPath 'D:\' -Recurse -File -Force -Filter *.gguf -ErrorAction SilentlyContinue |
    ForEach-Object { $onD["$($_.Name.ToLower())|$($_.Length)"] = $_.FullName }

$rows = foreach ($f in $found) {
    $key = "$($f.Name.ToLower())|$($f.Length)"
    [pscustomobject]@{
        Path    = $f.FullName
        Folder  = $f.DirectoryName
        Bytes   = $f.Length
        OnD     = $onD.ContainsKey($key)
        DCopy   = $(if ($onD.ContainsKey($key)) { $onD[$key] } else { Join-Path $DestRoot $f.FullName.Substring(3) })
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'runtime') | Out-Null
$report = Join-Path $Repo "runtime\clean-c-models-$stamp.csv"
$rows | Export-Csv -NoTypeInformation -LiteralPath $report

# other big model stores that are not plain .gguf files (shown only; use the app itself to clean them)
$extra = @()
foreach ($p in @("$env:USERPROFILE\.ollama\models", "$env:USERPROFILE\.cache\huggingface", "$env:LOCALAPPDATA\nomic.ai",
                 "$env:USERPROFILE\.cache\lm-studio", "$env:USERPROFILE\AppData\Local\llama.cpp")) {
    if (Test-Path -LiteralPath $p) {
        $sz = (Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        if ($sz -gt 500MB) { $extra += [pscustomobject]@{ Path = $p; Bytes = $sz } }
    }
}

Write-Host ''
Write-Host '=== .gguf files on C: outside the Local Swarm repo ===' -ForegroundColor Cyan
if (-not $rows) { Write-Host '   none found' }
$rows | Group-Object Folder | Sort-Object { -($_.Group | Measure-Object Bytes -Sum).Sum } | ForEach-Object {
    $sum = ($_.Group | Measure-Object Bytes -Sum).Sum
    $already = ($_.Group | Where-Object OnD).Count
    Write-Host ("{0}  {1,3} files  ({2} already on D:)  {3}" -f (GB $sum), $_.Count, $already, $_.Name)
}
$total   = ($rows | Measure-Object Bytes -Sum).Sum
$toCopy  = ($rows | Where-Object { -not $_.OnD } | Measure-Object Bytes -Sum).Sum
$dupes   = ($rows | Where-Object OnD | Measure-Object Bytes -Sum).Sum
Write-Host ''
Write-Host ("Total on C: {0} in {1} files" -f (GB $total), @($rows).Count) -ForegroundColor Green
Write-Host ("  already on D: (just delete from C:):  {0}" -f (GB $dupes))
Write-Host ("  not on D: yet (copy, then delete):     {0}" -f (GB $toCopy))
if ($extra) {
    Write-Host ''
    Write-Host 'Other model stores on C: (not touched by this script; clean them from the app):' -ForegroundColor Yellow
    $extra | ForEach-Object { Write-Host ("{0}  {1}" -f (GB $_.Bytes), $_.Path) }
}
$freeC = (Get-PSDrive C).Free; $freeD = (Get-PSDrive D).Free
Write-Host ''
Write-Host ("C: free now {0}   ->  about {1} after cleanup" -f (GB $freeC), (GB ($freeC + $total)))
Write-Host ("D: free now {0}   ->  {1} after copying" -f (GB $freeD), (GB ($freeD - $toCopy)))
Write-Host "Full list: $report"

if ($Mode -eq 'check' -or -not $rows) { exit 0 }
if ($freeD - $toCopy -lt 20GB) { Write-Host 'Not enough room on D: - stopping.' -ForegroundColor Red; exit 2 }
Write-Host ''
Write-Host 'Look over the folders above. Anything another program still needs from C: (for example'
Write-Host 'LM Studio or another project) will have to be pointed at the copy on D: afterwards.'
if ((Read-Host 'Copy what D: lacks to D:, then delete ALL of these from C:? (Y/N)') -notmatch '^[Yy]') { Write-Host 'Nothing done.'; exit 0 }

$freed = 0; $failed = 0
foreach ($r in $rows) {
    try {
        if (-not $r.OnD) {
            $dir = Split-Path $r.DCopy -Parent
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            robocopy (Split-Path $r.Path -Parent) $dir (Split-Path $r.Path -Leaf) /J /R:2 /W:5 /NJH /NJS /NDL /NP | Out-Null
            if ($LASTEXITCODE -ge 8) { throw 'copy failed' }
        }
        # the safety check: a complete copy must exist on D: before C: loses the file
        if (-not (Test-Path -LiteralPath $r.DCopy) -or (Get-Item -LiteralPath $r.DCopy).Length -ne $r.Bytes) {
            throw "no complete copy on D: ($($r.DCopy))"
        }
        Remove-Item -LiteralPath $r.Path -Force
        $freed += $r.Bytes
        Write-Host ("  moved  {0}  {1}" -f (GB $r.Bytes), $r.Path)
    } catch {
        $failed++
        Write-Host ("  KEPT   {0}  {1}  ({2})" -f (GB $r.Bytes), $r.Path, $_.Exception.Message) -ForegroundColor Yellow
    }
}
Write-Host ''
Write-Host ("Done. Freed {0} on C:. {1} file(s) kept on C: (see above)." -f (GB $freed), $failed) -ForegroundColor Green
Write-Host ("C: free now {0}" -f (GB (Get-PSDrive C).Free))
