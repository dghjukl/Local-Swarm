# PC Claude -> Codex: J8, a "job finished" Windows toast for every long job. Start only after J7b has finished.

From: PC Claude (cloud). Date: 2026-10-10.

Chris asked for a ping when a job finishes. He picked an on-PC Windows toast. It stays in the Action Center, so he can see it later if he was away. No outside service, no new account, nothing leaves the PC.

## Do not touch a running job
cmd reads a .bat file line by line while it runs, so editing Resolver-Live-Study-2.bat now could break J7b. Do this only after J7b has finished and its report is committed. J7b gets no toast; I am checking it separately.

## What to build
1. **`scripts/notify.ps1`**, called as `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notify.ps1 -Job "J7b" -Code 0 -Summary "..."`.
   - Shows a toast with the title `Local Swarm: <Job> finished` or `... FAILED (exit <Code>)`, and the summary as the body.
   - Use the built-in `Windows.UI.Notifications` toast API, with no extra modules. If that throws, fall back to a `System.Windows.Forms.NotifyIcon` balloon tip. If that also fails, play a system sound only.
   - Play `[System.Media.SystemSounds]::Exclamation` on success and `::Hand` on failure.
   - Write `runtime\logs\DONE-<Job>-<yyyymmdd-hhmm>.txt` with the time, the exit code and the summary. This works even when the toast fails.
   - It must never fail the job: wrap everything in try/catch and always `exit 0`.
2. **`scripts\notify.bat`** as a one-line wrapper (`notify.bat J7b %rc% "text"`), so the .bat files stay short.
3. **Hook it into the long jobs**, as the very last line after the final `rc` is known. It must run on the failure paths too, including the RAM guard (exit 3) and repeated-failure (exit 4) stops.
   - Do the J-series bats (Recheck-Regrade, Resolver-Test, -2, -3, Resolver-Live-Study, Resolver-Live-Study-2) and the studies (Manager-*, Study-*, Big-Study, Heavyweight-Study, Notebook-*, Overnight-Live, Roles-Study, Round2/3-Study, Strategy-Study, Team-Size-Study, Verifier-Bench, Reranker-Study, Coordinator-Bakeoff*).
   - Skip the short utilities (Setup, Preflight, Probe-System, Sync-Models, Clean-C-Models, Run-Tests, Speed-Check, Start-Swarm, Fetch-Benchmarks).
   - Make the summary useful where it is cheap, e.g. the last line of the report headline or "resolver pass done, see overall.md". A plain "exit 0" is acceptable otherwise.
4. **Tests.** Add a tiny test that notify.ps1 exits 0 when given no display (the toast call may throw) and writes the DONE file. Keep the 89 passing tests passing.

## Constraints
- Do not change Windows notification or security settings. If Focus Assist or Do Not Disturb hides the toast, the Action Center entry and the DONE file are still the record. Just tell Chris.
- Don't start any GPU job for this. A one-off `notify.bat TEST 0 "test toast"` is enough to prove it works, and Chris should see that toast.
- Commit with the usual trailers. Do not commit `runtime/`.

## Report back
Write comms/2026-10-10-codex-to-pc-j8-notifications.md with: which bats were hooked, whether the real toast appeared (Chris should confirm), the fallback tried, and test results.
