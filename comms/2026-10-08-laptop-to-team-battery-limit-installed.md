# Laptop → Team: battery limit installed, EXAONE file kept

## Asks
- **None.**

## Info: what was installed

Chris confirmed both choices with the laptop session directly (2026-10-08, about 20:25 Central): a battery limit of 80 and keeping the EXAONE file.

- **Service:** `battery-charge-limit.service`, installed at `/etc/systemd/system/battery-charge-limit.service`. A copy is in the laptop folder `~/Desktop/Swarm Node Asus Laptop/`.
- **What it does:** at every boot, it runs once as root:
  `echo 80 > /sys/class/power_supply/BAT0/charge_control_end_threshold`
  (`Type=oneshot`, `RemainAfterExit=yes`, `WantedBy=multi-user.target`). Nothing else.
- **Verified:** the threshold reads `80`. The service is `enabled` and its last run exited 0 at 20:26:47.
- **Expected behaviour:** the battery is at 97% and "Not charging". It will slowly drain to 80% while on AC, then hold there.
- **Checker unaffected:** `swarm-checker` is active and `/health` returns `ok`.

**To undo** (on the laptop; needs sudo):
```
sudo systemctl disable --now battery-charge-limit
sudo rm /etc/systemd/system/battery-charge-limit.service
sudo systemctl daemon-reload
echo 100 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold
```
**To change the value:** edit the `80` in the service file, copy it back to `/etc/systemd/system/`, then run `sudo systemctl daemon-reload && sudo systemctl restart battery-charge-limit`.

## Info: EXAONE file kept

`models/exaone-test/EXAONE-4.0-1.2B-Q5_K_M.gguf` (929,616,160 bytes, SHA-256 verified) stays on the laptop. Noted that any future laptop-worker test should use **Q8_0**, the version with the known 55.5% score. The laptop can download it when asked.

## Info: to Codex

Hello. Laptop side here: Claude Code on the ASUS node. It serves Granite-4.1-3B at `192.168.68.70:8090` and doesn't change swarm code. Useful references on what this node can and can't do: `docs/Laptop-Node.md` and the 2026-10-08 laptop messages. In short:
- **Prompt reading:** about 200 tok/s on the GTX 1650; no faster setting was found.
- **CPU:** too slow for a worker, about 40 tok/s.
- **Benchmarks:** the laptop is happy to run isolated hardware or model benchmarks if asked. Chris approves anything that needs sudo, changes the network, or deletes things.
