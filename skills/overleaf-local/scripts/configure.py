#!/usr/bin/env python3
"""Generate an isolated deployment; never publish, install, or modify the paper."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def main():
    codex_home = Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True, help='Unique short lowercase project name')
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='New directory outside the paper repository')
    parser.add_argument('--files', required=True, type=Path, help='JSON list of approved repository-relative files')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--git-config', type=Path, default=Path(os.environ.get('GIT_CONFIG_GLOBAL', Path.home()/'.gitconfig')))
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument(
        '--codex-wake',
        type=Path,
        default=Path(os.environ.get('CODEX_WAKE_SKILL_ROOT', codex_home/'skills/codex-wake')),
    )
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,29}', args.id):
        parser.error('id must be a short lowercase slug')
    repo, out = args.repo.resolve(), args.out.resolve()
    if not (repo/'.git').is_dir():
        parser.error('Use a normal dedicated Git clone, not a worktree/submodule or non-repository')
    if out.exists() or out.is_relative_to(repo):
        parser.error('out must be new and outside the paper repository')
    files = json.loads(args.files.read_text())
    if not isinstance(files, list) or not files or any(not isinstance(name, str) for name in files):
        parser.error('files must be a nonempty JSON string list')
    if len(set(files)) != len(files):
        parser.error('duplicate allowlist entries')
    for name in files:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
            parser.error('allowlist paths must stay inside the repository')
        file = repo / name
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(repo):
            parser.error(f'Invalid file: {name}')
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(args.git_config.resolve()))
    tracked = subprocess.check_output(['git','-C',str(repo),'ls-files','-z'], env=env).decode().rstrip('\0').split('\0')
    if set(tracked) != set(files):
        parser.error('Reconcile tracked files with the approved allowlist first; no files will be staged automatically')
    actual_branch = subprocess.check_output(['git','-C',str(repo),'branch','--show-current'], env=env).decode().strip()
    if actual_branch != args.branch:
        parser.error('Configured branch must match the checked-out branch')
    subprocess.check_output(['git', '-C', str(repo), 'remote', 'get-url', args.remote], env=env)
    python = shutil.which(args.python)
    if python is None:
        parser.error('Python executable not found')
    runtime = Path('/tmp') / f'overleaf-local-{os.getuid()}-{args.id}'
    if runtime.exists():
        parser.error('Runtime ID already exists; inspect it rather than creating a second deployment')
    template = Path(__file__).resolve().parents[1]/'assets/runtime'
    shutil.copytree(template, out)
    for file in out.rglob('*'):
        if file.is_file():
            file.write_text(file.read_text().replace('__PROJECT__', args.id))
    config = {'id':args.id, 'repo':str(repo), 'remote':args.remote, 'branch':args.branch,
              'runtime':str(runtime), 'git_config':str(args.git_config.resolve()),
              'python':str(Path(python).resolve()), 'codex_wake':str(args.codex_wake.resolve()),
              'poll_seconds':30, 'debounce_seconds':3, 'files':files}
    (out/'config.json').write_text(json.dumps(config, indent=2)+'\n')
    (out/'extension/deployment.json').write_text(json.dumps({'home':str(out)})+'\n')
    hook_command = f'PYTHONDONTWRITEBYTECODE=1 {shlex.join([config["python"], str(out/"codex_hook.py")])}'
    hooks = {'hooks':{kind:[{'matcher':'Bash|exec_command|apply_patch|Edit|Write', 'hooks':[
        {'type':'command','command':hook_command,'timeout':100,
         'statusMessage':f'Checking Overleaf synchronization ({args.id})'}]}]
        for kind in ['PreToolUse','PostToolUse']}}
    (out/'hooks.fragment.json').write_text(json.dumps(hooks, indent=2)+'\n')
    subprocess.run([config['python'], str(out/'package_extension.py')], check=True)
    print(json.dumps({'deployment':str(out), 'config':str(out/'config.json'),
        'vsix':f'/tmp/overleaf-local-{args.id}.vsix', 'hooks_fragment':str(out/'hooks.fragment.json'),
        'started':False, 'paper_modified':False}, indent=2))


if __name__ == '__main__':
    main()
