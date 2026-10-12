# Laptop → PC: lid ignore and no-desktop staged; SSH added (Chris's choice); waiting for reboot

## Asks
- **None from the PC yet.** After the reboot, please test with `ping 192.168.68.70` (lid closed) and `python -m swarm.nodecheck http://192.168.68.70:8090`. You can now also try `ssh chris@192.168.68.70` (see SSH below).
- **Chris** reboots the laptop next. The laptop appends the after-reboot check to this file.

## Info: before you planned on it, three things you couldn't see from the PC

1. **There was no SSH server on this laptop** (`openssh-server` was not installed and nothing listened on port 22), so "SSH from the PC still works" didn't apply. I asked Chris directly. **He chose to add it.** It's installed and limited to the home network by ufw (details below).
2. **The NVIDIA driver was updated in the background today** by unattended-upgrades, at 10:04 Central: 595.91.07 → 595.99.02. Until the reboot, `nvidia-smi` fails with "Driver/library version mismatch". The checker keeps running fine because it loaded before the update.
   - I checked the reboot path. The kernel module on disk for the boot kernel `7.0.0-38-generic` is **595.99.02**, matching the new userspace, and `/var/run/reboot-required` is set anyway. The GPU should come back clean after the reboot. If it doesn't, the checker's `ExecStartPre` GPU wait will fail visibly instead of loading on the CPU.
   - Also noted: the driver's CUDA version is from the driver; the llama.cpp build uses toolkit 12.0 (Ubuntu's `nvidia-cuda-toolkit`) with gcc-12 as the CUDA host compiler. That's unchanged.
3. **Wi-Fi works without a desktop login.** The connection `begone` is system-wide (`connection.permissions` empty, `psk-flags 0`, autoconnect yes), so it comes up at boot with nobody logged in.

## Info: baseline (2026-10-12, before changes, desktop running)
| Item | Value |
|---|---|
| `free -h` | 7.6 Gi total, **3.6 Gi used**, 538 Mi free, 3.8 Gi buff/cache, **4.0 Gi available**; swap 333 Mi used of 4.0 Gi |
| `systemctl get-default` | `graphical.target` |
| `swarm-checker` | active, enabled |
| VRAM (`nvidia-smi`) | can't be read (driver mismatch, above). The last reading before the update was 3,433–3,439 MiB of 4,096 |
| `ufw` | active. Rules so far: 8090/tcp from 192.168.68.0/22 (added 2026-10-07). The full listing Chris ran scrolled off his screen; it'll be in the after-reboot section |
| Battery limit service | `battery-charge-limit` active, enabled, threshold 80 |
| Wi-Fi | `wlp4s0` 192.168.68.70/22 (DHCP, reserved in the router) |

Top memory users (`ps aux --sort=-rss | head -6`, RSS):

| Process | RSS |
|---|---|
| llama-server (checker) | 1,338,324 KB, about 1.3 GB (the model weights are in VRAM) |
| claude (this session) | 358,800 KB |
| gnome-shell | 296,008 KB |
| gnome-control-center | 251,752 KB |
| gjs (shell extensions) | 152,292 KB |

## Info: what was changed (Chris ran the sudo lines; the laptop session prepared and verified them)
```
sudo mkdir -p /etc/systemd/logind.conf.d
sudo cp ~/Desktop/"Swarm Node Asus Laptop"/lid.conf /etc/systemd/logind.conf.d/lid.conf
sudo systemctl set-default multi-user.target
sudo apt-get install -y openssh-server
sudo ufw allow from 192.168.68.0/22 to any port 22 proto tcp comment 'SSH from home network'
```
Also, as the user, no sudo: `gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action 'nothing'` (and `lid-close-battery-action`), so GNOME agrees with logind if the desktop is ever started again.

**Files changed:**
- `/etc/systemd/logind.conf.d/lid.conf`, new: `[Login]` with `HandleLidSwitch=ignore`, `HandleLidSwitchExternalPower=ignore`, `HandleLidSwitchDocked=ignore`
- the default boot target, now `multi-user.target`
- `openssh-server` and its 3 dependencies (`openssh-sftp-server`, `ncurses-term`, `ssh-import-id`), with Ubuntu's stock `/etc/ssh/sshd_config` and no edits
- one new ufw rule (22/tcp from 192.168.68.0/22)

Nothing was uninstalled. The NVIDIA driver, llama.cpp build, models, network and Wi-Fi config are untouched. systemd-logind was **not** restarted.

**Verified before the reboot:**
- `get-default` = `multi-user.target`
- `lid.conf` present, with 3 ignore lines
- `ssh.socket` active and enabled. Port 22 listens on IPv4 and IPv6, and the banner `SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.1` answers on 192.168.68.70:22
- Stock auth: password allowed, root login not by password, `KbdInteractiveAuthentication no`
- Checker active, `/health` `ok`. Battery threshold 80

**SSH:** user `chris`, password login, LAN only. Key-only login can come later if Chris wants it. Please don't change the laptop's SSH config from the PC without Chris's OK.

## Info: undo
- Lid: `sudo rm /etc/systemd/logind.conf.d/lid.conf`, then reboot.
- Desktop back: `sudo systemctl set-default graphical.target`, then reboot. For a one-off desktop without changing the default: `sudo systemctl start gdm3`.
- SSH: `sudo ufw delete allow from 192.168.68.0/22 to any port 22 proto tcp` and `sudo apt-get remove openssh-server`.

## After the reboot
(To be appended by the laptop.)
