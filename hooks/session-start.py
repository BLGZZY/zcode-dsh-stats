"""Official process hook. Always returns protocol JSON without reading prompt content."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_restore import DEFAULT_RUNTIME, hook_output, run
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    args, _ = parser.parse_known_args()
    result = hook_output(run(args.runtime))
except Exception as exc:
    # Plugin faults must not abort a user's session; no tracebacks or user content in stdout.
    result = hook_output({'state': 'repair-failed', 'reason': '自动检查失败：' + type(exc).__name__})
print(json.dumps(result, ensure_ascii=False))
