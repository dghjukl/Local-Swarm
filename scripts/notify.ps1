param(
    [Parameter(Mandatory = $true)] [string]$Job,
    [Parameter(Mandatory = $true)] [int]$Code,
    [Parameter(Mandatory = $true)] [string]$Summary,
    [switch]$NoDisplay
)

# Notifications are deliberately best-effort: a broken toast must never change a job result.
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$logDir = Join-Path $root 'runtime\logs'
$donePath = Join-Path $logDir ("DONE-{0}-{1}.txt" -f $Job, $stamp)
$title = if ($Code -eq 0) { "Local Swarm: $Job finished" } else { "Local Swarm: $Job FAILED (exit $Code)" }
$body = if ([string]::IsNullOrWhiteSpace($Summary)) { "exit $Code" } else { $Summary }

try {
    New-Item -ItemType Directory -Force -Path $logDir -ErrorAction Stop | Out-Null
    @(
        "Time: $(Get-Date -Format o)"
        "Job: $Job"
        "Exit code: $Code"
        "Summary: $body"
    ) | Set-Content -LiteralPath $donePath -Encoding UTF8 -ErrorAction Stop
} catch {
    # The completion record is useful but must not fail the caller.
}

if (-not $NoDisplay) {
    $shown = $false
    try {
        Add-Type -AssemblyName System.Runtime.WindowsRuntime -ErrorAction Stop
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $safeTitle = [System.Security.SecurityElement]::Escape($title)
        $safeBody = [System.Security.SecurityElement]::Escape($body)
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$safeTitle</text><text>$safeBody</text></binding></visual></toast>")
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Local Swarm').Show($toast)
        $shown = $true
    } catch {
        # Fall through to the tray balloon.
    }

    if (-not $shown) {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
            Add-Type -AssemblyName System.Drawing -ErrorAction Stop
            $icon = New-Object System.Windows.Forms.NotifyIcon
            $icon.Icon = [System.Drawing.SystemIcons]::Application
            $icon.Visible = $true
            $tip = if ($Code -eq 0) { [System.Windows.Forms.ToolTipIcon]::Info } else { [System.Windows.Forms.ToolTipIcon]::Error }
            $icon.ShowBalloonTip(5000, $title, $body, $tip)
            Start-Sleep -Milliseconds 250
            $icon.Dispose()
            $shown = $true
        } catch {
            # Sound is the final fallback.
        }
    }

    try {
        if ($Code -eq 0) { [System.Media.SystemSounds]::Exclamation.Play() }
        else { [System.Media.SystemSounds]::Hand.Play() }
    } catch {
        # No display/audio stack is still a successful notification attempt.
    }
}

exit 0
