# Sync-Models: get the big "opponent" models ready for the heavyweight comparison.
#
#   1. DOWNLOAD  models you don't have anywhere        -> D:\Available\Models\<name>\
#   2. BACKUP    models that are only in the repo      -> D:\Available\Models\LocalSwarm-backup\<name>\
#   3. TO REPO   models from D that the tests need     -> <repo>\Models\<name>\
#
# Nothing is deleted or moved; files that are already in place (same name and size) are skipped.
# Before doing anything it adds up the sizes, checks free space on C: and D:, shows the plan
# and asks for Y.
#
#   Sync-Models.bat            plan, ask, then do everything
#   Sync-Models.bat check      only show the plan and the space check
#   Sync-Models.bat download   only step 1 (safe to run while an evaluation is running)
param([string]$Mode = 'all')
$ErrorActionPreference = 'Stop'

$Repo       = Split-Path -Parent $PSScriptRoot
$RepoModels = Join-Path $Repo 'Models'
$D          = 'D:\Available\Models'
$Backup     = Join-Path $D 'LocalSwarm-backup'
$ReserveC   = 25GB   # keep at least this much free on C: afterwards (Windows, runs, caches)
$ReserveD   = 10GB

# ---------------------------------------------------------------- what we want
# Downloads (Hugging Face direct links). Optional ones are only fetched if you say yes.
$Downloads = @(
    @{ Name = 'Qwen3.6-27B'; File = 'Qwen3.6-27B-Q4_K_M.gguf'; Size = 16817244384; Optional = $false
       Why  = 'big DENSE model, split between graphics card and RAM'
       Url  = 'https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/main/Qwen3.6-27B-Q4_K_M.gguf' },
    @{ Name = 'Gemma-4-31B-it'; File = 'gemma-4-31B_q4_0-it.gguf'; Size = 17651001568; Optional = $true
       Why  = "second big dense model (Google's official 4-bit)"
       Url  = 'https://huggingface.co/google/gemma-4-31B-it-qat-q4_0-gguf/resolve/main/gemma-4-31B_q4_0-it.gguf' },
    # coordinator bake-off: candidates that fit ENTIRELY on the graphics card (no RAM spill)
    @{ Name = 'Gemma-4-12B-it'; File = 'gemma-4-12b-it-qat-q4_0.gguf'; Size = 6975879296; Optional = $false
       Why  = "coordinator candidate: Google's 12B, official 4-bit"
       Url  = 'https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/main/gemma-4-12b-it-qat-q4_0.gguf' },
    @{ Name = 'Qwen3.8-27B'; File = 'Qwen3.8-27B-UD-IQ3_XXS.gguf'; Size = 10934860704; Optional = $false
       Why  = 'coordinator candidate: newest Qwen 27B, 3-bit so it fits on the card'
       Url  = 'https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-IQ3_XXS.gguf' },
    @{ Name = 'Bonsai-2-27B'; File = 'Ternary-Bonsai-2-27B-PQ2_0.gguf'; Size = 7206168928; Optional = $false
       Why  = 'coordinator candidate: Qwen3.8-27B in ternary weights (needs the PrismML llama.cpp, fetched below)'
       Url  = 'https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf/resolve/main/Ternary-Bonsai-2-27B-PQ2_0.gguf' },
    # round 2 (2026-09-29): verifier, reranker and worker candidates, incl. second-tier labs;
    # the optional ones are the bake-off round 2 coordinators (about 37 GB together)
    @{ Name = 'Granite-4.2-3B'; File = 'granite-4.2-3b-Q5_K_M.gguf'; Size = 2613634592; Optional = $false
       Why  = 'IBM: upgrade of the verifier/skeptic Granite-4.1-3B'
       Url  = 'https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF/resolve/main/granite-4.2-3b-Q5_K_M.gguf' },
    @{ Name = 'Granite-Guardian-4.1-8B'; File = 'granite-guardian-4.1-8b-Q5_K_M.gguf'; Size = 5971293248; Optional = $false
       Why  = 'IBM: built to judge whether a text is supported by documents (verifier)'
       Url  = 'https://huggingface.co/ibm-granite/granite-guardian-4.1-8b-GGUF/resolve/main/granite-guardian-4.1-8b-Q5_K_M.gguf' },
    @{ Name = 'Qwen3-Reranker-4B'; File = 'Qwen3-Reranker-4B-Q4_K_M.gguf'; Size = 2496717440; Optional = $false
       Why  = 'Qwen: picks the most relevant passages (a llama.cpp-ready conversion)'
       Url  = 'https://huggingface.co/Voodisss/Qwen3-Reranker-4B-GGUF-llama_cpp/resolve/main/Qwen3-Reranker-4B-Q4_K_M.gguf' },
    @{ Name = 'Olmo-3-7B-Instruct'; File = 'Olmo-3-7B-Instruct-Q5_K_M.gguf'; Size = 5208713088; Optional = $false
       Why  = 'Ai2: worker candidate (replaces OLMo-2)'
       Url  = 'https://huggingface.co/unsloth/Olmo-3-7B-Instruct-GGUF/resolve/main/Olmo-3-7B-Instruct-Q5_K_M.gguf' },
    @{ Name = 'NVIDIA-Nemotron-Nano-9B-v2'; File = 'nvidia_NVIDIA-Nemotron-Nano-9B-v2-Q5_K_M.gguf'; Size = 7069805920; Optional = $false
       Why  = 'NVIDIA: worker candidate'
       Url  = 'https://huggingface.co/bartowski/nvidia_NVIDIA-Nemotron-Nano-9B-v2-GGUF/resolve/main/nvidia_NVIDIA-Nemotron-Nano-9B-v2-Q5_K_M.gguf' },
    @{ Name = 'Falcon-H1R-7B'; File = 'Falcon-H1R-7B-Q5_K_M.gguf'; Size = 5390489632; Optional = $false
       Why  = 'TII: reasoning-tuned worker candidate'
       Url  = 'https://huggingface.co/tiiuae/Falcon-H1R-7B-GGUF/resolve/main/Falcon-H1R-7B-Q5_K_M.gguf' },
    @{ Name = 'MiMo-V2.6-Distill-Qwen-9B'; File = 'MiMo-V2.6-Distill-Qwen-9B-Q5_K_M.gguf'; Size = 6876124704; Optional = $false
       Why  = 'Xiaomi: worker / coordinator candidate'
       Url  = 'https://huggingface.co/bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF/resolve/main/MiMo-V2.6-Distill-Qwen-9B-Q5_K_M.gguf' },
    # expert-worker candidates (2026-10-05): stronger models MiMo can hand a stuck step to; Q5 or better
    @{ Name = 'Gemma-4-12B-it-Q5'; File = 'gemma-4-12b-it-Q5_K_M.gguf'; Size = 8413576000; Optional = $false
       Why  = "expert worker: Google's Gemma-4-12B instruct at Q5 (the QAT 4-bit copy stays too)"
       Url  = 'https://huggingface.co/unsloth/gemma-4-12b-it-GGUF/resolve/main/gemma-4-12b-it-Q5_K_M.gguf' },
    @{ Name = 'Ornith-1.5-9B'; File = 'Ornith-1.5-9B-Q5_K_M.gguf'; Size = 6642544576; Optional = $false
       Why  = 'expert worker: Ornith AI 9B trained as a research/search agent (Aug 2026)'
       Url  = 'https://huggingface.co/ornith-ai/Ornith-1.5-9B-GGUF/resolve/main/Ornith-1.5-9B-Q5_K_M.gguf' },
    # distillation teachers (2026-10-05): run ALONE, split between graphics card and RAM (slow is fine)
    @{ Name = 'Qwen3.8-27B-Q5'; File = 'Qwen3.8-27B-UD-Q5_K_M.gguf'; Size = 19771509664; Optional = $false
       Why  = 'teacher candidate: newest Qwen 27B at Q5 (the 3-bit copy stays for the old bake-off)'
       Url  = 'https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q5_K_M.gguf' },
    @{ Name = 'Trinity-Mini'; File = 'arcee-ai_Trinity-Mini-Q5_K_M.gguf'; Size = 18637071200; Optional = $true
       Why  = 'teacher candidate: Arcee 26B MoE (3B active), an independent lineage'
       Url  = 'https://huggingface.co/bartowski/arcee-ai_Trinity-Mini-GGUF/resolve/main/arcee-ai_Trinity-Mini-Q5_K_M.gguf' },
    @{ Name = 'Kanana-2-3B-Instruct'; File = 'kanana-2-3b-instruct.Q5_K_M.gguf'; Size = 2512165760; Optional = $false
       Why  = 'Kakao: small worker candidate'
       Url  = 'https://huggingface.co/mradermacher/kanana-2-3b-instruct-GGUF/resolve/main/kanana-2-3b-instruct.Q5_K_M.gguf' },
    @{ Name = 'Jamba2-3B'; File = 'ai21labs_AI21-Jamba2-3B-Q5_K_M.gguf'; Size = 2272889728; Optional = $false
       Why  = 'AI21: small hybrid worker candidate'
       Url  = 'https://huggingface.co/bartowski/ai21labs_AI21-Jamba2-3B-GGUF/resolve/main/ai21labs_AI21-Jamba2-3B-Q5_K_M.gguf' },
    @{ Name = 'Apertus-v1.5-8B'; File = 'apertus-v1.5-8b-text-q4_k_m.gguf'; Size = 5059027136; Optional = $false
       Why  = 'Swiss AI: worker candidate (community 4-bit)'
       Url  = 'https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/resolve/main/apertus-v1.5-8b-text-q4_k_m.gguf' },
    @{ Name = 'rnj-1.5-Instruct'; File = 'rnj-1.5-instruct-q4_k_m.gguf'; Size = 5113915040; Optional = $false
       Why  = 'Essential AI: worker candidate (community 4-bit)'
       Url  = 'https://huggingface.co/pszemraj/rnj-1.5-instruct-GGUF/resolve/main/rnj-1.5-instruct-q4_k_m.gguf' },
    # round 3 (2026-10-01): labs from Codex's lab catalog whose lineages we did not have yet
    @{ Name = 'Llama-3.1-8B-Instruct'; File = 'Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf'; Size = 5732992416; Optional = $false
       Why  = 'Meta: first Llama-lineage worker candidate'
       Url  = 'https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf' },
    @{ Name = 'Llama-3.2-3B-Instruct'; File = 'Llama-3.2-3B-Instruct-Q6_K_L.gguf'; Size = 2739276320; Optional = $false
       Why  = 'Meta: small Llama worker candidate'
       Url  = 'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q6_K_L.gguf' },
    @{ Name = 'Command-R7B'; File = 'c4ai-command-r7b-12-2024-Q5_K_M.gguf'; Size = 5803595904; Optional = $false
       Why  = 'Cohere: trained for grounded answers with citations'
       Url  = 'https://huggingface.co/bartowski/c4ai-command-r7b-12-2024-GGUF/resolve/main/c4ai-command-r7b-12-2024-Q5_K_M.gguf' },
    @{ Name = 'AFM-4.5B'; File = 'arcee-ai_AFM-4.5B-Q6_K.gguf'; Size = 3797600512; Optional = $false
       Why  = 'Arcee AI: own-pretraining 4.5B worker candidate'
       Url  = 'https://huggingface.co/bartowski/arcee-ai_AFM-4.5B-GGUF/resolve/main/arcee-ai_AFM-4.5B-Q6_K.gguf' },
    @{ Name = 'EXAONE-4.0-1.2B'; File = 'EXAONE-4.0-1.2B-Q8_0.gguf'; Size = 1363939616; Optional = $false
       Why  = 'LG AI Research: tiny worker candidate (official GGUF)'
       Url  = 'https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF/resolve/main/EXAONE-4.0-1.2B-Q8_0.gguf' },
    @{ Name = 'GLM-4-9B-0414'; File = 'THUDM_GLM-4-9B-0414-Q5_K_M.gguf'; Size = 7050917248; Optional = $false
       Why  = 'Zhipu / Z.ai: GLM-lineage worker candidate'
       Url  = 'https://huggingface.co/bartowski/THUDM_GLM-4-9B-0414-GGUF/resolve/main/THUDM_GLM-4-9B-0414-Q5_K_M.gguf' },
    @{ Name = 'HyperCLOVAX-SEED-Think-14B'; File = 'HyperCLOVAX-SEED-Think-14B-Q4_K_M.gguf'; Size = 8916242240; Optional = $true
       Why  = 'NAVER: coordinator candidate (bake-off round 2)'
       Url  = 'https://huggingface.co/naver-ellm/HyperCLOVAX-SEED-Think-14B-GGUF/resolve/main/HyperCLOVAX-SEED-Think-14B-Q4_K_M.gguf' },
    @{ Name = 'Apriel-1.6-15B-Thinker'; File = 'Apriel-1.6-15b-Thinker-Q4_K_M.gguf'; Size = 8785478848; Optional = $true
       Why  = 'ServiceNow: coordinator candidate (bake-off round 2)'
       Url  = 'https://huggingface.co/ServiceNow-AI/Apriel-1.6-15b-Thinker-GGUF/resolve/main/Apriel-1.6-15b-Thinker-Q4_K_M.gguf' },
    @{ Name = 'Phi-4-reasoning-vision-15B'; File = 'microsoft.Phi-4-reasoning-vision-15B.f16.gguf.Q4_K_M.gguf'; Size = 9053117056; Optional = $true
       Why  = 'Microsoft: coordinator candidate (bake-off round 2)'
       Url  = 'https://huggingface.co/DevQuasar/microsoft.Phi-4-reasoning-vision-15B-GGUF/resolve/main/microsoft.Phi-4-reasoning-vision-15B.f16.gguf.Q4_K_M.gguf' },
    @{ Name = 'ERNIE-4.5-21B-A3B-Thinking'; File = 'ERNIE-4.5-21B-A3B-Thinking-Q3_K_M.gguf'; Size = 10524818304; Optional = $true
       Why  = 'Baidu: MoE coordinator candidate, 3-bit to fit on the card (bake-off round 2)'
       Url  = 'https://huggingface.co/unsloth/ERNIE-4.5-21B-A3B-Thinking-GGUF/resolve/main/ERNIE-4.5-21B-A3B-Thinking-Q3_K_M.gguf' }
)
# Extra llama.cpp builds some models need (unzipped into Bin\<Dest>). Bonsai's ternary weights only
# run on the PrismML fork; stock llama.cpp produces gibberish with them.
$ToolZips = @(
    @{ Dest = 'llama-prism'; File = 'llama-prism-b10709-9a9394a-bin-win-cuda-13.3-x64.zip'; Size = 145031500
       Url  = 'https://github.com/PrismML-Eng/llama.cpp/releases/download/prism-b10709-9a9394a/llama-prism-b10709-9a9394a-bin-win-cuda-13.3-x64.zip' },
    @{ Dest = 'llama-prism'; File = 'cudart-llama-bin-win-cuda-13.3-x64.zip'; Size = 390970417
       Url  = 'https://github.com/PrismML-Eng/llama.cpp/releases/download/prism-b10709-9a9394a/cudart-llama-bin-win-cuda-13.3-x64.zip' }
)
# Models already on D: that the heavyweight tests need in the repo (folder name = model id).
$ToRepo = @(
    @{ Name = 'gpt-oss-20b';                  Src = "$D\gpt-oss-20b\gpt-oss-20b-Q5_K_M.gguf" },
    @{ Name = 'Qwen3-14B';                    Src = "$D\Qwen\Qwen3-14B-Q6_K.gguf" },
    @{ Name = 'DeepSeek-R1-Distill-Qwen-14B'; Src = "$D\Qwen\DeepSeek-R1-Distill-Qwen-14B-Q5_K_M.gguf" },
    @{ Name = 'Gemma-4-26B-A4B-it';           Src = "$D\reasoning\gemma-4-26B-A4B-it\gemma-4-26B-A4B-it-UD-Q5_K_M.gguf" },
    @{ Name = 'Qwen3.6-35B-A3B';              Src = "$D\Qwen3.6-35B-A3B\Qwen3.6-35B-A3B-UD-Q5_K_M.gguf" }
)
# downloaded models also go into the repo
foreach ($dl in $Downloads) {
    $ToRepo += @{ Name = $dl.Name; Src = (Join-Path (Join-Path $D $dl.Name) $dl.File); Optional = $dl.Optional; FromDownload = $true }
}

