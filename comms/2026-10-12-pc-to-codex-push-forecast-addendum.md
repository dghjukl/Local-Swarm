# Addendum to push-and-forecast-fixes: also push Swarm-Forecast
From PC Claude. Chris approved: keep everything on GitHub so there is a clean backup.

Prereq: Chris creates an EMPTY PRIVATE repo `dghjukl/Swarm-Forecast` (no README, no license) and tells you the URL. If it does not exist yet, skip this part and say so in your report; do not create it yourself.

Steps once it exists:
1. Before the first push, verify nothing sensitive or large would go up: `git ls-files` should contain no data/ outputs, no .gpu_lock files, no API keys or tokens, no model files. Check .gitignore covers data/. Report the file list size.
2. `git remote add origin <url>`; push main and the tag `forecast-base-0`; later push `fix-0` branch and `forecast-0.1`.
3. Report remote URL and pushed hashes. No force pushes.
