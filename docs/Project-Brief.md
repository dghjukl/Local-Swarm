# Local Swarm

## A project brief for someone new to the project

## In one sentence

Local Swarm is an experiment in using several small, locally running language models as a coordinated research team, to see whether organization, specialization, criticism, memory, and persistence can let modest hardware perform research that would normally require a much larger model.

This is both a working local research assistant and a laboratory for studying whether collective process can compensate for limited individual model capability.

## Why this exists

Large language models are often impressive at producing an answer, but serious research requires more than fluent text. A useful research system must be able to:

- break a vague question into answerable parts;
- find relevant sources;
- distinguish evidence from guesses;
- notice when information is missing or contradictory;
- follow promising leads;
- check important claims;
- revise its plan when a line of investigation fails; and
- explain what it knows, what it does not know, and why.

The project's working definition of the target: *generality is the ability to apply knowledge and reasoning across domains to solve unfamiliar problems.*

The central question of Local Swarm is:

> Can a group of smaller local models, given the right roles and workflow, conduct more capable and more reliable research than any one of those models could do alone?

The project is deliberately local. The models, inference runtime, research tools, speech components, traces, and evaluations run on one Windows PC with an RTX 5060 Ti 16 GB GPU and 16 GB of system RAM.

**Design priority: capability over speed.** The intended use is long-form research, not chat. The guiding question is how much capability this hardware can produce when time is the main thing traded for it. Minutes per question, or hours per investigation, are acceptable when they buy accuracy, thoroughness or better-calibrated uncertainty. Effort is still escalated step by step, but to avoid wasted work, not to save seconds. The speed comparison is a person doing the research by hand, not another machine: a multi-hop question that takes a careful person ten minutes or more is answered, checked and cited in a few minutes, unattended.

## What the system does today

For a research question, the current system can:

1. Ask a coordinator model to classify and decompose the question.
2. Search the web, Wikipedia, news sources, and selected scholarly indexes.
3. Fetch and clean source pages.
4. Split source material into ranked passages.
5. Give passages to several local models with different roles.
6. Ask those models to report facts and cite the passages supporting them.
7. Have a verifier check claims against the cited evidence.
8. Have a coordinator write a final answer from the checked material.
9. Save the plan, searches, sources, passages, worker responses, verification, timing, token usage, and final answer for later analysis.

The browser interface shows the research stages, team members, sources, claims, verification state, GPU models, and final citations while a question is running.

## The main research architectures

### Solo baseline

One coordinator reads the evidence and writes the answer. This establishes how well the main model performs without collaboration.

### Standard swarm

Several workers answer subquestions independently. A verifier checks their claims, and the coordinator synthesizes the result.

This tests whether model diversity and independent attempts help.

### Notebook

Workers read different passages and write notes into a shared notebook. The notes are merged, deduplicated, fact-checked, reviewed, and passed to a writer.

This tests whether shared memory and collaboration are better than simply collecting separate answers.

### Multiple attempts + vote (being tested)

The manager loop runs several times independently (different randomness, optionally different worker pairs), and the coordinator compares the answers and picks the best-supported one. This tests whether a "swarm of attempts" beats one deeper attempt, and whether diverse attempts beat copies of one model.

### Manager

The coordinator behaves more like a research lead. It repeatedly examines the current workspace and decides the next action:

- which teammate should investigate;
- what single fact that teammate should look for;
- whether a new search is needed;
- whether another teammate should independently check the result;
- whether a failed line of inquiry should be retried differently; and
- whether a larger expert model should be called in.

This is the most important architecture for the long-term goal. It moves the system toward an autonomous investigator rather than a fixed answer pipeline.

## What “small models doing real research” means here

The goal is not merely to make several small models vote on an answer. The goal is to give them a process that lets them compensate for one another.

A weak model may still be useful if it can accurately perform one narrow task:

- identify the relevant source;
- extract one fact;
- compare two passages;
- notice a contradiction;
- check whether a claim is actually supported; or
- suggest the next search.

The coordinator can then combine many narrow, checked contributions into a longer investigation. In this design, capability comes partly from the workflow: decomposition, persistence, memory, specialization, criticism, and verification.

The more ambitious future target is “frontier autonomous research”: starting from a broad objective, deciding what must be learned, pursuing evidence, revising hypotheses, testing contradictions, and producing a reproducible research record.

## What has been tested

The repository contains evaluations for:

- single models versus teams;
- mixed model lineages versus copies of one model;
- one to five workers;
- different worker roles;
- different reasoning strategies;
- keyword ranking versus neural reranking;
- notebook collaboration versus separate answers;
- large, small, or absent coordinators;
- manager loops with one worker or multiple workers;
- identical versus diverse worker pairs;
- coordinator thinking versus direct answering;
- verification versus no verification;
- larger expert models called only when the team is stuck; and
- equal-compute solo baselines.

