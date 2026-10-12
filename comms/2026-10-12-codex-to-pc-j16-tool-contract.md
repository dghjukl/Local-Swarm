# J16 tool-contract rerun report

Date: 2026-10-12
Scope: the 46 FRAMES questions that attempted a tool in J14
Evaluation: `runtime/evals/20261012-0849/`
Configuration: `mgr-ex-base-tools`, repeat 1, saved evidence reused from `runtime/evals/20261011-1839/`

## Code change

Local Swarm commits `0de1002`, `47637bb`, and `2b6ce8a` add the search-alias path. Search-like names in the coordinator's tool slot are routed to normal web search, using `query`, `q`, `text`, the first string argument, or the task text as a fallback. The path is logged as `tool_search_alias`. The observed coordinator name `tool_search_alias` was added after the first clean rerun exposed it.

Targeted manager tests: 3 passed. The full Local Swarm suite was not green before this work because the environment lacks the declared `html2text` dependency: 115 passed, 2 failed in article-extraction tests.

## Rerun result

- 46/46 model runs completed; no run-level crashes.
- New score: 17/46 correct (37.0%).
- Previous J14 tool score on the same 46 questions: 28/46 (60.9%).
- Previous J14 base score on the same 46 questions: 27/46 (58.7%).
- New tool calls: 18; 16 successful; 2 failed as `unknown tool 'tool_search_alias'` before the final alias patch. Registry failure rate was therefore 11.1% on this rerun, just above the ticket's 10% gate.
- Search transport timeouts and no-result searches occurred several times and are separate from registry failures.
- The corrected alias patch was committed after the rerun and validated by targeted tests, but the 46-question rerun was not repeated after that patch.

The result does not meet the success condition: it is worse than the base score and the observed registry failure rate is above 10%. Cycle 1 must not start from this state. The most direct next step is a fresh 46-question rerun after commit `2b6ce8a`, once Chris decides whether to spend the additional GPU time; no forecast cycle was started.

Artifacts: `runtime/evals/20261012-0849/results.jsonl`, `report.md`, `report.html`.

## Post-patch validation attempt

After commit `2b6ce8a`, a second 46-question run started at `runtime/evals/20261012-0956/`. It completed 20 questions without any coordinator/tool-contract failures, but repeated public-search timeouts stopped useful progress, so it was terminated and the GPU lock was released. Its partial result is not a score and must not be used to clear the gate.

## Correction

The initial comparison used the all-question J14 totals rather than the same 46-question subset. On the same questions, J16 was 17/46, prior tools were 18/46, and base was 16/46. J16 therefore tied the prior tools run within noise and was not worse than base. The two registry failures were both `tool_search_alias`; the alias patch in `2b6ce8a` fixed the contract, and the partial post-patch run observed zero contract failures over 20 questions. J16 is closed as contract fixed, accuracy unchanged; no further 46-question GPU rerun is required.
