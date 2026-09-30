#!/usr/bin/env python3
"""Scoped guardrail for Codex paper edits; unrelated projects are unaffected."""
import json
import os
from pathlib import Path
import re
import sys
import time

from sync import HOME, rpc

config = json.loads((HOME / 'config.json').read_text())
repo = Path(config['repo'])
allowed = {repo / name for name in config['files']}
runtime = Path(config['runtime'])


def changed_source(event, reason):
    session = re.sub(r'[^A-Za-z0-9_-]', '_', event.get('session_id', 'unknown'))
    path = runtime / ('codex-retries-' + session + '.json')
    record = json.loads(path.read_text()) if path.exists() else {}
    turn = event.get('turn_id', 'unknown')
    previous = record.get('count', 0)
    count = previous if record.get('turn') == turn or previous >= 10 else 0
    count += 1
    path.write_text(json.dumps({'turn': turn, 'count': count}))
    if count >= 10:
        return ('Paper changed during 10 edit checks. Stop retrying this turn. Use the codex-wake skill and '
                f'{HOME / "arm_quiet_watch.py"} with this session ID '
                'and a task-specific continuation prompt. End the turn after reporting wake readiness. '
                'Resume only after 90 seconds of observed remote stability, synchronization, and rereading. '
                'Do not disable sync or apply a stale patch.')
    return reason + f' (source-change check {count}/10)'


def decide(event):
    tool = event.get('tool_name', '')
    payload = event.get('tool_input', {})
    if isinstance(payload, str):
        command = payload
    else:
        command = payload.get('command', payload.get('cmd', payload.get('input', '')))
    if not isinstance(command, str):
        return None
    cwd = Path(event.get('cwd') or str(repo))
    patch = tool in ('apply_patch', 'Edit', 'Write')
    touched = []
    if patch:
        for name in re.findall(r'^\*\*\* (?:Update File|Add File|Delete File|Move to): (.+)$', command, re.M):
            path = Path(name)
            touched.append(path if path.is_absolute() else cwd / path)
        if isinstance(payload, dict):
            for key in ('file_path', 'path'):
                if isinstance(payload.get(key), str):
                    path = Path(payload[key])
                    touched.append(path if path.is_absolute() else cwd / path)
        scoped = any(path.resolve() in allowed for path in touched)
    else:
        cwd_scoped = cwd == repo or cwd.is_relative_to(repo)
        scoped = (str(repo) in command or
                  (cwd_scoped and any(name in command for name in config['files'])))
    if not scoped:
        return None
    with (runtime / 'hook-audit.jsonl').open('a') as audit:
        audit.write(json.dumps({'time': time.time(), 'event': event.get('hook_event_name'),
                                'tool': tool, 'session': event.get('session_id')}) + '\n')
    event_name = event.get('hook_event_name')
    session = re.sub(r'[^A-Za-z0-9_-]', '_', event.get('session_id', 'unknown'))
    marker = runtime / ('codex-read-' + session + '.json')
    read_only = tool in ('Bash', 'exec_command') and bool(re.search(r'\b(cat|sed|rg|head|tail|git diff|git show)\b', command))
    suspicious = bool(re.search(r'(?:\b(python\d*|perl|ruby|node|tee|cp|mv|rm|apply_patch)\b|sed\s+-[^\s]*i|(?<![<>])[>](?![>]))', command))
    if event_name == 'PostToolUse':
        if read_only and not suspicious:
            state = rpc(runtime / 'service.sock', {'op': 'status'}, timeout=3)
            if state.get('state') == 'synced':
                marker.write_text(json.dumps({'head': state.get('head')}))
        elif patch:
            rpc(runtime / 'service.sock', {'op': 'sync'}, timeout=85)
        return None
    if not patch:
        if read_only and not suspicious:
            return None
        return 'Use apply_patch for manuscript changes after reading the synchronized source; shell writes are not covered by this paper guard.'
    retries = runtime / ('codex-retries-' + session + '.json')
    if retries.exists() and json.loads(retries.read_text()).get('count', 0) >= 10:
        quiet = rpc(runtime / 'service.sock', {'op': 'quiet'}, timeout=10)
        if not quiet.get('ready'):
            return changed_source(event, 'Remote manuscript is still active')
        retries.unlink()
    state = rpc(runtime / 'service.sock', {'op': 'pre-edit'}, timeout=85)
    if not state.get('allowed'):
        if state.get('behind', 0):
            return changed_source(event, state.get('message', 'Remote source changed'))
        return state.get('message', 'Paper is not synchronized')
    if not marker.exists() or json.loads(marker.read_text()).get('head') != state.get('head'):
        reason = 'The manuscript changed since this session last read it. Read the current main.tex, then reconstruct the patch.'
        return changed_source(event, reason) if marker.exists() else reason
    retries.unlink(missing_ok=True)
    return None


def main():
    event = json.load(sys.stdin)
    try:
        reason = decide(event)
    except Exception as error:
        reason = f'Paper sync guard unavailable ({type(error).__name__}); do not edit the manuscript until synchronization is checked.'
    if reason and event.get('hook_event_name') == 'PreToolUse':
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                          'permissionDecision': 'deny', 'permissionDecisionReason': reason}}))
    else:
        print('{}')


if __name__ == '__main__':
    main()
