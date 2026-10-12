TO: pc-claude
FROM: codex
MACHINE: pc -> thinkpad

# ThinkPad finish — blocked on lid configuration

## Asks

The ThinkPad requires Chris's sudo password before I can create `/etc/systemd/logind.conf.d/lid.conf`. The ticket says to stop at this point if sudo needs a password. No reboot or further assessment work was started.

## Checks completed

- SSH to `thinkpad@192.168.68.71`: successful.
- `sudo -n true`: password required; no password was stored or requested.
- `systemctl get-default`: `graphical.target` (left unchanged).
- `systemctl is-enabled ssh.socket`: `enabled`.
- `nmcli` did not return the connection table in the noninteractive SSH session, so Wi-Fi autoconnect remains unverified.
- ASUS `192.168.68.70` was not contacted.

## Next authorized steps after sudo is available

1. Write and verify the three `HandleLidSwitch=ignore` settings on the ThinkPad only, without restarting logind.
2. Verify Wi-Fi autoconnect and SSH enablement, then reboot once.
3. Reconnect on `192.168.68.71`, verify the settings and no suspend, then finish T1/T2/T3.

No files on the PC repo were changed by this attempt.
