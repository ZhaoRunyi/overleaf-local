import argparse
import atexit
import shutil
import base64
import importlib.util
import json
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading

parser = argparse.ArgumentParser()
parser.add_argument('deployment', type=Path)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('paper_sync', args.deployment / 'sync.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(tempfile.mkdtemp(prefix='paper-sync-tests-', dir='/tmp'))
atexit.register(shutil.rmtree, root, ignore_errors=True)
results = []
def git(directory, *args):
    result = subprocess.run(['git', '-C', str(directory), *args], capture_output=True, check=True)
    return result.stdout.decode().strip()
def identity(repo):
    git(repo, 'config', 'user.name', 'Paper test')
    git(repo, 'config', 'user.email', 'test@localhost')
def setup(name, editor=True):
    directory = root / name
    directory.mkdir()
    remote = directory/'remote.git'
    git(directory, 'init', '--bare', '--initial-branch=main', str(remote))
    local = directory/'local'
    web = directory/'web'
    git(directory, 'clone', str(remote), str(local))
    identity(local)
    (local/'main.tex').write_text('title\n\nintro\n\nmethod\n\nresults\n\nconclusion\n')
    (local/'image.pdf').write_bytes(b'%PDF\x00original')
    git(local, 'add', '.')
    git(local, 'commit', '-m', 'initial')
    git(local, 'push', '-u', 'origin', 'main')
    git(directory, 'clone', str(remote), str(web))
    identity(web)
    runtime = directory/'run'
    synchronizer = module.Synchronizer({'repo': str(local), 'runtime': str(runtime), 'files': ['main.tex','image.pdf'],
                                       'git_config':'/dev/null', 'remote':'origin', 'branch':'main', 'poll_seconds':30, 'debounce_seconds':3})
    state = {'dirty': [], 'race': False}
    if editor:
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                request = json.loads(self.rfile.readline())
                if request['op'] == 'status':
                    response = {'repo': str(local), 'dirty': state['dirty']}
                else:
                    if state['race']:
                        (local/'main.tex').write_text('concurrent save\n')
                    response = {'ok': True}
                    for item in request['changes']:
                        path = local/item['path']
                        if path.read_bytes() != base64.b64decode(item['before']):
                            response = {'ok': False, 'error':'Changed since merge'}
                            break
                    if response['ok']:
                        for item in request['changes']:
                            (local/item['path']).write_bytes(base64.b64decode(item['after']))
                self.wfile.write(json.dumps(response).encode()+b'\n')
        server = socketserver.ThreadingUnixStreamServer(str(runtime/'editor-test.sock'), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return synchronizer, local, web, state
def change(repo, old, new):
    file = repo/'main.tex'
    file.write_text(file.read_text().replace(old,new))
def push(web):
    git(web, 'add', '.')
    git(web, 'commit', '-m', 'web edit')
    git(web, 'push', 'origin', 'main')
def check(label, actual):
    assert actual, label
    results.append(label)

s,l,w,state = setup('roundtrip')
(l/'.git/info/exclude').write_text('*\n')
check('unchanged sync', s.sync()['state']=='synced')
change(l,'title','local title')
check('local save automatically committed and pushed with strict excludes', s.sync()['state']=='synced')
git(w,'pull','--ff-only')
check('remote receives local content','local title' in (w/'main.tex').read_text())
change(w,'conclusion','web conclusion')
push(w)
check('pre-edit refuses stale local version', not s.check(pre_edit=True)['allowed'])
check('remote update through editor', s.sync()['state']=='synced')
check('local receives remote content', 'web conclusion' in (l/'main.tex').read_text())
check('pre-edit allows synchronized clean editor', s.check(pre_edit=True)['allowed'])

s,l,w,state = setup('concurrent')
change(l,'title','local title')
change(w,'conclusion','web conclusion')
push(w)
check('three-way nonoverlap merge', s.sync()['state']=='synced')
check('both edits retained', 'local title' in (l/'main.tex').read_text() and 'web conclusion' in (l/'main.tex').read_text())

s,l,w,state = setup('conflict')
change(l,'title','local title')
change(w,'title','web title')
push(w)
check('overlapping edits pause', s.sync()['state']=='conflict')
check('no conflict markers in manuscript', '<<<<<<<' not in (l/'main.tex').read_text())
check('both conflict sides preserved', 'local title' in (l/'main.tex').read_text() and 'web title' in git(w,'show','HEAD:main.tex'))
check('persistent conflict survives restart', module.Synchronizer(s.config).sync()['state']=='conflict')
check('resolution requires confirmation', s.handle({'op':'resolve'})['state']=='waiting')
(l/'main.tex').write_text((l/'main.tex').read_text().replace('local title','reviewed local and web title'))
check('explicit reviewed merge resolution publishes', s.handle({'op':'resolve','accept_current_resolution':True})['state']=='synced')
git(w,'pull','--ff-only')
check('resolved remote contains reviewed content','reviewed local and web title' in (w/'main.tex').read_text())

s,l,w,state = setup('dirty')
state['dirty'] = [str(l/'main.tex')]
change(w,'title','remote title')
push(w)
check('unsaved buffer blocks remote apply', s.sync()['state']=='waiting')
check('working file untouched for dirty editor', (l/'main.tex').read_text().startswith('title'))
state['dirty'] = []
check('save unblocks sync', s.sync()['state']=='synced')

s,l,w,state = setup('missing-editor', editor=False)
change(w,'title','remote title')
push(w)
check('missing editor safely defers pull', s.sync()['state']=='waiting')
check('pre-edit requires editor protection', not s.check(pre_edit=True)['allowed'])

s,l,w,state = setup('save-race')
change(w,'title','remote title')
push(w)
state['race'] = True
check('new local save blocks stale apply', s.sync()['state']=='waiting')
check('concurrent save preserved', (l/'main.tex').read_text()=='concurrent save\n')

s,l,w,state = setup('unknown-remote')
(w/'unknown.txt').write_text('unexpected')
push(w)
check('unknown remote file stops sync', s.sync()['state']=='waiting')
check('unknown file not copied locally', not (l/'unknown.txt').exists())

s,l,w,state = setup('private-local')
(l/'private.txt').write_text('not for upload')
check('untracked file is excluded', s.sync()['state']=='synced')
git(l,'add','private.txt')
check('unapproved staged file blocks entire commit', s.sync()['state']=='waiting')
check('private file never uploaded','private.txt' not in git(w,'ls-tree','-r','--name-only','HEAD'))

s,l,w,state = setup('offline')
url=git(l,'remote','get-url','origin')
git(l,'remote','set-url','origin',str(root/'missing.git'))
change(l,'title','offline title')
check('offline reported', s.sync()['state']=='error')
check('offline edit preserved', 'offline title' in (l/'main.tex').read_text())
check('offline pre-edit denied', not s.check(pre_edit=True)['allowed'])
git(l,'remote','set-url','origin',url)
check('connection recovery syncs saved edits', s.sync()['state']=='synced')

s,l,w,state = setup('binary-conflict')
(l/'image.pdf').write_bytes(b'%PDF\x00local')
(w/'image.pdf').write_bytes(b'%PDF\x00web')
push(w)
check('binary conflict pauses', s.sync()['state']=='conflict')
check('local binary not replaced', (l/'image.pdf').read_bytes()==b'%PDF\x00local')

s,l,w,state = setup('delete-modify')
(l/'main.tex').unlink()
change(w,'title','remote title')
push(w)
check('deletion requires explicit review', s.sync()['state']=='waiting')
check('deleted local not recreated silently', not (l/'main.tex').exists())

s,l,w,state = setup('push-race')
original=s.git
raced=False
def racing(*args, **kwargs):
    global raced
    if args[0]=='push' and not raced:
        raced=True
        change(w,'conclusion','racing web conclusion')
        push(w)
    return original(*args, **kwargs)
s.git=racing
change(l,'title','local title')
check('push race refuses overwrite', s.sync()['state']=='retry')
check('push race retry merges', s.sync()['state']=='synced')
check('racing web content retained','racing web conclusion' in (l/'main.tex').read_text())

report={'checks_passed':len(results),'checks':results,'scope':'Production sync engine against disposable local Git remotes and a test editor adapter','temporary_fixture_removed_on_exit':True}
print(json.dumps(report,indent=2))
(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
