"""Start the serialized project daemon; the daemon lock prevents duplicate workers."""
import json
import os
from pathlib import Path
import subprocess

home = Path(__file__).resolve().parent
config = json.loads((home/'config.json').read_text())
runtime = Path(config['runtime'])
runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
runtime.chmod(0o700)
env = dict(os.environ, GIT_CONFIG_GLOBAL=config['git_config'], GIT_TERMINAL_PROMPT='0',
           PYTHONDONTWRITEBYTECODE='1')
env.pop('GIT_ASKPASS', None)
env.pop('SSH_ASKPASS', None)
subprocess.run(['screen','-dmS','overleaf-local-'+config['id'],config['python'],'-u',str(home/'sync.py'),'serve'],
               env=env, check=True)
