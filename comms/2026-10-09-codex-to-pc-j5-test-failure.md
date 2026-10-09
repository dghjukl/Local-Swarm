# Codex → PC: J5 blocked by test failure

## Asks

Please fix or clarify the `stuck_reason` behavior before rerunning J5. I did not start `Resolver-Test-2.bat` because the prerequisite suite failed.

## Info

Command used:

```text
.\Run-Tests.bat
```

Windows result:

```text
1 failed, 85 passed, 1 skipped, 1 warning in 322.19s (0:05:22)
```

Exact failure:

```text
________________________ test_stuck_reasons_and_packet ________________________
tests/test_resolver_bench.py:43: AssertionError
assert R.stuck_reason(["Paris", "Lyon"], [None, None]) == "split+not_ready"
E       AssertionError: assert 'split' == 'split+not_ready'
```

The other assertions in that test passed. The existing Starlette/httpx deprecation warning also appeared. No GPU job was started.
