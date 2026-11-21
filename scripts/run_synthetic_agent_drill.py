from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', message=r'Using `httpx` with `starlette\.testclient` is deprecated;.*')
    from nexus.agent_drill import main

if __name__ == '__main__':
    raise SystemExit(main())
