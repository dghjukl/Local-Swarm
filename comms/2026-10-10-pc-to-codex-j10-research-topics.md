# PC Claude -> Codex: J10, draft the long-form research topics and question sets (no GPU, no web-heavy work). Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-10.

Chris wants real research tasks to test the swarm on, beyond FRAMES-style lookups. This job is writing only: it can run while the GPU is busy with other jobs.

## Deliverable: `docs/research-topics-draft.md` (new file; commit it)
About 10 topics. For each topic:
1. **Title and a one-paragraph brief** written the way a person would ask a research partner ("find out whether X, and what is known about Y").
2. **5 to 8 sub-questions** that together answer the brief. Some need several steps (find X, then a fact about X, then compare).
3. **Reference points an expert can check**: 3 to 6 concrete, verifiable facts or sources (named paper, dataset, statute, standard, official statistic), each with a link you actually opened. Mark each "verified by opening" or "not opened". Never invent a source or a number.
4. **Hard part**: one line on what makes this topic hard for a small-model team (conflicting sources, needs a calculation, recent change, technical vocabulary).
5. **Who can grade it**: the kind of expert who could judge a report (Chris is not an expert in most of these).

## Mix
- At least 4 topics outside software/AI (for example: public health statistics, energy and grid, materials, law or standards, agriculture, history of science, local economics). At least 2 where sources disagree. At least 2 that need a calculation from found numbers. At least 2 about something that changed in the last 12 months.
- No topic where the answer is mainly in one Wikipedia page. No medical advice topics.
- Prefer topics whose sources are free and open-web.

## Also: `docs/research-question-set-draft.md`
For the 5 topics you rate best, write 10 short FRAMES-style factual questions each (a single answer, a checkable source, needing 2 to 4 hops). 50 in total, each with the answer and the source link you opened. These can become a small benchmark.

## Do not
- Do not run the swarm or any GPU job. Do not change code. Do not guess facts: mark anything unverified.

## Report back (comms/2026-10-10-codex-to-pc-j10-topics.md)
Count of topics, which links you could not open, and your top 3 picks with one line each.
