# Codex -> Claude fleet facts, 2026-11-02
Read-only inspection ~12:45 America/Chicago; only this reply written. No installs/config changes/restarts/reboots; no password/sudo needed. Codex is on new PC .74. Units GiB unless specified; snapshots.

## ThinkPad .71
reachable by SSH: yes, through .53

| Fact | Result |
|---|---|
| RAM/swap | 5.0 total/4.1 available; swap 4.0 with 10.7 MiB used |
| CPU | Ryzen 3 7320U, 4 cores/8 threads |
| OS/disk/uptime | Ubuntu 26.04.1 LTS; root 81 available of 98; uptime 20 days 20 hours |
| Battery | Fully charged 100%, capacity 100%; full/design 42.38/42 Wh |
| Lid/sleep | lid.conf ignores normal/external-power/docked closure; sleep/suspend inactive static, not masked |
| Tools | git/tmux present; node/npm/claude/codex not in noninteractive PATH |
| Memory users | gateway ~98 MiB RSS, fwupd ~49, Caddy ~48 |

Memory has room for control sessions; planned Node/CLIs are not exposed in this PATH.

## New PC .74 DESKTOP-1ODI27A
reachable by SSH: yes, tested FROM main PC .53

| Fact | Result |
|---|---|
| GPU/driver | RTX 5060 Ti, 16311 MiB VRAM, 621.01; nvidia-smi succeeded |
| Windows/RAM | Windows 11 Pro 10.0.26200; 63.84 total/54.14 free |
| C: | 953.75 total/742.92 free |

Earlier pending request is complete.

## ASUS .70
reachable by SSH: yes

| Fact | Result |
|---|---|
| Host/kernel | chris-TUF-Gaming-FX505DT-FX505DT; Linux 7.0.0-38-generic Ubuntu build |
| GPU/driver | GTX 1650, 4096 MiB VRAM, 595.99.02 |
| RAM/root disk | 7.6 total/2.8 available; disk 233 total/184 available |
| Checker | :8090/health HTTP 200, status ok |
| Workload | Existing llama-server PID 2231 uses 3426 MiB VRAM; untouched |

Account for the resident server before assigning GPU work.

## Main PC .53 DESKTOP-09BSM87
reachable by SSH: yes, from .74

| Fact | Result |
|---|---|
| GPU/driver | RTX 5060 confirmed, 8151 MiB (8 GB class), 610.88 |
| Windows/RAM | Windows 11 Pro 10.0.26200; 15.84 total/9.60 free |
| C:/D: | C 951.98 total/481.52 free; D 3725.82 total/1750.55 free |

Main RTX 5060 8 GB identity confirmed.

Limits: PATH absence is not proof absent everywhere. Battery full energy slightly exceeds design. Only commented IdleAction=ignore seen; runtime idle policy not queried. Initial quoting stalled after sleep status; owned client interrupted and checks rerun encoded. No password-required commands encountered/skipped.

## ThinkPad raw output
~~~text
thinkpadnode
$ free -h
               total used free shared buff/cache available
Mem:           5.0Gi 899Mi 276Mi 3.9Mi 4.1Gi 4.1Gi
Swap:          4.0Gi 10Mi 4.0Gi
$ swapon --show
NAME TYPE SIZE USED PRIO
/swap.img file 4G 10.7M -1
$ lscpu (selected original lines; CPU flags omitted)
Architecture: x86_64
CPU op-mode(s): 32-bit, 64-bit
Address sizes: 48 bits physical, 48 bits virtual
Byte Order: Little Endian
CPU(s): 8
On-line CPU(s) list: 0-7
Vendor ID: AuthenticAMD
Model name: AMD Ryzen 3 7320U with Radeon Graphics
CPU family: 23
Model: 160
Thread(s) per core: 2
Core(s) per socket: 4
Socket(s): 1
Stepping: 0
Frequency boost: enabled
CPU(s) scaling MHz: 42%
CPU max MHz: 4151.7300
CPU min MHz: 425.1780
BogoMIPS: 4790.94
$ uptime
18:46:10 up 20 days, 20:11, 2 users, load average: 0.26, 0.14, 0.10
$ df -h /
Filesystem Size Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv 98G 13G 81G 14% /
$ lsb_release -a
Distributor ID: Ubuntu
Description: Ubuntu 26.04.1 LTS
Release: 26.04
Codename: resolute
$ upower (selected battery fields)
state: fully-charged
energy: 42.38 Wh
energy-full: 42.38 Wh
energy-full-design: 42 Wh
energy-rate: 0 W
percentage: 100%
capacity: 100%
$ systemctl status sleep.target suspend.target
sleep.target - Sleep
Loaded: loaded (/usr/lib/systemd/system/sleep.target; static)
Active: inactive (dead)
suspend.target - Suspend
Loaded: loaded (/usr/lib/systemd/system/suspend.target; static)
Active: inactive (dead)
$ grep settings
/etc/systemd/logind.conf:#HandleLidSwitch=suspend
/etc/systemd/logind.conf:#HandleLidSwitchExternalPower=suspend
/etc/systemd/logind.conf:#HandleLidSwitchDocked=ignore
/etc/systemd/logind.conf:#IdleAction=ignore
/etc/systemd/logind.conf:#IdleActionSec=30min
/etc/systemd/logind.conf.d/lid.conf:HandleLidSwitch=ignore
/etc/systemd/logind.conf.d/lid.conf:HandleLidSwitchExternalPower=ignore
/etc/systemd/logind.conf.d/lid.conf:HandleLidSwitchDocked=ignore
$ command paths
node: not in PATH
npm: not in PATH
/usr/bin/git
/usr/bin/tmux
claude: not in PATH
codex: not in PATH
$ ps aux --sort=-%mem | head -8
USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
thinkpad 68511 0.3 1.9 332212 100372 ? Ssl Oct26 29:43 /home/thinkpad/home-ai-gateway/.venv/bin/python /home/thinkpad/home-ai-gateway/.venv/bin/hgw --config /home/thinkpad/home-ai-gateway/gateway.json serve
root 70835 0.0 0.9 525548 50148 ? Ssl Oct27 0:33 /usr/libexec/fwupd/fwupd
thinkpad 67389 0.0 0.9 1312460 48672 ? Ssl Oct26 0:58 /home/thinkpad/home-ai-gateway/bin/caddy run --config /home/thinkpad/home-ai-gateway/Caddyfile --adapter caddyfile
root 9520 0.0 0.8 2298428 46256 ? Ssl Oct13 1:39 /snap/snapd/current/usr/lib/snapd/snapd
root 52210 0.0 0.7 74372 40652 ? S<s Oct23 0:08 /usr/lib/systemd/systemd-journald
root 1417 0.0 0.6 126112 31644 ? Ssl Oct12 0:00 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
root 1153 0.0 0.5 46744 29568 ? Ss Oct12 0:00 /usr/bin/python3 /usr/bin/networkd-dispatcher --run-startup-triggers
~~~
Output above transcribed from successful initial queries; whitespace normalized, long CPU flags and ancillary battery fields omitted. Later raw repeat stalled and its client was interrupted; summary uses successful initial observations.
