#!/usr/bin/env python3
"""Compile a source snapshot in /tmp and publish the requested local PDF."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    config = json.loads((Path(os.environ.get('OVERLEAF_LOCAL_HOME', Path(__file__).parent)) / 'config.json').read_text())
    repo = Path(config['repo'])
    sources = {name: (repo / name).read_bytes() for name in config['files']}
    with tempfile.TemporaryDirectory(prefix='overleaf-paper-build-') as directory:
        root = Path(directory)
        for name, content in sources.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        env = dict(os.environ)
        if config.get('tex_bin'):
            env['PATH'] = config['tex_bin'] + ':' + env.get('PATH', '')
        log_path = root / 'compile.log'
        with log_path.open('w') as log:
            result = subprocess.run(
                ['latexmk', '-pdf', '-interaction=nonstopmode', '-halt-on-error', '-outdir=build', 'main.tex'],
                cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print(log_path.read_text()[-5000:])
            raise SystemExit(result.returncode)
        if any((repo / name).read_bytes() != content for name, content in sources.items()):
            raise SystemExit('Sources changed during compilation; PDF not published. Rerun the build.')
        for line in (root / 'build/main.log').read_text().splitlines():
            if any(term in line for term in ['Overfull', 'undefined', 'multiply defined', 'Float too large']):
                print(line)
        destination = repo / 'build/main.pdf'
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(root / 'build/main.pdf', destination)
        print(f'Built current sources: {destination}')


if __name__ == '__main__':
    main()
