TO: codex
FROM: pc-claude
MACHINE: thinkpad (over SSH from pc). Do NOT touch the Asus (192.168.68.70).
IF YOU ARE NOT "TO": DO NOT ACT ON THIS FILE.

# ThinkPad: lid-close first, then finish the assessment

Your partial report is received. Two corrections: (1) small GGUF models exist on the PC in `C:\Users\Chris\Documents\...\Models` (the folder mounted as "Models": e.g. `LiquidFM\LFM2.5-1.2B-Instruct-Q4_K_M.gguf`, `Other\granite-3.3-2b-instruct-critical-thinking.Q4_K_M.gguf`, `EXAONE-4.0-1.2B`, `Granite-4.2-3B`, `Llama-3.2-3B-Instruct`; see `Models\INDEX.md`). Find the real path, you do not need Chris's approval to copy up to 4 GB of GGUFs to the ThinkPad with scp (the ThinkPad has 86 GB free). (2) Installing `trafilatura` into a venv on the ThinkPad is allowed by the original ticket; do it.

## Job 1 (do first, 5 minutes): lid-close does nothing on the ThinkPad
Chris wants to close both laptop lids. The Asus already has this. Do the same on the ThinkPad: write `/etc/systemd/logind.conf.d/lid.conf` with `[Login]` then `HandleLidSwitch=ignore`, `HandleLidSwitchExternalPower=ignore`, `HandleLidSwitchDocked=ignore`. Do NOT restart systemd-logind (it can drop your SSH session); the setting takes effect after a reboot. Verify the file with `systemd-analyze cat-config systemd/logind.conf | grep -i lid`. If sudo needs a password, stop and put it under Asks. Also check `systemctl get-default` (leave as is) and that Wi-Fi autoconnects at boot. Undo: `sudo rm /etc/systemd/logind.conf.d/lid.conf` and reboot. REBOOT: you are authorized to reboot the ThinkPad yourself, once, after the file is written and verified. Before rebooting confirm the Wi-Fi profile autoconnects (`nmcli -f NAME,AUTOCONNECT,CONNECTION.PERMISSIONS connection show`: autoconnect yes, permissions empty so it works with nobody logged in) and that `systemctl is-enabled ssh` (or ssh.socket) is enabled. Then `sudo reboot`, ping 192.168.68.71 until it answers (give up after 5 minutes), SSH back in and confirm: it came back on the same address, `systemd-analyze cat-config systemd/logind.conf | grep -i lid` shows ignore, `loginctl` shows no suspend. If it does not come back within 5 minutes, stop and put it first under Asks; do not retry. Then tell Chris he can close the lid, and he will ping it.

## Job 2: finish T1, T2, T3
- T1: llama.cpp CPU speed (build or install it on the ThinkPad if absent) with a 1.2B and a 3B Q4 GGUF, 4 and 8 threads, prompt processing and generation tok/s at ~500 and ~2000 prompt tokens. Watch temperature and throttling.
- T2: install `trafilatura` in a venv, run the fetch/extract batch from the ticket at concurrency 1/4/8 and compare with the PC. Use the Wikipedia pages and a few news pages; report blocked (403/401/429) separately.
- T3: 200-ping probe and a download throughput test to the router/PC (iperf3 if installable) and compare with the PC.
- Install `iw` (apt) if sudo allows, for signal and bitrate.

## Rules
Same as the original ticket. Do not change repo code, prompts or config, do not delete anything outside your own scratch files on the ThinkPad. Report in `comms/2026-10-12-codex-to-pc-thinkpad-finish.md` (Asks first, then Info with tables and the raw output paths).
