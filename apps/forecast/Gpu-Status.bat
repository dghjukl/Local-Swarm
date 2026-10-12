@echo off
python -c "from swarm_forecast.gpu_lock import status; import json; print(json.dumps(status(), indent=2))"
