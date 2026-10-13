$ErrorActionPreference = 'Stop'
$cRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\Models')).Path
$dRoot = 'D:\Available\Models'
$out = Join-Path $PSScriptRoot 'duplicates.csv'
$inventory = Join-Path $PSScriptRoot 'model-inventory.csv'
$chunk = 64MB
$fullLimit = 2GB

function Get-Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-SampleHashes([string]$Path, [int64]$Length) {
    $last = $Length - $chunk; if ($last -lt 0) { $last = 0 }
    $offsets = @([int64]0, [int64]$last)
    $mid = [int64]($Length / 2) - [int64]($chunk / 2); if ($mid -lt 0) { $mid = 0 }
    $offsets += $mid
    $m1 = [int64]($Length / 3) - [int64]($chunk / 2); if ($m1 -lt 0) { $m1 = 0 }
    $m2 = [int64](($Length * 2) / 3) - [int64]($chunk / 2); if ($m2 -lt 0) { $m2 = 0 }
    $offsets += $m1
    $offsets += $m2
    $offsets = $offsets | Sort-Object -Unique
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $result = foreach ($offset in $offsets) {
            $fs.Seek($offset, [System.IO.SeekOrigin]::Begin) | Out-Null
            $remaining = $Length - $offset
            $n64 = if ($remaining -lt $chunk) { $remaining } else { $chunk }
            $n = [int]$n64
            $buffer = New-Object byte[] $n
            $read = 0
            while ($read -lt $n) {
                $got = $fs.Read($buffer, $read, $n - $read)
                if ($got -le 0) { break }
                $read += $got
            }
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try { ($sha.ComputeHash($buffer, 0, $read) | ForEach-Object ToString x2) -join '' }
            finally { $sha.Dispose() }
        }
        $result -join ';'
    }
    finally { $fs.Dispose() }
}

function Get-RelativeFiles([string]$Root) {
    Get-ChildItem -LiteralPath $Root -File -Recurse -Force | ForEach-Object {
        $relative = $_.FullName.Substring($Root.Length).TrimStart('\\')
        [PSCustomObject]@{ Relative = $relative; FullName = $_.FullName; Length = $_.Length }
    }
}

$cFolders = @(Get-ChildItem -LiteralPath $cRoot -Directory -Force | Select-Object -ExpandProperty Name)
$dFolders = @(Get-ChildItem -LiteralPath $dRoot -Directory -Force | Select-Object -ExpandProperty Name)
$common = @($cFolders | Where-Object { $dFolders -contains $_ })
$inventoryRows = @()
foreach ($name in $cFolders) {
    $cPath = Join-Path $cRoot $name
    $dPath = Join-Path $dRoot $name
    $cBytes = (Get-ChildItem -LiteralPath $cPath -File -Recurse -Force | Measure-Object Length -Sum).Sum
    $dBytes = if (Test-Path -LiteralPath $dPath) { (Get-ChildItem -LiteralPath $dPath -File -Recurse -Force | Measure-Object Length -Sum).Sum } else { $null }
    $inventoryRows += [PSCustomObject]@{ Folder=$name; CBytes=$cBytes; DBytes=$dBytes; OnD=[bool](Test-Path -LiteralPath $dPath); COnly= -not (Test-Path -LiteralPath $dPath) }
}
$inventoryRows | Export-Csv -LiteralPath $inventory -NoTypeInformation

Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue
$rows = New-Object System.Collections.Generic.List[object]
foreach ($name in $common) {
    $cPath = Join-Path $cRoot $name
    $dPath = Join-Path $dRoot $name
    $cFiles = @(Get-RelativeFiles $cPath)
    $dFiles = @(Get-RelativeFiles $dPath)
    $dByRel = @{}
    foreach ($f in $dFiles) { $dByRel[$f.Relative] = $f }
    foreach ($cf in $cFiles) {
        $df = $dByRel[$cf.Relative]
        $verified = $false
        $how = 'missing-on-D'
        if ($null -ne $df) {
            if ($cf.Length -ne $df.Length) { $how = 'size-mismatch' }
            elseif ($cf.Length -lt $fullLimit) {
                $verified = (Get-Hash $cf.FullName) -eq (Get-Hash $df.FullName)
                $how = 'full-sha256'
            }
            else {
                $verified = (Get-SampleHashes $cf.FullName $cf.Length) -eq (Get-SampleHashes $df.FullName $df.Length)
                $how = 'sha256-first-last-3-middle-64MiB'
            }
        }
        $rows.Add([PSCustomObject]@{ Folder=$name; File=$cf.Relative; Size=$cf.Length; Verified=if($verified){'yes'}else{'no'}; How=$how })
        if (($rows.Count % 25) -eq 0) { Write-Output "checked=$($rows.Count) folder=$name file=$($cf.Relative)" }
    }
    foreach ($df in $dFiles | Where-Object { -not ($cFiles.Relative -contains $_.Relative) }) {
        $rows.Add([PSCustomObject]@{ Folder=$name; File=$df.Relative; Size=$df.Length; Verified='no'; How='extra-on-D' })
    }
}
$rows | Export-Csv -LiteralPath $out -NoTypeInformation
Write-Output "common-folders=$($common.Count) rows=$($rows.Count) output=$out inventory=$inventory"
