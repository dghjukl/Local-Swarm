"""Resolver test (plan step 4): a big model settles the questions where the team got stuck.

Works on a finished multi-attempt run. No new research is done: for each "stuck" question (the attempts
disagree, or no attempt passed the trust check) the resolver model gets the research packet - the
question, the evidence passages, and every attempt's answer, fact chain, trust verdict and citations -
and writes its own final answer. The answers go into a new eval folder next to the team's original
vote on the same questions, so both are graded by the same judge in the same pass:

    python -m swarm.resolver_bench make RUN --config mgr-scale8-trust --model Qwen3.6-35B-A3B --out runtime/evals/resolver-1
    python -m swarm.evals --regrade runtime/evals/resolver-1 --no-open
    python -m swarm.resolver_bench compare runtime/evals/resolver-1

The key numbers (compare): the RESCUE rate (stuck questions the vote got wrong and the resolver gets
right), the BREAK rate (vote right, resolver wrong) and the time per question.
`make` can be run again with other models into the same folder; each model becomes its own config, and
a question already answered by that model is skipped (so an interrupted run continues).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from swarm.selector_bench import group, no_answer, short_answers

BASELINE = "vote-baseline"

RESOLVER_SYSTEM = """You are the resolver for a small research team. Several independent attempts tried to \
answer the same question from the same kind of evidence, and they got stuck: their answers disagree, or \
none of them passed the team's trust check. Your job is to settle the question.

How to work:
- Do not count votes. Check each attempt's facts against the evidence passages and decide which facts \
are actually supported.
- Recompute any arithmetic, date or unit conversion yourself.
- Watch for attempts that answered a slightly different question, used an outdated fact, or skipped a step.
- You may agree with one attempt, combine facts from several, or reach a different answer if the \
evidence supports it.
- If the evidence is not enough, give the best-supported answer and say plainly what is uncertain.

Reply in this format:
FINAL ANSWER: <the short answer, one line>
WHY: <a few sentences: the chain of facts, each with its passage id like [E3], and any calculation>
UNCERTAIN: <what is not settled, or "nothing">"""


# ------------------------------------------------------------------ packet

def _clip(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def stuck_reason(shorts: list[str], ready: list) -> str | None:
    """Why the team counts as stuck on this question, or None when it is not (all attempts give one
    answer and at least one passed the trust check)."""
    split = len(group(shorts, list(range(len(shorts))))) > 1
    # a run without the trust check (every verdict None) is judged on agreement alone
    any_ready = any(bool(r) for r in ready) or all(r is None for r in ready)
    if split and not any_ready:
        return "split+not_ready"
    if split:
        return "split"
    if not any_ready:
        return "not_ready"
    return None


def build_packet(trace: dict, k: int, passage_chars: int = 900, max_chars: int = 60000) -> tuple[str, dict]:
    """The research packet for one question: evidence passages, then every attempt's work."""
    atts = (trace.get("attempts") or [])[:k]
    shorts = short_answers(trace.get("attempts") or [], trace.get("votes") or [])[:k]
    # passages: shared evidence first, then anything an attempt cited that is not in it
    passages: dict[str, dict] = {}
    by_url: dict[str, str] = {}

    def add(pid: str, url: str, title: str, text: str) -> str:
        url = url or ""
        if url and url in by_url:
            return by_url[url]
        key = pid
        if key in passages and passages[key]["url"] != url:
            n = 2
            while f"{pid}-{n}" in passages:
                n += 1
            key = f"{pid}-{n}"
        passages[key] = {"url": url, "title": title or "", "text": text or ""}
        if url:
            by_url[url] = key
        return key

    for e in (trace.get("evidence") or []) + (trace.get("evidence_found") or []):
        add(str(e.get("id") or f"E{len(passages) + 1}"), e.get("url", ""), e.get("title", ""), e.get("text", ""))
    att_blocks = []
    for i, a in enumerate(atts):
        idmap = {}
        for s in a.get("sources") or []:
            if isinstance(s, dict) and s.get("id"):
                idmap[s["id"]] = add(str(s["id"]), s.get("url", ""), s.get("title", ""), s.get("snippet", ""))
        m = a.get("manager") or {}
        trust = (m.get("trust") or [])
        last = trust[-1] if trust else {}
        lines = [f"### Attempt {i + 1}",
                 f"Short answer: {_clip(shorts[i] if i < len(shorts) else '', 300)}",
                 f"Trust check: {'READY' if last.get('ready') else ('not ready' if last else 'not run')}"]
        if last.get("problems"):
            lines.append("Trust-check problems: " + _clip("; ".join(map(str, last["problems"])), 400))
        steps = last.get("steps") or []
        if steps:
            lines.append("Fact chain:")
            for s in steps[:10]:
                ids = ", ".join(idmap.get(x, x) for x in (s.get("sources") or []))
                lines.append(f"- {_clip(s.get('claim'), 300)} [{s.get('status', '?')}{'; ' + ids if ids else ''}]")
        notes = m.get("notes") or []
        if notes and not steps:
            lines.append("Notebook facts:")
            for n in notes[:10]:
                ids = ", ".join(idmap.get(x, x) for x in (n.get("sources") or []))
                lines.append(f"- {_clip(n.get('fact'), 250)}{' [' + ids + ']' if ids else ''}")
        lines.append("Answer as written: " + _clip(a.get("answer"), 700))
        att_blocks.append("\n".join(lines))
    head = f"QUESTION: {trace.get('question', '')}\n\n"
    att_text = "## The attempts\n\n" + "\n\n".join(att_blocks)
    room = max(4000, max_chars - len(head) - len(att_text) - 200)
    ev_lines, used = [], 0
    for pid, p in passages.items():
        line = f"[{pid}] {_clip(p['title'], 120)} ({p['url']})\n{_clip(p['text'], passage_chars)}"
        if used + len(line) > room:
            break
        ev_lines.append(line)
        used += len(line) + 2
    packet = head + "## Evidence passages\n\n" + "\n\n".join(ev_lines) + "\n\n" + att_text
    info = {"attempts": len(atts), "passages": len(ev_lines), "passages_total": len(passages),
            "packet_chars": len(packet)}
    return packet, info


