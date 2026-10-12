# PC Claude -> Codex: J14, coordinator tool step (calculator, dates, units) vs base on the 63 numeric questions. GPU job. Start when Chris passes this on; do J13 (no GPU) first or in the same sitting.

From: PC Claude (cloud). Date: 2026-10-11.

Why: in the J11 base run, 28 of 46 wrong answers had numeric/date answers (ages, year gaps, day counts, sums) and several look like found-but-mis-combined facts. This is milestone M0 of the runtime plan: the coordinator can now call exact tools. This run measures the rescue rate (wrong -> right) and the break rate (right -> wrong) on the 63 numeric/date questions of J11 (28 wrong, 35 right), against the same base config in the same session.

## What changed (cloud copy; deploy under fresh filenames, verify md5s; staged with a `.j14` suffix in the repo root)
- NEW `swarm/toolreg.py`: tool registry. Built-in tools: `calc` (safe arithmetic), `date_diff`, `age_on`, `date_add`, `weekday`, `unit_convert`. Also a generic MCP stdio client (`McpServer`), not used in this run. Every call returns data, never raises.
- `swarm/manager.py`: opt-in `manager.tools: {enabled: [...], max_calls}`. The coordinator's decision gets an optional `tool: {name, args}` field; the result becomes a `tool://` passage with an E-id and a note authored "tool", so it is cited and shown in the next turn. Log entries have `tool`; `stats.manager.tools` has the call log. (This file also contains the earlier J11/J12 changes.)
- `evals/configs.yaml`: `mgr-ex-base-tools` and group `tools-numeric` = [mgr-ex-base, mgr-ex-base-tools].
- `tests/test_tools.py` (new), `tests/echo_mcp_server.py` (new), `tests/mock_llama.py`, `tests/test_integration.py` (a new tool-step test).
- New `Tool-Step-Numeric.bat` (both configs, the 63 question ids, saved sources 20261004-2126, GPU/RAM logs, toast).

## Steps
1. Deploy, `uv sync`, run the full suite. The new `tests/test_tools.py::test_mcp_server_tools_and_failures` starts a tiny local MCP server with `sys.executable`; if it fails only because `mcp.server.fastmcp` is missing in the PC venv, report the exact error (do not install anything) and skip that one test.
2. Run `Tool-Step-Numeric.bat`. Nothing else on the GPU. Expect about 2.5 hours. Same stop rules as before.
3. Afterwards, from the traces of mgr-ex-base-tools: how many questions had at least one tool call, calls per question, ok vs failed calls, and the list of failed calls with their error text.

## Report back (`comms/2026-10-11-codex-to-pc-j14-tools.md`)
Run folder; score per config on the 63; paired result (rescued, broken, unchanged right, unchanged wrong); average seconds per question; the tool-call statistics from step 3; any errors.

## Do not
Do not change config values or tool code. Do not start other GPU jobs. Do not commit `runtime/`.

## Where the files are
Repo root, `.j14` suffix: `toolreg.py.j14` -> swarm/toolreg.py (new), `manager.py.j14` -> swarm/manager.py, `configs.yaml.j14` -> evals/configs.yaml, `test_tools.py.j14` -> tests/test_tools.py (new), `echo_mcp_server.py.j14` -> tests/echo_mcp_server.py (new), `mock_llama.py.j14` -> tests/mock_llama.py, `test_integration.py.j14` -> tests/test_integration.py, `Tool-Step-Numeric.bat.j14` -> Tool-Step-Numeric.bat (keep CRLF). md5s in `j14-md5.txt`. If J13 added tests to `tests/test_integration.py`, merge rather than overwrite (J13 should only add `tests/test_durable.py`). Move the `.j14` files into `_to_delete/` after deploying.
