"""Exercise shared-code deployments without touching a real paper or Overleaf."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from configure import link_runtime


def main():
    skill = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    with tempfile.TemporaryDirectory(prefix='overleaf-shared-', dir='/tmp') as directory:
        root = Path(directory)
        deployments = []
        for name in ('alpha', 'beta'):
            repo = root / (name + '-paper')
            repo.mkdir()
            config = {'id': name, 'repo': str(repo), 'runtime': str(root / (name + '-runtime')),
                      'git_config': '/dev/null', 'python': sys.executable,
                      'files': ['main.tex'], 'remote': 'origin', 'branch': 'main',
                      'poll_seconds': 30, 'debounce_seconds': 3}
            deployment = root / name
            link_runtime(deployment, config)
            assert (deployment / 'repo').resolve() == repo
            assert (deployment / 'runtime').resolve() == skill / 'assets/runtime'
            assert len((deployment / 'sync.py').read_text().splitlines()) < 12
            subprocess.run([sys.executable, str(deployment / 'sync.py'), '--help'], env=env, check=True,
                           stdout=subprocess.DEVNULL)
            subprocess.run([sys.executable, str(deployment / 'package_extension.py')], env=env, check=True)
            Path(config['runtime']).mkdir()
            for command, denied in [('sed -n 1p ' + str(repo / 'main.tex'), False),
                                    ('rm ' + str(repo / 'main.tex'), True),
                                    ('rm /tmp/unrelated-file', False)]:
                event = {'hook_event_name': 'PreToolUse', 'tool_name': 'exec_command',
                         'tool_input': {'cmd': command}, 'cwd': str(root), 'session_id': name}
                result = subprocess.run([sys.executable, str(deployment / 'codex_hook.py')],
                                        input=json.dumps(event), text=True, capture_output=True,
                                        env=env, check=True)
                response = json.loads(result.stdout)
                assert (response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny') == denied
            deployments.append(deployment)
        first, second = deployments
        subprocess.run(['node', str(skill / 'scripts/regression_factory.js'), str(first), str(second)],
                       env=env, check=True)
        assert json.loads((first / 'config.json').read_text())['runtime'] != json.loads((second / 'config.json').read_text())['runtime']
        for script in ('regression.py', 'regression_guards.py'):
            subprocess.run([sys.executable, str(skill / 'scripts' / script), str(first)], env=env, check=True)
        for deployment in deployments:
            subprocess.run(['node', str(skill / 'scripts/regression_ui.js'), str(deployment), deployment.name],
                           env=env, check=True)
        print('PASS: two isolated deployments reuse one runtime; engine, guards and UI regressions passed')


if __name__ == '__main__':
    main()
