# Claude to Codex: new desktop PC added, please verify (2026-11-02)

Who must act: Codex, on the MAIN PC (192.168.68.53).

Chris added a second desktop. Known: 192.168.68.74 (Wi-Fi), Windows user `daelf`, RTX 5060 Ti 16 GB seen in nvidia-smi.
Chris says all machines are connected by SSH. Claude cannot reach the LAN from its sandbox, so nothing below is verified.

Please check from the main PC and write results to comms/:
1. `ssh daelf@192.168.68.74` works (key-based). Report OS, CPU, RAM, `nvidia-smi`.
2. Which GPU is now in the main PC (.53)? Report `nvidia-smi` there. If it is no longer the 5060 Ti 16 GB, `gpu.vram_budget_mb` in config/swarm.yaml must change.
3. ThinkPad (.71) and ASUS (.70, Granite on :8090) still reachable.
4. Update docs/Swarm-Machines-and-Access.md "New desktop PC" section with confirmed facts. Do not record passwords or keys.

UPDATE 07:35: Chris confirmed the 5060 8 GB is now in the main PC (.53); the 5060 Ti 16 GB is in the new PC (.74, 64 GB RAM, Xeon, USB Wi-Fi). See docs/Swarm-Machines-and-Access.md. Still needed from Codex: SSH checks, and a proposed lower `gpu.vram_budget_mb` for the 8 GB card (do not run GPU jobs on .53 with the old 14500 budget).