# ------------------------------------------------------------------ selecting the questions

def load_stuck(run: Path, config: str, k: int | None, only_stuck: bool = True) -> list[dict]:
    """Rows of `run` for `config`, each with its trace, why it is stuck, and the vote's answer."""
    out = []
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("config") != config or not r.get("trace"):
            continue
        try:
            t = json.loads((run / r["trace"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        atts = t.get("attempts") or []
        if len(atts) < 2:
            continue
        kk = min(k or len(atts), len(atts))
        shorts = short_answers(atts, t.get("votes") or [])[:kk]
        ready = [((a.get("manager") or {}).get("trust") or [{}])[-1].get("ready") for a in atts[:kk]]
        reason = stuck_reason(shorts, ready)
        if only_stuck and reason is None:
            continue
        out.append({"row": r, "trace": t, "k": kk, "reason": reason or "clear",
                    "answered": sum(not no_answer(s) for s in shorts)})
    return out


# ------------------------------------------------------------------ make

def _row(src: dict, config: str, desc: str, answer: str, seconds: float | None, extra: dict,
         model: str, error: str | None = None, tokens: dict | None = None) -> dict:
    return {"config": config, "config_description": desc, "question_id": src["question_id"],
            "question": src.get("question", ""), "repeat": 0, "mode": "resolver", "error": error,
            "answer": answer, "sources": [], "n_citations": 0,
            "stats": {"total_seconds": seconds, "tokens": tokens or {}}, "total_seconds": seconds,
            "peak_vram_mb": None, "coordinator": model, "team": [], "verifier": None, "workers": [],
            "trace": "", "evidence_web_pages": src.get("evidence_web_pages"), "resolver": extra}


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(path)


async def make(args) -> int:
    from swarm import llm
    from swarm.config import load_config
    from swarm.paths import repo_path
    from swarm.pool import ModelPool
    from swarm.registry import scan_models

    run, out = repo_path(args.run), repo_path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items = load_stuck(run, args.config, args.k, only_stuck=not args.all)
    if args.limit:
        items = items[: args.limit]
    meta_path = out / "meta.json"
    src_meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        **src_meta, "configs": [BASELINE], "resolver_of": {"run": str(args.run), "config": args.config},
        "live": False, "question_ids": None}
    cfg_name = args.name or f"resolver-{args.model}" + (f"-k{args.k}" if args.k else "") + ("-think" if args.think else "")
    if cfg_name not in meta["configs"]:
        meta["configs"].append(cfg_name)
    meta.setdefault("resolver", {})[cfg_name] = {"model": args.model, "k": args.k, "think": args.think,
                                                 "ctx": args.ctx, "max_chars": args.max_chars,
                                                 "only_stuck": not args.all}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    res_path = out / "results.jsonl"
    rows = _read_rows(res_path)
    have = {(r["config"], r["question_id"]) for r in rows}
    # the team's own answer on the same questions, graded in the same pass as the resolver
    for it in items:
        src = it["row"]
        if (BASELINE, src["question_id"]) not in have:
            rows.append(_row(src, BASELINE, f"the team's coordinator vote ({args.config})", src.get("answer", ""),
                             src.get("total_seconds"), {"reason": it["reason"], "k": it["k"]},
                             src.get("coordinator", ""), src.get("error")))
            have.add((BASELINE, src["question_id"]))
    _write_rows(res_path, rows)
    todo = [it for it in items if (cfg_name, it["row"]["question_id"]) not in have]
    print(f"{len(items)} stuck questions in {args.run} ({args.config}); {len(todo)} to resolve with {args.model}",
          flush=True)
    if not todo:
        return 0

    cfg = load_config()
    pool = ModelPool(cfg, scan_models())
    if args.model not in pool.cards:
        print(f"model '{args.model}' not found in Models/", flush=True)
        return 2
    try:
        async with pool.use(args.model, args.ctx, 1, pin=True) as url:
            for n, it in enumerate(todo, 1):
                src, t = it["row"], it["trace"]
                packet, info = build_packet(t, it["k"], max_chars=args.max_chars)
                info.update({"reason": it["reason"], "k": it["k"], "model": args.model})
                t0 = time.time()
                try:
                    res = await llm.chat(url, [{"role": "system", "content": RESOLVER_SYSTEM},
                                               {"role": "user", "content": packet}],
                                         max_tokens=args.max_tokens, temperature=0.2, think=args.think,
                                         timeout=args.timeout, final=True)
                    answer = llm.strip_think(res.text).strip()
                    err = None if answer else "resolver gave no answer"
                    toks = {"prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens}
                    info["reasoning_chars"] = len(res.reasoning or "")
                except Exception as e:  # keep going; the row records the failure
                    answer, err, toks = "", f"{type(e).__name__}: {e}"[:300], {}
                secs = round(time.time() - t0, 1)
                rows.append(_row(src, cfg_name, f"{args.model} resolves the stuck questions from the research packet",
                                 answer, secs, info, args.model, err, toks))
                _write_rows(res_path, rows)
                first = answer.splitlines()[0][:90] if answer else err
                print(f"  [{n}/{len(todo)}] {src['question_id']:<12} {secs:>6.0f}s  {first}", flush=True)
    finally:
        await pool.shutdown()
    return 0


# ------------------------------------------------------------------ compare

def compare(folder: Path) -> str:
    rows = _read_rows(folder / "results.jsonl")
    ok = lambda r: bool(r and (r.get("grade") or {}).get("score") is not None and r["grade"]["score"] >= 0.5)
    graded = lambda r: bool(r and (r.get("grade") or {}).get("score") is not None)
    base = {r["question_id"]: r for r in rows if r["config"] == BASELINE}
    configs = [c for c in dict.fromkeys(r["config"] for r in rows) if c != BASELINE]
    lines = [f"# Resolver test: {folder.name}", "",
             "Stuck questions only (attempts disagree and/or no attempt passed the trust check).",
             "Rescue = vote wrong, resolver right. Break = vote right, resolver wrong.", "",
             "| Config | Questions | Vote right | Resolver right | Rescued | Broken | Net | Avg seconds |",
             "|---|---|---|---|---|---|---|---|"]
    detail = []
    for c in configs:
        rs = [r for r in rows if r["config"] == c and graded(r) and graded(base.get(r["question_id"]))]
        if not rs:
            lines.append(f"| {c} | 0 (not graded yet: run swarm.evals --regrade on this folder) | | | | | | |")
            continue
        vr = sum(ok(base[r["question_id"]]) for r in rs)
        rr = sum(ok(r) for r in rs)
        resc = [r["question_id"] for r in rs if ok(r) and not ok(base[r["question_id"]])]
        brk = [r["question_id"] for r in rs if not ok(r) and ok(base[r["question_id"]])]
        secs = [r.get("total_seconds") for r in rs if r.get("total_seconds")]
        lines.append(f"| {c} | {len(rs)} | {vr} | {rr} | {len(resc)} | {len(brk)} | {len(resc) - len(brk):+d} | "
                     f"{(sum(secs) / len(secs)) if secs else 0:.0f} |")
        by_reason: dict[str, list[int]] = {}
        for r in rs:
            reason = (r.get("resolver") or {}).get("reason", "?")
            b = by_reason.setdefault(reason, [0, 0, 0])
            b[0] += 1
            b[1] += ok(base[r["question_id"]])
            b[2] += ok(r)
        detail.append(f"\n## {c}\n")
        detail.append("By why the team was stuck (questions / vote right / resolver right): " +
                      "; ".join(f"{k} {v[0]}/{v[1]}/{v[2]}" for k, v in sorted(by_reason.items())))
        detail.append(f"\nRescued: {', '.join(resc) or 'none'}")
        detail.append(f"\nBroken: {', '.join(brk) or 'none'}")
        errs = sum(1 for r in rows if r["config"] == c and r.get("error"))
        if errs:
            detail.append(f"\nErrors: {errs} questions had no resolver answer")
    text = "\n".join(lines) + "\n" + "\n".join(detail) + "\n"
    (folder / "resolver_report.md").write_text(text, encoding="utf-8")
    return text


def overall(folder: Path) -> str:
    """Whole-run accuracy if the resolver had answered every stuck question and the team's answer were
    kept on the clear ones. Clear questions use the vote's grade when all attempts were used, else the
    grade of attempt 1 (the attempts agree there, so that is what the team would answer)."""
    from swarm.paths import repo_path
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    src = meta.get("resolver_of") or {}
    rows = _read_rows(folder / "results.jsonl")
    ok = lambda g: bool(g) and g.get("score") is not None and g["score"] >= 0.5
    lines = ["| Resolver | k | Clear right | Stuck right | Overall | Team alone |", "|---|---|---|---|---|---|"]
    for c, info in (meta.get("resolver") or {}).items():
        k = info.get("k")
        items = load_stuck(repo_path(src["run"]), src["config"], k, only_stuck=False)
        res = {r["question_id"]: r for r in rows if r["config"] == c}
        base = {r["question_id"]: r for r in rows if r["config"] == BASELINE}
        clear_ok = stuck_ok = team_ok = n = 0
        for it in items:
            r = it["row"]
            n += 1
            if it["reason"] == "clear":
                g = r.get("grade") if not k else (r.get("attempt_grades") or [None])[0]
                clear_ok += ok(g)
                team_ok += ok(r.get("grade"))
            else:
                stuck_ok += ok((res.get(r["question_id"]) or {}).get("grade"))
                team_ok += ok((base.get(r["question_id"]) or r).get("grade"))
        lines.append(f"| {c} | {k or 'all'} | {clear_ok} | {stuck_ok} | {100 * (clear_ok + stuck_ok) / max(1, n):.0f}% "
                     f"| {100 * team_ok / max(1, n):.0f}% |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="resolve the stuck questions of a run with one model")
    m.add_argument("run")
    m.add_argument("--config", required=True)
    m.add_argument("--model", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--name", help="config name for this resolver (default resolver-<model>)")
    m.add_argument("--k", type=int, help="use only the first k attempts (default: all)")
    m.add_argument("--all", action="store_true", help="every question, not only the stuck ones")
    m.add_argument("--limit", type=int)
    m.add_argument("--think", action="store_true")
    m.add_argument("--ctx", type=int, default=24576)
    m.add_argument("--max-chars", type=int, default=60000)
    m.add_argument("--max-tokens", type=int, default=1500)
    m.add_argument("--timeout", type=float, default=900)
    c = sub.add_parser("compare", help="rescue / break table for a graded resolver folder")
    c.add_argument("folder")
    o = sub.add_parser("overall", help="whole-run accuracy with the resolver on the stuck questions")
    o.add_argument("folder")
    s = sub.add_parser("count", help="how many questions of a run count as stuck (no GPU)")
    s.add_argument("run")
    s.add_argument("--config", required=True)
    s.add_argument("--k", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "make":
        return asyncio.run(make(args))
    if args.cmd == "compare":
        from swarm.paths import repo_path
        print(compare(repo_path(args.folder)))
        return 0
    from swarm.paths import repo_path
    if args.cmd == "overall":
        print(overall(repo_path(args.folder)))
        return 0
    items = load_stuck(repo_path(args.run), args.config, args.k, only_stuck=False)
    stuck = [i for i in items if i["reason"] != "clear"]
    ok = lambda r: (r.get("grade") or {}).get("score", 0) >= 0.5
    print(f"{len(items)} questions, {len(stuck)} stuck "
          f"(vote right on {sum(ok(i['row']) for i in stuck)} of them; "
          f"clear ones right {sum(ok(i['row']) for i in items if i['reason'] == 'clear')}/{len(items) - len(stuck)})")
    sizes = sorted(build_packet(i["trace"], i["k"])[1]["packet_chars"] for i in stuck) or [0]
    print(f"packet chars: median {sizes[len(sizes) // 2]}, max {sizes[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
