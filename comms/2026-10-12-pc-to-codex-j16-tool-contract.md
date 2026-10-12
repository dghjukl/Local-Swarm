# Ticket (queue after push+fixes): J16 tool-contract fix and rerun
From PC Claude. To Codex. This edits core swarm code (swarm/manager.py), so it is NOT part of the unattended night queue; do it when Chris is present or has approved.

## Cause (verified from J14 results.jsonl)
Of 113 tool calls in the tools config, 79 failed and 76 were `unknown tool 'search'`. The decision schema has separate `search` and `tool` fields; the coordinator put {"name":"search","args":{}} into `tool`. Note the args were empty, so the search text was lost and the turn was wasted.

## Change
1. In manager.py where a tool call is handled: if tool name (case-insensitive) is `search`, `web_search`, `web`, or `google`, do not call the registry. Take the search text from args (`query`, `q`, `text`, or first string value). If empty, fall back to the decision's `task` text trimmed to a short query. Run it as a normal search for that turn. Count it in stats as `tool_search_alias` and log it.
2. TOOL_NOTE: add one line: "To search the web use the `search` field, never `tool`."
3. Tests: mock-based unit test of the alias (with args, without args). Existing tests stay green.
4. Config `mgr-ex-base-tools-ws` is unchanged. Add group `tools-numeric-fixed` = the 46 questions of J14 that attempted a tool call, config `mgr-ex-base-tools`, repeat 1.

## Run (GPU, after the forecast cycle finishes or in a gap; use the GPU lock)
Run the group. Report vs J14: for the 46 questions, base score, old tools score, new tools score; rescued/broken; tool call counts and failure reasons; `tool_search_alias` count. Success = failed-call rate under 10% and no worse than base.
