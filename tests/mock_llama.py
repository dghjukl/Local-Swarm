"""A stand-in for llama-server used by tests: same CLI flags, same HTTP API, canned answers.

Usage: python mock_llama.py -m <model.gguf> --port N [other llama-server flags ignored]
Set MOCK_LLAMA_FAIL=<substring of model path> to make that model fail to load.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

ap = argparse.ArgumentParser()
ap.add_argument("-m")
ap.add_argument("--port", type=int)
ap.add_argument("--host", default="127.0.0.1")
args, _ = ap.parse_known_args()

if os.environ.get("MOCK_LLAMA_FAIL") and os.environ["MOCK_LLAMA_FAIL"] in (args.m or ""):
    print("error: mock load failure", flush=True)
    sys.exit(1)

app = FastAPI()
MODEL = os.path.basename(os.path.dirname(args.m or "x/unknown"))


def reply(body: dict) -> str:
    rf = body.get("response_format") or {}
    schema = (rf.get("json_schema") or {}).get("schema") or rf.get("schema") or {}
    props = schema.get("properties", {})
    if not props and "verdicts-kv" in (body.get("grammar") or ""):  # a plain GBNF grammar (llm.chat gbnf=)
        props = {"verdicts": {}}
    user = body["messages"][-1]["content"]
    ids = re.findall(r"\[(E\d+)\]", user)
    if "mode" in props:
        direct = user.lower().startswith(("hi", "hello", "what is 2+2"))
        return json.dumps({"mode": "direct" if direct else "research",
                           "subquestions": ["When was the Eiffel Tower built?", "How tall is it?"],
                           "search_queries": ["Eiffel Tower history", "Eiffel Tower height"]})
    if user.startswith("<guardian>"):  # Granite Guardian: 'yes' if the claim mentions 1889
        claim = next((m["content"] for m in reversed(body["messages"]) if m["role"] == "assistant"), "")
        return "<think>\n</think>\n<score>" + ("yes" if "1889" in claim else "no") + "</score>"
    if "notes" in props and "open_questions" in props:  # notebook mode: running notes
        e1, e2 = (ids[0], ids[-1]) if ids else ("E99", "E99")
        notes = [{"fact": "The tower was completed in 1889.", "sources": [e1]},
                 {"fact": "A note without a real source.", "sources": ["E999"]},
                 {"fact": "Additional details from new passages", "sources": [e1]},   # filler: dropped
                 {"fact": "Who designed the Eiffel Tower in Paris?", "sources": [e1]}]  # a question: dropped
        if "Ministral" in MODEL:  # a fact only one worker found
            notes.insert(1, {"fact": "It stands about 330 metres tall today.", "sources": [e2]})
        return json.dumps({"notes": notes,
                           "open_questions": ["Who designed the tower?"]})
    if "worker" in props and "done" in props:  # manager mode: the coordinator picks the next step
        steps = len(re.findall(r"^\d+\. ", user.split("=== Steps so far ===")[-1], re.M))
        letters = props["worker"].get("enum", ["A"])
        if "nowhere" in user.split("=== Your evidence ===")[0]:  # a step that keeps failing
            if steps >= 3:
                return json.dumps({"thought": "give up", "done": True, "worker": letters[0], "task": "", "search": ""})
            return json.dumps({"thought": "try again", "done": False, "worker": letters[0],
                               "task": "Find the nowhere fact.", "search": "nowhere fact"})
        if "X" in letters and steps == 1:  # call the expert once
            return json.dumps({"thought": "stuck, ask the expert", "done": False, "worker": "X",
                               "task": "Find the official height of the Eiffel Tower.", "search": ""})
        if steps >= 2:
            return json.dumps({"thought": "enough", "done": True, "worker": letters[0], "task": "", "search": ""})
        who = letters[min(steps, len(letters) - 1)]
        return json.dumps({"thought": "need the height", "done": False, "worker": who,
                           "task": "Find how tall the Eiffel Tower is.", "search": "Eiffel Tower height"})
    if "ready" in props and "steps" in props:  # manager trust check: the chain the answer rests on
        e1 = ids[-1] if ids else "E1"
        again = "TRUST CHECK" in user          # a second check, after the team fixed the gaps
        steps = [{"claim": "The Eiffel Tower is about 330 metres tall.", "sources": [e1], "status": "supported"},
                 {"claim": "Its height in feet.", "sources": [], "status": "inferred" if again else "unsupported"},
                 {"claim": "A step citing a passage that doesn't exist.", "sources": ["E999"], "status": "supported"}]
        return json.dumps({"answer": "about 330 m", "steps": steps[:2] if again else steps,
                           "calc_expression": "2024 - 1987", "calc_result": "37" if again else "36",
                           "parts_answered": True, "gaps": "" if again else "height in feet not found",
                           "ready": True})
    if "best" in props and "same" in props:  # several attempts: the vote
        n = props["answers"].get("maxItems", 2)
        return json.dumps({"answers": [{"attempt": i + 1, "short": "330 metres"} for i in range(n)],
                           "same": "agree" in user.split("=== Attempt 1")[0], "best": min(2, n),
                           "reason": "mock vote"})
    if "said" in props and "next_search" in props:  # manager mode: a structured report (worker or expert)
        e1 = ids[-1] if ids else "E99"
        task = (re.findall(r"^Your task: (.*)$", user, re.M) or [""])[0]
        ok = "nowhere" not in task or "Qwen3.5-9B" in MODEL
        return json.dumps({"said": f"[{e1}] gives the height." if ok else "None of the passages mention it.",
                           "notes": [{"fact": "The Eiffel Tower stands about 330 metres tall.", "sources": [e1]}] if ok else [],
                           "result": f"{MODEL}: about 330 metres." if ok else "Not in these passages.",
                           "found": ok, "missing": "" if ok else "the fact itself",
                           "why_missing": "" if ok else "the passages are about something else",
                           "next_step": "Look up the official height page",
                           "next_search": "Eiffel Tower official height" if ok else "nowhere fact official",
                           "confidence": "high" if ok else "low", "confidence_reason": "stated directly"})
    if "found" in props and "result" in props and "notes" in props:  # manager mode: a teammate's task
        e1 = ids[-1] if ids else "E99"
        return json.dumps({"found": True, "result": f"{MODEL}: it is about 330 metres tall.",
                           "notes": [{"fact": f"The Eiffel Tower stands about 330 metres tall.", "sources": [e1]}]
                           + ([{"fact": "Gustave Eiffel's company designed and built the tower.", "sources": [e1]}]
                              if "Phi" in MODEL else [])})
    if "agree" in props and "new_notes" in props:  # notebook mode: review the shared notebook
        e1 = ids[0] if ids else "E99"
        return json.dumps({"agree": ["N1", "N2"], "dispute": [{"id": "N2", "reason": "mock disagreement"}]
                           if "Phi" in MODEL else [],
                           "new_notes": [{"fact": "Gustave Eiffel's company designed and built it.", "sources": [e1]}]})
    if "ok" in props and "problems" in props:  # notebook mode: review a teammate's draft
        bad = "LFM" in MODEL
        return json.dumps({"ok": not bad, "problems": ["The designer is missing."] if bad else []})
    thinking = (body.get("chat_template_kwargs") or {}).get("enable_thinking")
    if "answer" in props or (thinking and '"answer"' in body["messages"][0]["content"]):
        e1 = ids[0] if ids else "E99"
        extra = {"reasoning": "Path A: E1 says 1889. Path B agrees."} if "reasoning" in props else {}
        return json.dumps({**extra, "answer": f"{MODEL} says it was completed in 1889 [{e1}].",
                           "claims": [{"claim": "It was completed in 1889.", "evidence": [e1]},
                                      {"claim": "It is made of cheese.", "evidence": ["E999"]}],
                           "confidence": 0.8, "missing": ""})
    if "extracted_answer" in props:  # benchmark judge: right if the reference answer is in the response
        ref = user.split("Reference answer:")[1].split("\n")[0].strip()
        resp = user.split("Response:")[-1]
        ok = ref.lower() in resp.lower()
        return json.dumps({"extracted_answer": ref if ok else "something else",
                           "verdict": "correct" if ok else "incorrect", "reason": "mock"})
    if "must" in props and "must_not" in props:  # eval judge
        sec = user.split("MUST items:")[1] if "MUST items:" in user else ""
        must_txt, _, not_txt = sec.partition("MUST NOT items:")
        mn = re.findall(r"^(\d+)\. ", must_txt, re.M)
        nn = re.findall(r"^(\d+)\. ", not_txt, re.M)
        return json.dumps({
            "must": [{"n": int(n), "status": "met" if i else "partial", "reason": "mock"} for i, n in enumerate(mn)],
            "must_not": [{"n": int(n), "status": "ok", "reason": "mock"} for n in nn]})
    if "facts" in props:  # fact-sheet role
        e1 = ids[0] if ids else "E99"
        return json.dumps({"facts": [{"fact": "Completed in 1889", "evidence": [e1, "E999"]}],
                           "not_to_confuse": ["Blackpool Tower"]})
    if "premise_ok" in props:  # premise-check role
        bad = "moon" in user.lower()
        return json.dumps({"premise_ok": not bad, "problem": "No tower on the Moon" if bad else "",
                           "quote": "It was completed in 1889 as the entrance to the World's Fair" if bad else "",
                           "evidence": ids[:1]})
    if "reviews" in props:  # skeptic role: flag the first claim
        nums = re.findall(r"^(\d+)\. ", user.split("Claims:")[-1], re.M)
        return json.dumps({"reviews": [{"n": int(n), "issue": "overcertain" if i == 0 else "none",
                                        "fix": "Say 'about 1889'" if i == 0 else ""} for i, n in enumerate(nums)]})
    if "verdicts" in props:
        nums = re.findall(r"^(\d+)\. ", user, re.M)
        return json.dumps({"verdicts": [{"n": int(n), "verdict": "supported", "reason": "stated in passage"} for n in nums]})
    return f"The tower was completed in 1889 [E1] and is about 330 m tall [E2, E77]. ({MODEL})"


@app.post("/v1/rerank")
async def rerank(req: Request):
    """Reranker: score = share of query words found in the document (the 'broken' model scores 0)."""
    body = await req.json()
    q = set(re.findall(r"\w+", body["query"].lower()))
    res = []
    for i, d in enumerate(body["documents"]):
        words = set(re.findall(r"\w+", d.lower()))
        score = 0.0 if "Broken" in MODEL else (len(q & words) / max(1, len(q)) + 0.001 * i)
        res.append({"index": i, "relevance_score": score})
    res.sort(key=lambda x: -x["relevance_score"])
    return {"results": res[: body.get("top_n", len(res))]}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    text = reply(body)
    if not body.get("stream"):
        msg = {"role": "assistant", "content": text}
        if (body.get("chat_template_kwargs") or {}).get("enable_thinking"):
            msg["reasoning_content"] = "Let me look at the passages. E1 gives the date 1889, so that answers it."
        return JSONResponse({"choices": [{"message": msg}],
                             "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                             "timings": {"predicted_per_second": 123.0}})

    def gen():
        for i in range(0, len(text), 12):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": text[i:i + 12]}}]}) + "\n\n"
            time.sleep(0.005)
        yield "data: " + json.dumps({"choices": [], "timings": {"predicted_per_second": 99.0,
                                                                 "prompt_n": 300, "predicted_n": 40}}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    time.sleep(0.3)  # pretend to load
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
