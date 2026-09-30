#!/usr/bin/env python3
"""Host-side entry point; codex-wake owns calibration and same-thread delivery."""
import argparse
import json
import shlex
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--session-id', default=os.environ.get('CODEX_THREAD_ID'), required=False)
parser.add_argument('--prompt', required=True)
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.session_id:
    parser.error('A root Codex thread ID is required')
home = Path(__file__).resolve().parent
config = json.loads((home / 'config.json').read_text())
wake_root = Path(config['codex_wake'])
command = [str(wake_root / 'scripts/start_watch.sh'), 'start',
           '--name', 'paper-' + config['id'] + '-quiet-' + args.session_id, '--session-id', args.session_id,
           '--probe-key', 'overleaf-synchronized-quiet-status',
           '--probe-command', shlex.join([config['python'], str(home / 'quiet_probe.py')]),
           '--match', '^PAPER_QUIET_READY$', '--probe-timeout', '12', '--prompt', args.prompt]
if args.dry_run:
    command.append('--dry-run')
raise SystemExit(subprocess.call(command))