The main question sets include FRAMES multi-hop questions, 2026 news questions, GAIA text questions, local research questions, and a verifier-specific claim benchmark.

## Results so far

The results are mixed but meaningful.

### Manager experiments on FRAMES

All runs use the same 100 FRAMES multi-hop questions with the same saved sources. The coordinator is MiMo-V2.6-Distill-Qwen-9B; workers are Qwen3.5-4B and Gemma-4-E4B.

| Configuration | Score | Average time | Interpretation |
|---|---:|---:|---|
| MiMo coordinator alone with wide evidence | 24–25% | about 4 seconds/question | Fast baseline, weak on many multi-hop questions |
| Manager, thinking MiMo + Qwen3.5-4B and Gemma-4-E4B (every task to both) | **44–52%** | about 60–65 seconds/question | Best setup so far; at 52% it beat solo by +28 points (31 questions won, 3 lost) |
| Manager with two identical Qwen3.5-4B workers | 38–46% | about 59–70 seconds/question | Statistically tied with the diverse pair |
| + fact-checker on facts only one worker found | 42–46% | 65–127 seconds/question | The checker confirmed 189 of 199 such facts; no score gain |
| + structured worker reports, or 10 turns and more thinking | 47% | 85–95 seconds/question | No gain |
| + a larger expert model (Qwen3.5-9B, Gemma-4-12B, Ornith-1.5-9B) when stuck | 42–47% | 122–167 seconds/question | No gain; the experts often found the missing fact, but the stuck questions stayed hard |

Three lessons from these runs:

1. **The research loop is the big win.** Turning one-shot answering into a coordinator-directed, step-by-step investigation roughly doubles accuracy on multi-hop questions.
2. **Adding more effort to a single attempt has stopped paying off.** Reports, extra turns, extra thinking and bigger experts all failed to beat the plain loop.
3. **Variance is now the main lever.** The same configuration scored 44% in one run and 52% in another, so single-run differences under about 8 points are noise. Across six manager setups, 71 of 100 questions were answered correctly by at least one setup but only 21 by all six. A simple majority vote over the answers of any three setups scored 56–57%, above every single setup. The current experiment tests this directly: three independent attempts plus a coordinator vote, with identical versus diverse worker pairs.

### Notebook experiments

Earlier 2026-news experiments produced more nuanced results. A solo MiMo coordinator reached roughly 69–73% on one saved question set, while notebook variants ranged from approximately 48% to 65% depending on the leader and configuration.

This means collaboration is not automatically beneficial. A notebook can add useful coverage, but it can also introduce latency, distract the writer, propagate weak notes, or spend computation on work the coordinator could have done directly.

### Strategy experiments

On a saved screening set, MiMo performed better when using structured strategies such as “step back” or “self ask” than when answering directly. This supports the idea that process and prompting can matter nearly as much as raw model size for some tasks.

### Verifier experiments

The verifier benchmark checked 400 real worker claims against cited passages. The best local verifier candidates were very strong on that particular benchmark:

| Verifier | Accuracy |
|---|---:|
| Gemma-4-E4B | 99% |
| Qwen3.5-4B | 99% |
| Granite-4.1-3B | 98% |

These numbers are encouraging, but they are not definitive. The reference labels were produced partly with larger reference judges, so the benchmark should be expanded with independently labeled cases.

## What the results mean

The project has not yet shown that a swarm is universally better than a large model. It has shown something more specific and potentially more interesting:

> On difficult multi-hop research tasks, a persistent manager-and-worker process more than doubles what the same coordinator achieves alone (24% → 52% on FRAMES-100), and different runs of that process succeed on different questions, so combining independent attempts looks like the next gain.

The cost is substantial. The swarm uses more time, more memory, more model loads, and more opportunities for coordination failure.

The likely practical solution is selective escalation:

```text
ordinary question
    → one local model

uncertain or multi-step question
    → coordinator + evidence + verifier

hard multi-hop question
    → manager + targeted workers

stubborn or high-value question (or attempts that disagree)
    → several independent manager attempts + a vote + explicit uncertainty
```

The swarm should be used where its additional investigation earns its cost.

## The larger direction

The current system is still closer to a highly structured research assistant than a fully autonomous scientist. The intended next stage is to make research state explicit.

Instead of storing only extracted facts, the system should track:

- the objective;
- subquestions;
- competing hypotheses;
- evidence for and against each hypothesis;
- source quality and source independence;
- unresolved contradictions;
- assumptions and calculations;
- failed searches;
- proposed experiments or analyses;
- stopping criteria; and
- a clear list of unresolved questions.

