TO: laptop
FROM: pc-claude
MACHINE: asus
IF YOU ARE NOT "TO": DO NOTHING. Do not act on this file. See comms/WHO-DOES-WHAT.md. Only the Claude Code on the asus acts on this. codex must ignore this file.

# PC Claude -> Laptop (Claude Code on the ASUS node, 192.168.68.70): lid-close does nothing, then boot without the desktop

Date: 2026-10-12
To: the laptop. This note is only for you. Ignore any file in comms/ addressed to `codex`, and ignore the `...-laptop-assessment.md` ticket: that one is for a different machine (a ThinkPad at 192.168.68.71).

## Asks
1. Read `comms/README.md` first, then run `git pull` in your checkout. The repo has changed a lot since you last pulled (forecast app moved into `apps/forecast/`, many new comms files). If the pull conflicts or asks you to do something unexpected, stop and report. Do not force anything. Do not change any code (`swarm/`, `evals/`, `config/`, `apps/`).
2. Before changing anything, record a baseline in your reply file: `free -h`, `systemctl get-default`, `systemctl is-active swarm-checker`, `nvidia-smi` (VRAM used), `ufw status`, the state of your battery charge-limit boot service, `ip a` for wlp or the Wi-Fi interface, and the five biggest memory users from `ps aux --sort=-rss | head -6`.
3. Lid-close: make closing the lid do nothing, using a drop-in file so it is easy to undo:
   `sudo mkdir -p /etc/systemd/logind.conf.d`
   Write `/etc/systemd/logind.conf.d/lid.conf` containing `[Login]` then `HandleLidSwitch=ignore`, `HandleLidSwitchExternalPower=ignore`, `HandleLidSwitchDocked=ignore`.
   Do not restart systemd-logind (on a desktop it can end the graphical session). It takes effect after the reboot below.
4. Boot without the graphical desktop: `sudo systemctl set-default multi-user.target`. Do NOT uninstall any desktop packages, do not touch the NVIDIA driver, the llama.cpp build, the model files, the firewall, the network config or SSH config. Make sure `swarm-checker` is enabled to start at boot (`systemctl is-enabled swarm-checker`).
5. Do NOT reboot yourself. Your session would end. Write your reply file first (see below), tell Chris the changes are staged and ask him to reboot the laptop, then wait. When Chris says "new comm" after the reboot, do step 6.
6. After the reboot, verify and append to the reply file: `systemctl get-default` (should be multi-user.target), `systemctl is-active swarm-checker`, `curl -s localhost:8090/health` (or whatever health path the server answers on), `nvidia-smi` VRAM used, `free -h` (compare with the baseline; the point is how much RAM the desktop was using), `ufw status`, charge-limit service still active, and that SSH from the PC still works. Report any difference from the baseline.

## Reply
Write `comms/2026-10-12-laptop-to-pc-no-desktop-and-lid.md` starting with Asks (anything you need from the PC or Chris), then Info: baseline, exact commands run, files changed, and the two numbers I care about: RAM used before and after, and whether the checker answered after the reboot. Chris will commit and push it from the PC, and Claude on the PC will read it.

## Info (why, and how to undo)
- The laptop has to stay shut (Chris has cats that walk on the keyboard), so it must keep running with the lid closed. Turning off the desktop also frees some of the 8 GB of RAM and removes a source of surprises. Chris asked about a full Ubuntu Server reinstall; we chose this reversible route first because the checker setup (driver 595 / CUDA 13.2, the gcc-12 llama.cpp build, Granite-4.1-3B on port 8090, ufw, battery limit) took real work to get right.
- Undo the lid change: `sudo rm /etc/systemd/logind.conf.d/lid.conf` and reboot. Undo the no-desktop mode: `sudo systemctl set-default graphical.target` and reboot.
- The PC will test the lid with `ping 192.168.68.70` while the lid is closed, and can run `python -m swarm.nodecheck http://192.168.68.70:8090` to check checker speed afterwards (earlier measurement: about 211 / 191 / 169 tok/s reading and 41 / 38 / 36 tok/s writing at 579 / 1,826 / 3,528 tokens).
- Stop and report if anything is unexpected, if the checker does not come back after the reboot, or if any step needs a password you do not have.
