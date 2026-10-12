# Local Swarm: Machines, Operating Systems, Models, and Access

Last reviewed: 2026-10-13

This document describes the physical machines and software/runtime arrangement used by Local Swarm. It intentionally does not contain passwords, private keys, API tokens, or other secrets.

## At a glance

| Machine | Operating system | Main hardware | Address / service | Primary purpose |
|---|---|---|---|---|
| Main PC | Windows 11 | Intel i5-14400F, 16 GB RAM, NVIDIA RTX 5060 Ti with 16 GB VRAM | `192.168.68.53` | Holds the repository; runs the swarm, studies, forecast cycles, and GPU work |
| ThinkPad | Ubuntu Server 26.04 | AMD Ryzen 3 7320U, 4 cores / 8 threads; CPU-only | `thinkpad@192.168.68.71` | Remote CPU worker, benchmark host, and web-fetch/extraction node |
| ASUS laptop | Ubuntu 24.04 | NVIDIA GTX 1650 Mobile with 4 GB VRAM; 8 GB-class laptop | `192.168.68.70`; checker on port `8090` | Dedicated remote Granite checker/fact-checking service |

All three machines are on the same private LAN. The addresses above are local-network addresses, not public Internet addresses.

## Main Windows PC

The PC is the central machine. The Git repository is located at:

`C:\Users\Chris\Documents\GitHub\Local Swarm`

### Hardware and limits

- Windows 11.
- Intel i5-14400F CPU.
- 16 GB system RAM, single-channel configuration.
- NVIDIA RTX 5060 Ti with 16 GB VRAM.
- The swarm normally budgets approximately 14.5 GB of VRAM for model work so that the operating system and runtime remain responsive.
- Large models split between GPU memory and system RAM are possible, but they are slow and memory-sensitive on this machine.

### Local runtime

- Python environment: `.venv` in the repository.
- CUDA-enabled llama.cpp binaries: `Bin\llama-cuda\`.
- Local model files: `Models\`.
- Evaluation and study outputs: `runtime\`.
- Forecast application: `apps\forecast\`.
- Shared GPU lease: `C:\Users\Chris\Documents\GitHub\.gpu_lock\lock.json`.

Only one GPU-heavy job should use the PC at a time. The forecast application has a shared GPU lock; older evaluation scripts may still need manual coordination.

### Models on the PC

The PC has a large catalog of GGUF models under `Models\`, including models from Qwen, Gemma, Granite, Mistral, LFM, MiMo, OpenAI, Microsoft, NVIDIA, DeepSeek, EXAONE, Apertus, Bonsai, and other families. The exact installed inventory is the directory itself and changes as models are added or retired.

The principal models used by the current swarm and forecast setup are:

- `MiMo-V2.6-Distill-Qwen-9B` — current coordinator / lead model.
- `Qwen3.5-4B` — worker and verification work.
- `Gemma-4-E4B-it` — worker or verifier depending on the experiment.
- `Granite-4.1-3B` — available verifier/checker model.
- `gpt-oss-20b` — larger teacher/resolver candidate.
- `Bonsai-2-27B` — low-bit/ternary-style larger-model candidate under evaluation.

Many other models are available for controlled studies, but availability does not mean that a model is currently loaded or part of a running job.

### PC access

- Local Windows applications run directly on the PC.
- The repository is shared with the PC-side coding/research tools through the local checkout.
- The PC can initiate SSH connections to the ThinkPad and ASUS over the private LAN.
- The desktop reconnect launcher is:

  `C:\Users\Chris\Desktop\Swarm Nodes Reconnect.cmd`

  It waits for the two remote SSH ports, then opens Windows Terminal connections. It does not store passwords. The ThinkPad uses the existing SSH key; the ASUS connection may prompt for its password.

## ThinkPad node

The ThinkPad is a Lenovo IdeaPad 1 15AMN7 running Ubuntu Server 26.04. It is configured to continue running with the lid closed and has SSH enabled.

### Hardware and runtime

- AMD Ryzen 3 7320U, 4 cores / 8 threads.
- CPU-only for the swarm work; it is not a replacement for the PC GPU.
- Observed usable memory during assessment was approximately 5 GiB.
- A CPU-only llama.cpp build is maintained in the ThinkPad assessment area.
- The ThinkPad scratch/runtime area is `~/assess/`.

### Models used there

The ThinkPad has been used with small CPU-friendly GGUF models, especially:

- `LFM2.5-1.2B-Instruct-Q5_K_M.gguf` — practical small CPU worker.
- `granite-4.2-3b-Q5_K_M.gguf` — usable but much slower CPU worker.
- `EXAONE-4.0-1.2B-Q5_K_M.gguf` — benchmarked; too slow for routine worker use.

The ThinkPad can also run sequential web fetching and text extraction. Tests showed that it does not materially bypass the same public news-site blocks seen from the PC.

### ThinkPad access

SSH from the PC uses:

`ssh thinkpad@192.168.68.71`

Authentication uses the existing SSH key on the PC. No password is recorded here. The node is normally operated remotely; it does not have its own agent process in the swarm arrangement.

## ASUS laptop node

The ASUS is an ASUS TUF FX505DT running Ubuntu 24.04. It is kept as a dedicated service node rather than a general swarm development machine.

### Hardware and service

- NVIDIA GTX 1650 Mobile with 4 GB VRAM.
- Granite-4.1-3B is served locally on the ASUS GPU.
- Service address: `http://192.168.68.70:8090`.
- The service exposes a local OpenAI-compatible-style model endpoint and a health endpoint used by node checks.
- The laptop is configured to remain operating with the lid closed and to boot without the graphical desktop, leaving the checker service running.

### ASUS access

SSH from the PC uses:

`ssh chris@192.168.68.70`

The connection may request the account password interactively. The password is intentionally not stored in this document or in the reconnect launcher.

The ASUS node is not used for repository edits, forecast studies, or general PC work. Changes there are limited to its service, power/lid behavior, and related local configuration.

## Network and service relationships

```text
                         private LAN
                              |
        +---------------------+---------------------+
        |                     |                     |
  Windows PC            ThinkPad node          ASUS node
  192.168.68.53         192.168.68.71          192.168.68.70
  repo + GPU            SSH + CPU work         SSH + Granite:8090
```

- The PC is the coordination and storage point.
- The ThinkPad is reached over SSH for isolated CPU tasks and benchmarks.
- The ASUS is reached over SSH for service maintenance, while the PC can call its checker over port 8090.
- The machines do not require public inbound access for this arrangement; they communicate on the private LAN.

## Recovery after a reboot

1. Start the machines and wait for them to obtain their LAN addresses.
2. Double-click `C:\Users\Chris\Desktop\Swarm Nodes Reconnect.cmd` on the PC.
3. If prompted, enter the ASUS account password interactively.
4. Confirm the ThinkPad SSH session opens.
5. Confirm the ASUS checker responds at `http://192.168.68.70:8090`.
6. Before starting a GPU study or forecast cycle, check that no other GPU job owns the shared lock.

## Security notes

- This document contains connection names, private-LAN addresses, usernames, ports, and paths only.
- Passwords, private SSH keys, API tokens, and credentials must remain in their normal protected locations.
- A LAN address is not a guarantee of security; keep the machines behind the trusted network and firewall.
- Do not expose the model service ports to the public Internet.

## Related project files

- `comms/WHO-DOES-WHAT.md` — machine and responsibility map.
- `docs/Laptop-Node.md` — ASUS checker details.
- `apps/forecast/README.md` — pinned forecast application and swarm dependency.
- `tools/connect-swarm-nodes.ps1` — reconnect logic used by the desktop launcher.
