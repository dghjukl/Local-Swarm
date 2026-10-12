[CmdletBinding()]
param(
    [int]$RetrySeconds = 5
)

$ErrorActionPreference = "Stop"

$nodes = @(
    @{ Name = "ThinkPad"; Host = "192.168.68.71"; User = "thinkpad" },
    @{ Name = "ASUS"; Host = "192.168.68.70"; User = "chris" }
)

function Test-SshPort {
    param([string]$HostName)
    try {
        $result = Test-NetConnection -ComputerName $HostName -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
        return [bool]$result
    } catch {
        return $false
    }
}

Write-Host "Waiting for the swarm laptops to accept SSH connections..."
$ready = @{}
foreach ($node in $nodes) { $ready[$node.Name] = $false }

while (($ready.Values | Where-Object { -not $_ }).Count -gt 0) {
    foreach ($node in $nodes) {
        if (-not $ready[$node.Name] -and (Test-SshPort $node.Host)) {
            $ready[$node.Name] = $true
            Write-Host "$($node.Name) is reachable. Opening its SSH tab."
            $sshTarget = "$($node.User)@$($node.Host)"
            Start-Process -FilePath "wt.exe" -ArgumentList @(
                "new-tab", "--title", $node.Name,
                "ssh", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", $sshTarget
            ) | Out-Null
        }
    }
    if (($ready.Values | Where-Object { -not $_ }).Count -gt 0) {
        Start-Sleep -Seconds $RetrySeconds
    }
}

Write-Host "Both SSH tabs were opened. Press Enter to close this launcher window."
Read-Host
