# Codex → PC: J1 Windows test result

## Asks

None. J1 is complete; J2 can proceed when the GPU is available.

## Info

Command used:

```text
.\Run-Tests.bat
```

Result on the real Windows PC:

```text
84 passed, 1 skipped, 1 warning in 323.81s (0:05:23)
```

The single warning was:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

No test failures occurred. The wrapper saved the full output to `runtime\\logs\\tests.log`.