function GB($b) { '{0,6:N1} GB' -f ($b / 1GB) }
function Free($drive) { (Get-PSDrive $drive).Free }
function SameFile($path, $size) { (Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Length -eq $size) }

if (-not (Test-Path $D)) { Write-Host "Can't find $D - is the D: drive connected?" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- optional choices
$wantOptional = $false
if ($Mode -ne 'check' -and ($Downloads | Where-Object { $_.Optional })) {
    foreach ($dl in $Downloads | Where-Object { $_.Optional }) {
        Write-Host ("Optional: {0} ({1}) - {2}" -f $dl.Name, (GB $dl.Size).Trim(), $dl.Why)
    }
    $wantOptional = (Read-Host 'Include the optional model(s)? (Y/N)') -match '^[Yy]'
}
function Wanted($item) { -not $item.Optional -or $wantOptional }

# ---------------------------------------------------------------- 1. downloads
$planDl = @()
foreach ($dl in $Downloads) {
    if (-not (Wanted $dl)) { continue }
    $dest = Join-Path (Join-Path $D $dl.Name) $dl.File
    if (SameFile $dest $dl.Size) { continue }
    $have = if (Test-Path -LiteralPath $dest) { (Get-Item -LiteralPath $dest).Length } else { 0 }  # resume a partial file
    $planDl += [pscustomobject]@{ Item = $dl; Dest = $dest; Need = $dl.Size - $have }
}

# ---------------------------------------------------------------- 2. backups (repo -> D)
Write-Host 'Indexing the model files on D: ...'
$onD = @{}
Get-ChildItem -LiteralPath $D -Recurse -File -Filter *.gguf -ErrorAction SilentlyContinue |
    ForEach-Object { $onD["$($_.Name.ToLower())|$($_.Length)"] = $_.FullName }
$planBackup = @()
if (Test-Path $RepoModels) {
    Get-ChildItem -LiteralPath $RepoModels -Recurse -File -Filter *.gguf | ForEach-Object {
        if (-not $onD.ContainsKey("$($_.Name.ToLower())|$($_.Length)")) {
            $folder = $_.Directory.Name
            $planBackup += [pscustomobject]@{ Src = $_.FullName; Dest = (Join-Path (Join-Path $Backup $folder) $_.Name); Need = $_.Length }
        }
    }
}

# ---------------------------------------------------------------- 3. D -> repo
$planRepo = @()
foreach ($m in $ToRepo) {
    if (-not (Wanted $m)) { continue }
    $dest = Join-Path (Join-Path $RepoModels $m.Name) (Split-Path $m.Src -Leaf)
    if ($m.FromDownload) {
        $size = ($Downloads | Where-Object { $_.Name -eq $m.Name }).Size
    } elseif (Test-Path -LiteralPath $m.Src) {
        $size = (Get-Item -LiteralPath $m.Src).Length
    } else {
        Write-Host "  missing on D: $($m.Src) - skipped" -ForegroundColor Yellow; continue
    }
    if (SameFile $dest $size) { continue }
    $planRepo += [pscustomobject]@{ Name = $m.Name; Src = $m.Src; Dest = $dest; Need = $size }
}

# ---------------------------------------------------------------- 4. extra llama.cpp builds
$ToolDir = Join-Path $D 'LocalSwarm-tools'
$planTools = @()
foreach ($t in $ToolZips) {
    $binDir = Join-Path (Join-Path $Repo 'Bin') $t.Dest
    $zip = Join-Path $ToolDir $t.File
    $done = Join-Path $binDir ('.unzipped-' + $t.File)
    if (Test-Path -LiteralPath $done) { continue }
    $planTools += [pscustomobject]@{ Item = $t; Zip = $zip; BinDir = $binDir; Marker = $done
                                     Need = $(if (SameFile $zip $t.Size) { 0 } else { $t.Size }) }
}

if ($Mode -eq 'download') { $planBackup = @(); $planRepo = @() }

# ---------------------------------------------------------------- space check
$needD = ($planDl | Measure-Object -Property Need -Sum).Sum + ($planBackup | Measure-Object -Property Need -Sum).Sum + ($planTools | Measure-Object -Property Need -Sum).Sum
$needC = ($planRepo | Measure-Object -Property Need -Sum).Sum
$freeC = Free 'C'; $freeD = Free 'D'

Write-Host ''
Write-Host '=== Plan ===' -ForegroundColor Cyan
Write-Host '1. Download to D:'
if ($planDl) { $planDl | ForEach-Object { Write-Host ("   {0}  {1}  ({2})" -f (GB $_.Need), $_.Item.Name, $_.Item.Why) } } else { Write-Host '   nothing' }
Write-Host '2. Back up repo-only models to D:\Available\Models\LocalSwarm-backup'
if ($planBackup) { $planBackup | ForEach-Object { Write-Host ("   {0}  {1}" -f (GB $_.Need), ($_.Src.Substring($RepoModels.Length + 1))) } } else { Write-Host '   nothing' }
Write-Host '3. Copy into the repo Models folder (C:)'
if ($planRepo) { $planRepo | ForEach-Object { Write-Host ("   {0}  {1}" -f (GB $_.Need), $_.Name) } } else { Write-Host '   nothing' }
Write-Host '4. Extra llama.cpp builds (into Bin\)'
if ($planTools) { $planTools | ForEach-Object { Write-Host ("   {0}  {1} -> Bin\{2}" -f (GB $_.Item.Size), $_.Item.File, $_.Item.Dest) } } else { Write-Host '   nothing' }
Write-Host ''
$okC = ($freeC - $needC) -ge $ReserveC
$okD = ($freeD - $needD) -ge $ReserveD
Write-Host ("C:  needs {0}   free {1}   left afterwards {2}   {3}" -f (GB $needC), (GB $freeC), (GB ($freeC - $needC)),
            $(if ($okC) { 'OK' } else { "NOT ENOUGH (keeps $(GB $ReserveC) free)" })) -ForegroundColor $(if ($okC) { 'Green' } else { 'Red' })
Write-Host ("D:  needs {0}   free {1}   left afterwards {2}   {3}" -f (GB $needD), (GB $freeD), (GB ($freeD - $needD)),
            $(if ($okD) { 'OK' } else { "NOT ENOUGH (keeps $(GB $ReserveD) free)" })) -ForegroundColor $(if ($okD) { 'Green' } else { 'Red' })

if ($Mode -eq 'check') { exit 0 }
if (-not ($okC -and $okD)) { Write-Host 'Stopping: not enough space. Free some up (or answer N to the optional model) and run again.' -ForegroundColor Red; exit 2 }
if (-not ($planDl -or $planBackup -or $planRepo -or $planTools)) { Write-Host 'Everything is already in place.' -ForegroundColor Green; exit 0 }
if ((Read-Host 'Go ahead? (Y/N)') -notmatch '^[Yy]') { Write-Host 'Nothing done.'; exit 0 }

# ---------------------------------------------------------------- do it
function CopyFile($src, $dest) {
    $dir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    # robocopy: unbuffered I/O for big files, restartable, shows progress; exit codes < 8 mean success
    robocopy (Split-Path $src -Parent) $dir (Split-Path $src -Leaf) /J /R:2 /W:5 /NJH /NJS /NDL | Out-Host
    if ($LASTEXITCODE -ge 8) { throw "copy failed: $src" }
    if ((Get-Item -LiteralPath $dest).Length -ne (Get-Item -LiteralPath $src).Length) { throw "size mismatch after copy: $dest" }
}

foreach ($p in $planDl) {
    Write-Host "`n>> Downloading $($p.Item.Name) ..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path $p.Dest -Parent) | Out-Null
    for ($try = 1; $try -le 5; $try++) {
        # -C - resumes a partial download, so a dropped connection or power cut loses nothing
        curl.exe -L --fail --retry 3 -C - -o $p.Dest $p.Item.Url
        if (SameFile $p.Dest $p.Item.Size) { break }
        Write-Host "   download incomplete, retrying ($try/5) ..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
    }
    if (-not (SameFile $p.Dest $p.Item.Size)) { throw "download of $($p.Item.Name) did not complete; run Sync-Models.bat again to resume" }
    Write-Host "   done" -ForegroundColor Green
}
foreach ($p in $planTools) {
    Write-Host "`n>> $($p.Item.File) -> Bin\$($p.Item.Dest)" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $ToolDir, $p.BinDir | Out-Null
    for ($try = 1; $try -le 5 -and -not (SameFile $p.Zip $p.Item.Size); $try++) {
        curl.exe -L --fail --retry 3 -C - -o $p.Zip $p.Item.Url
    }
    if (-not (SameFile $p.Zip $p.Item.Size)) { throw "download of $($p.Item.File) did not complete; run Sync-Models.bat again to resume" }
    # the release zips hold the files either at the top or in one folder: flatten into Bin\<Dest>
    $tmp = Join-Path $env:TEMP ('lsw-' + [guid]::NewGuid())
    Expand-Archive -LiteralPath $p.Zip -DestinationPath $tmp -Force
    Get-ChildItem -LiteralPath $tmp -Recurse -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $p.BinDir -Force }
    Remove-Item -LiteralPath $tmp -Recurse -Force
    Set-Content -LiteralPath $p.Marker -Value (Get-Date)
    Write-Host "   done" -ForegroundColor Green
}
foreach ($p in $planBackup) { Write-Host "`n>> Backing up $($p.Src)" -ForegroundColor Cyan; CopyFile $p.Src $p.Dest }
foreach ($p in $planRepo)   { Write-Host "`n>> Copying $($p.Name) into the repo" -ForegroundColor Cyan; CopyFile $p.Src $p.Dest }

Write-Host "`nAll done." -ForegroundColor Green
Write-Host ("C: free now {0}   D: free now {1}" -f (GB (Free 'C')), (GB (Free 'D')))
