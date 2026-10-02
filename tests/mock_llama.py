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
