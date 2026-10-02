$ErrorActionPreference = 'Continue'
$Repo = Split-Path -Parent $PSScriptRoot
function Section($t) { "`n===== $t =====" }
function Try-Run($label, [scriptblock]$sb) { try { & $sb } catch { "$label failed: $($_.Exception.Message)" } }

Section 'PROBE'
"time_utc: $((Get-Date).ToUniversalTime().ToString('o'))"
"repo: $Repo"

Section 'OS'
Try-Run 'os' { Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List | Out-String }
Try-Run 'longpaths' { "LongPathsEnabled: " + (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled }
"PowerShell: $($PSVersionTable.PSVersion)"

Section 'CPU'
Try-Run 'cpu' { Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, L3CacheSize | Format-List | Out-String }

Section 'MEMORY'
Try-Run 'ram' { Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer, PartNumber, @{n='GB';e={[math]::Round($_.Capacity/1GB,1)}}, Speed, ConfiguredClockSpeed | Format-Table -AutoSize | Out-String }
Try-Run 'ramfree' { $o = Get-CimInstance Win32_OperatingSystem; "visible_GB: {0:N1}  free_GB: {1:N1}" -f ($o.TotalVisibleMemorySize/1MB), ($o.FreePhysicalMemory/1MB) }
Try-Run 'pagefile' { Get-CimInstance Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, CurrentUsage | Format-Table -AutoSize | Out-String }

Section 'GPU'
Try-Run 'gpu' { Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, @{n='AdapterRAM_GB';e={[math]::Round($_.AdapterRAM/1GB,1)}} | Format-Table -AutoSize | Out-String }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { $p = 'C:\Windows\System32\nvidia-smi.exe'; if (Test-Path $p) { $smi = $p } }
if ($smi) {
  Try-Run 'smi-query' { & $smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap,pcie.link.gen.max,pcie.link.width.max,power.limit,temperature.gpu --format=csv }
  Try-Run 'smi' { & $smi }
} else { 'nvidia-smi not found' }

Section 'DISK'
Try-Run 'vol' { $d = (Get-Item $Repo).PSDrive.Name; Get-Volume -DriveLetter $d | Select-Object DriveLetter, FileSystem, @{n='SizeGB';e={[math]::Round($_.Size/1GB)}}, @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB)}} | Format-Table -AutoSize | Out-String }
Try-Run 'phys' { Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, @{n='SizeGB';e={[math]::Round($_.Size/1GB)}} | Format-Table -AutoSize | Out-String }

Section 'AUDIO DEVICES'
Try-Run 'audio' { Get-CimInstance Win32_SoundDevice | Select-Object Name, Status | Format-Table -AutoSize | Out-String }
Try-Run 'pnp-audio' { Get-PnpDevice -Class AudioEndpoint -ErrorAction Stop | Where-Object Status -eq 'OK' | Select-Object FriendlyName | Format-Table -AutoSize | Out-String }

Section 'SYSTEM RUNTIMES (informational only - the build will not depend on these)'
foreach ($f in 'msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll') { "$f present: " + (Test-Path "C:\Windows\System32\$f") }
foreach ($c in 'python','py','uv','git','node','ffmpeg') {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue
  if ($cmd) { $v = try { (& $c --version 2>&1 | Select-Object -First 1) } catch { '?' }; "$c : $($cmd.Source) : $v" } else { "$c : not on PATH" }
}

Section 'REPO BINARIES'
foreach ($b in 'Bin\cuda\llama-server.exe','Bin\cpu\llama-server.exe') {
  $full = Join-Path $Repo $b
  if (Test-Path $full) {
    "--- $b --version"; Try-Run $b { & $full --version 2>&1 | Select-Object -Last 4 }
    "--- $b --list-devices"; Try-Run $b { & $full --list-devices 2>&1 | Select-Object -Last 8 }
  } else { "$b missing" }
}
$w = Join-Path $Repo 'Bin\Whisper-CUDA\Release\whisper-server.exe'; "whisper-server present: " + (Test-Path $w)
$pp = Join-Path $Repo 'Bin\Piper\piper.exe'; "piper present: " + (Test-Path $pp)
$t = Join-Path $Repo 'Bin\Tesseract-OCR\tesseract.exe'; if (Test-Path $t) { Try-Run 'tess' { & $t --version 2>&1 | Select-Object -First 1 } }

Section 'NETWORK'
foreach ($u in 'https://huggingface.co','https://pypi.org/simple/','https://github.com','https://astral.sh','https://duckduckgo.com','https://en.wikipedia.org') {
  try { $r = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 10 -UseBasicParsing; "$u -> $($r.StatusCode)" } catch { "$u -> FAILED: $($_.Exception.Message)" }
}
Try-Run 'ports' { $used = Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -ge 8000 -and $_.LocalPort -le 8200 } | Select-Object -ExpandProperty LocalPort -Unique; "listening ports 8000-8200: " + ($used -join ', ') }

Section 'END'
