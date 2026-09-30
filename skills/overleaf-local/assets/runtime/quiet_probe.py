#!/usr/bin/env python3
"""Bounded read-only probe reusing the synchronizer's remote observations."""
import json
from pathlib import Path

from sync import HOME, rpc

config = json.loads((HOME / 'config.json').read_text())
state = rpc(Path(config['runtime']) / 'service.sock', {'op': 'quiet'}, timeout=10)
print('PAPER_QUIET_READY' if state.get('ready') else 'PAPER_WAITING')
print(json.dumps(state))
