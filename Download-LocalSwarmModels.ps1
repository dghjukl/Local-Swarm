[CmdletBinding()]
param(
    [string]$Destination = 'C:\Users\Chris\Documents\GitHub\Local Swarm\Models',
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$models = @(
    [pscustomobject]@{ Name='Qwen3.5-4B'; Repo='bartowski/Qwen_Qwen3.5-4B-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='MiniCPM5-1B'; Repo='openbmb/MiniCPM5-1B-GGUF'; Vision=$false; ExactFile='MiniCPM5-1B-Q8_0.gguf' },
    [pscustomobject]@{ Name='MiniCPM5-2B'; Repo='prithivMLmods/MiniCPM5-2B-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='LFM2.5-2.6B'; Repo='LiquidAI/LFM2.5-2.6B-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='LFM2.5-8B-A1B'; Repo='LiquidAI/LFM2.5-8B-A1B-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='Ministral-3-3B-Instruct'; Repo='unsloth/Ministral-3-3B-Instruct-2512-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='Ministral-3-3B-Reasoning'; Repo='unsloth/Ministral-3-3B-Reasoning-2512-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='Granite-4.1-3B'; Repo='ibm-granite/granite-4.1-3b-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='Gemma-4-E2B-it'; Repo='unsloth/gemma-4-E2B-it-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='Gemma-4-E4B-it'; Repo='unsloth/gemma-4-E4B-it-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='Phi-4-mini-instruct'; Repo='unsloth/Phi-4-mini-instruct-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='NVIDIA-Nemotron-3-Nano-4B'; Repo='unsloth/NVIDIA-Nemotron-3-Nano-4B-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='SmolLM3-3B'; Repo='bartowski/HuggingFaceTB_SmolLM3-3B-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='Qwen3.5-9B'; Repo='bartowski/Qwen_Qwen3.5-9B-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='Granite-4.2-8B'; Repo='ibm-granite/granite-4.2-8b-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='Ministral-3-8B-Instruct'; Repo='unsloth/Ministral-3-8B-Instruct-2512-GGUF'; Vision=$true; ExactFile=$null },
    [pscustomobject]@{ Name='OLMo-2-7B-Instruct'; Repo='allenai/OLMo-2-1124-7B-Instruct-GGUF'; Vision=$false; ExactFile=$null },
    [pscustomobject]@{ Name='Ministral-3-14B-Instruct'; Repo='unsloth/Ministral-3-14B-Instruct-2512-GGUF'; Vision=$true; ExactFile=$null }
)

function Get-RepoFiles {
    param([Parameter(Mandatory)][string]$Repo)
    $headers = @{ 'User-Agent' = 'LocalSwarmModelDownloader/1.0' }
    $uri = "https://huggingface.co/api/models/${Repo}?expand[]=siblings"
    $metadata = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
    return @($metadata.siblings)
}

function Get-FileSize {
    param($Sibling)
    if ($null -ne $Sibling.lfs -and $null -ne $Sibling.lfs.size) { return [int64]$Sibling.lfs.size }
    if ($null -ne $Sibling.size) { return [int64]$Sibling.size }
    return [int64]0
}

function Select-FirstMatch {
    param(
        [Parameter(Mandatory)][array]$Files,
        [Parameter(Mandatory)][string[]]$Patterns,
        [string[]]$ExcludePatterns = @()
    )
    foreach ($pattern in $Patterns) {
        $matches = @($Files | Where-Object {
            $name = [string]$_.rfilename
            $included = $name -match $pattern
            $excluded = $false
            foreach ($exclude in $ExcludePatterns) {
                if ($name -match $exclude) { $excluded = $true; break }
            }
            $included -and -not $excluded
        } | Sort-Object { [string]$_.rfilename })
        if ($matches.Count -gt 0) { return $matches[0] }
    }
    return $null
}

function Select-ModelFile {
    param([Parameter(Mandatory)]$Model, [Parameter(Mandatory)][array]$Files)
    if ($Model.ExactFile) {
        return $Files | Where-Object { $_.rfilename -eq $Model.ExactFile } | Select-Object -First 1
    }
    $patterns = @(
        '(?i)(^|[-_.])Q5_K_M\.gguf$',
        '(?i)(^|[-_.])Q5_K_S\.gguf$',
        '(?i)(^|[-_.])Q5[^/]*\.gguf$',
        '(?i)(^|[-_.])Q6_K\.gguf$',
        '(?i)(^|[-_.])Q6[^/]*\.gguf$',
        '(?i)(^|[-_.])Q8_0\.gguf$'
    )
    return Select-FirstMatch -Files $Files -Patterns $patterns -ExcludePatterns @('(?i)mmproj','(?i)imatrix','(?i)(^|[-_.])MTP')
}

function Select-ProjectorFile {
    param([Parameter(Mandatory)][array]$Files)
    $patterns = @(
        '(?i)mmproj.*BF16.*\.gguf$',
        '(?i)mmproj.*Q8_0.*\.gguf$',
        '(?i)mmproj.*F16.*\.gguf$',
        '(?i)mmproj.*F32.*\.gguf$',
        '(?i)mmproj.*\.gguf$'
    )
    return Select-FirstMatch -Files $Files -Patterns $patterns
}

function Get-DownloadUrl {
    param([Parameter(Mandatory)][string]$Repo, [Parameter(Mandatory)][string]$FileName)
    $segments = $FileName -split '/' | ForEach-Object { [uri]::EscapeDataString($_) }
    $encodedPath = $segments -join '/'
    return "https://huggingface.co/${Repo}/resolve/main/${encodedPath}?download=true"
}

function Save-HuggingFaceFile {
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$FileName,
        [Parameter(Mandatory)][string]$Folder,
        [int64]$ExpectedBytes = 0
    )
    $finalPath = Join-Path $Folder ([IO.Path]::GetFileName($FileName))
    $partialPath = "$finalPath.partial"
    if (Test-Path -LiteralPath $finalPath) {
        $length = (Get-Item -LiteralPath $finalPath).Length
        if (($ExpectedBytes -eq 0 -and $length -gt 0) -or ($ExpectedBytes -gt 0 -and $length -eq $ExpectedBytes)) {
            Write-Host "Already complete: $finalPath" -ForegroundColor DarkGreen
            return $finalPath
        }
        Move-Item -LiteralPath $finalPath -Destination $partialPath -Force
    }

    $url = Get-DownloadUrl -Repo $Repo -FileName $FileName
    $started = Get-Date
    Write-Host "[$($started.ToString('yyyy-MM-dd HH:mm:ss'))] Downloading $Repo / $FileName" -ForegroundColor Cyan
    Write-Host 'Live progress appears below. A transfer below 1 KB/s for 120 seconds is treated as stalled and retried.' -ForegroundColor DarkGray
    $curlArgs = @(
        '--fail', '--location', '--show-error', '--progress-bar',
        '--retry', '8', '--retry-connrefused', '--retry-delay', '5',
        '--speed-limit', '1024', '--speed-time', '120',
        '--continue-at', '-', '--output', $partialPath, $url
    )
    & curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) { throw "curl.exe failed with exit code $LASTEXITCODE" }

    $actualBytes = (Get-Item -LiteralPath $partialPath).Length
    if ($ExpectedBytes -gt 0 -and $actualBytes -ne $ExpectedBytes) {
        throw "Size check failed for $FileName. Expected $ExpectedBytes bytes; received $actualBytes bytes."
    }
    if ($actualBytes -le 0) { throw "Downloaded file is empty: $FileName" }
    Move-Item -LiteralPath $partialPath -Destination $finalPath -Force
    $elapsed = (Get-Date) - $started
    Write-Host ('Completed {0} in {1:hh\:mm\:ss} ({2:N2} GB).' -f $FileName, $elapsed, ($actualBytes / 1GB)) -ForegroundColor Green
    return $finalPath
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$manifestPath = Join-Path $Destination 'model-download-manifest.csv'
$results = [System.Collections.Generic.List[object]]::new()
$failures = [System.Collections.Generic.List[string]]::new()

$modelNumber = 0
foreach ($model in $models) {
    $modelNumber++
    Write-Host "`n[$modelNumber/$($models.Count)] Resolving $($model.Name) at $((Get-Date).ToString('HH:mm:ss'))" -ForegroundColor Yellow
    try {
        $files = Get-RepoFiles -Repo $model.Repo
        $modelFile = Select-ModelFile -Model $model -Files $files
        if ($null -eq $modelFile) { throw 'No allowed Q5, Q6, or Q8 model file was found.' }
        $selected = [System.Collections.Generic.List[object]]::new()
        $selected.Add([pscustomobject]@{ Kind='model'; Item=$modelFile })

        if ($model.Vision) {
            $projector = Select-ProjectorFile -Files $files
            if ($null -eq $projector) { throw 'This is a vision model, but no compatible mmproj file was found.' }
            $selected.Add([pscustomobject]@{ Kind='mmproj'; Item=$projector })
        }

        $folder = Join-Path $Destination $model.Name
        New-Item -ItemType Directory -Path $folder -Force | Out-Null

        foreach ($selection in $selected) {
            $fileName = [string]$selection.Item.rfilename
            $expected = Get-FileSize -Sibling $selection.Item
            $sizeText = if ($expected -gt 0) { '{0:N2} GB' -f ($expected / 1GB) } else { 'size unavailable' }
            Write-Host "Selected [$($selection.Kind)] $fileName ($sizeText)" -ForegroundColor White
            $status = if ($PlanOnly) { 'planned' } else { 'downloaded' }
            $localPath = Join-Path $folder ([IO.Path]::GetFileName($fileName))
            if (-not $PlanOnly) {
                $localPath = Save-HuggingFaceFile -Repo $model.Repo -FileName $fileName -Folder $folder -ExpectedBytes $expected
            }
            $results.Add([pscustomobject]@{
                model_name = $model.Name
                repository = $model.Repo
                kind = $selection.Kind
                file_name = $fileName
                quantization = if ($selection.Kind -eq 'model') { ([regex]::Match($fileName, '(?i)(Q[568][A-Z0-9_]*)(?=\.gguf$)')).Value } else { 'projector' }
                expected_bytes = $expected
                local_path = $localPath
                status = $status
                recorded_utc = [DateTime]::UtcNow.ToString('o')
            })
        }
    }
    catch {
        $message = "$($model.Name): $($_.Exception.Message)"
        $failures.Add($message)
        Write-Warning $message
    }
    Write-Host "Finished model $modelNumber of $($models.Count) at $((Get-Date).ToString('HH:mm:ss'))." -ForegroundColor DarkCyan
}

$results | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8
$totalBytes = ($results | Measure-Object -Property expected_bytes -Sum).Sum
Write-Host "`nManifest: $manifestPath" -ForegroundColor Green
if ($totalBytes -gt 0) { Write-Host ('Selected download size: {0:N2} GB' -f ($totalBytes / 1GB)) -ForegroundColor Green }

if ($failures.Count -gt 0) {
    Write-Host "`nThe following models need attention:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

if ($PlanOnly) {
    Write-Host "`nPlan complete. Run again without -PlanOnly to download." -ForegroundColor Green
} else {
    Write-Host "`nAll selected models and projectors downloaded successfully." -ForegroundColor Green
}