The desired research loop is:

```text
objective
  → questions
  → hypotheses
  → search plan
  → evidence
  → contradictions
  → revised hypotheses
  → targeted follow-up
  → conclusion
  → unresolved questions
```

That is the point where a collection of small models could begin doing work that is qualitatively different from ordinary question answering.

## Other parts of the project

### Model laboratory

The repository contains a large collection of GGUF models from different labs and lineages, along with model manifests, download scripts, runtime compatibility handling, VRAM measurements, and model-specific chat-template fixes.

### Training pool

A deterministic 3,000-item training pool has been built from multi-hop research datasets. It contains source questions, shuffled evidence, supporting-source labels, contamination checks, train/dev splits, and false-premise examples. The purpose is to eventually distill useful research strategies into smaller models.

### Local research MCP

The separate `MCP/research-mcp` component provides search, fetch, extraction, planning, and iteration tools. It is stateless and includes SSRF protection, response-size limits, and tests.

### Speech and interface

The system includes local speech-to-text through Whisper, local text-to-speech through Piper, and a browser UI showing the live research process.

## Current limitations

- The GPU and RAM limits make model scheduling and eviction critical.
- Multi-model runs are much slower than a single-model answer. That is acceptable for the intended long-form use, but it makes evaluations long (a 100-question study takes 10–18 hours).
- Web search results are discovery material, not automatically trustworthy evidence.
- Some evaluations depend on model-based judges and can be sensitive to answer wording.
- The current notebook stores facts better than it stores hypotheses, disagreements, or research strategy.
- The manager can still choose poor searches, repeat unproductive reasoning, or stop too early.
- The system has not yet demonstrated broad, open-ended research autonomy across real domains.

The full automated test suite passes (76 passed, 1 skipped on 2026-10-06), and the MCP-specific suite passed 53/53. An earlier scheduling-test failure turned out to be the tests and a live evaluation competing for the same network ports; the tests now use their own port range. Model scheduling still matters a great deal on this hardware: for example, raising context windows briefly pushed the team past the 14.5 GB VRAM budget and made workers swap on every task.

## What success would look like

Success is not simply a higher benchmark score. A successful Local Swarm would be able to receive a broad research objective and produce:

1. a sensible investigation plan;
2. a record of the sources it found and why they mattered;
3. competing explanations or hypotheses;
4. explicit treatment of conflicting evidence;
5. reproducible calculations or code-based analyses where appropriate;
6. a conclusion separated from speculation;
7. a clear confidence and uncertainty report; and
8. a trace showing how the conclusion was reached.

The project would be especially successful if a small local team could handle certain investigations that a single larger model tends to answer prematurely, hallucinate, or abandon.

## Current status

Local Swarm is beyond the proof-of-concept stage. It has a functioning runtime, user interface, local model pool, research tools, multiple collaboration architectures, evaluation harnesses, saved experimental results, a verifier benchmark, and a training-data pipeline.

It is not yet a finished autonomous research system. The project is currently in the transition from infrastructure building and architecture experiments toward a more explicit research-agent design.

The most important next steps are:

1. finish the multiple-attempts + vote experiment (identical vs diverse worker pairs);
2. freeze a small regression benchmark, and repeat key comparisons because one run varies by about 8 points;
3. make manager escalation cost-aware (solo first, the manager loop when needed, extra attempts only when answers disagree);
4. add hypothesis and contradiction tracking;
5. add deterministic checks for arithmetic, dates, units, and required answer parts;
6. test on open-ended research objectives rather than only fixed questions; and
7. use the saved traces to train smaller models to research, delegate, verify, and stop intelligently.

## Repository guide

- [README.md](../README.md) — quick-start overview
- [swarm/orchestrator.py](../swarm/orchestrator.py) — main research pipeline
- [swarm/manager.py](../swarm/manager.py) — coordinator-driven iterative research
- [swarm/notebook.py](../swarm/notebook.py) — shared-memory research mode
- [swarm/pool.py](../swarm/pool.py) — model loading, VRAM budgeting, and eviction
- [swarm/evidence.py](../swarm/evidence.py) — source cleaning, chunking, ranking, and citations
- [swarm/evals.py](../swarm/evals.py) — evaluation runner and reports
- [evals/configs.yaml](../evals/configs.yaml) — tested architecture configurations
- [swarm/training_pool.py](../swarm/training_pool.py) — training-pool construction and validation
- [MCP/research-mcp/HANDOFF.md](../MCP/research-mcp/HANDOFF.md) — research MCP design
- [docs/Model-Research-2026-10.md](Model-Research-2026-10.md) — model-selection research

