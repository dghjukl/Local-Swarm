"""Start one tiny model on the GPU, ask it a question, shut it down."""
import subprocess
import sys
import time

import httpx

from swarm.paths import LLAMA_SERVER, LOGS, MODELS

PORT = 8190
MODEL = MODELS / "Qwen3-0.6B" / "Qwen3-0.6B-Q8_0.gguf"


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if not LLAMA_SERVER.exists():
        print("missing", LLAMA_SERVER)
        return 1
    ver = subprocess.run([str(LLAMA_SERVER), "--version"], capture_output=True, text=True)
    print("llama-server:", (ver.stdout + ver.stderr).strip().splitlines()[-2:])
    log = open(LOGS / "selftest-llama.log", "w", encoding="utf-8")
    t0 = time.time()
    proc = subprocess.Popen(
        [str(LLAMA_SERVER), "-m", str(MODEL), "--port", str(PORT), "--host", "127.0.0.1",
         "-ngl", "99", "-c", "4096", "--jinja"],
        stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        base = f"http://127.0.0.1:{PORT}"
        with httpx.Client(timeout=5) as c:
            for _ in range(120):
                try:
                    if c.get(base + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if proc.poll() is not None:
                    print("server exited early; see runtime/logs/selftest-llama.log")
                    return 1
                time.sleep(0.5)
            else:
                print("server never became healthy")
                return 1
        print(f"loaded in {time.time() - t0:.1f}s")
        t1 = time.time()
        r = httpx.post(base + "/v1/chat/completions", timeout=120, json={
            "messages": [{"role": "user", "content": "What is the capital of France? Answer in one word. /no_think"}],
            "max_tokens": 64, "temperature": 0,
        })
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        timings = data.get("timings", {})
        print("answer:", text.strip()[:200])
        print(f"reply in {time.time() - t1:.2f}s, gen tok/s: {timings.get('predicted_per_second', 0):.0f}")
        ok = "paris" in text.lower()
        print("SELFTEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
