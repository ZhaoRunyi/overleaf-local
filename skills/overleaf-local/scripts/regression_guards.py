import runpy
from pathlib import Path
import time

env = runpy.run_path(str(Path(__file__).with_name('regression.py')))
setup, change, push, git = (env[key] for key in ('setup', 'change', 'push', 'git'))
s, local, web, state = setup('quiet-owner')
assert s.sync()['state']=='synced'
assert not s.quiet()['ready']
s.remote_stable_since = time.time() - 91
assert s.quiet()['ready']
s.last_fetch = time.time() - 70
assert not s.quiet()['ready']
s.fetch()
assert not s.quiet()['ready']
s.remote_stable_since = time.time() - 91
change(web, 'title', 'changed remote')
push(web)
s.fetch()
assert not s.quiet()['ready']
assert s.sync()['state']=='synced'
original = s.editors
editors = original()
editors.append((s.runtime/'editor-other.sock', {'repo':str(local), 'dirty':[]}))
s.editors = lambda: editors
assert s.check(pre_edit=True)['allowed']
assert s.check(pre_edit=True)['allowed']
editors[1][1]['dirty']=['main.tex']
assert not s.check(pre_edit=True)['allowed']
assert not s.quiet()['ready']
editors[1][1]['dirty']=[]
s.editors=original

s, local, web, state = setup('multi-window-apply')
editors = s.editors()
peer = s.runtime/'editor-peer.sock'
editors.append((peer, {'repo':str(local), 'dirty':[], 'validate_updates':True}))
s.editors=lambda: editors
module = env['module']
original_rpc=module.rpc
peer_checks=[]
refuse=[True]
def peer_rpc(path, payload, **kwargs):
    if path==peer:
        peer_checks.append(payload['op'])
        return {'ok':not refuse[0], 'error':'Other buffer changed'}
    return original_rpc(path,payload,**kwargs)
module.rpc=peer_rpc
change(web,'title','multi-window remote title')
push(web)
assert s.sync()['state']=='waiting'
assert (local/'main.tex').read_text().startswith('title')
refuse[0]=False
assert s.sync()['state']=='synced'
assert (local/'main.tex').read_text().startswith('multi-window remote title')
assert peer_checks==['check-update','check-update']
module.rpc=original_rpc

s, local, web, state = setup('conflict-refresh')
change(local, 'title', 'local title')
change(web, 'title', 'web title')
push(web)
assert s.sync()['state']=='conflict'
assert s.handle({'op':'resume'})['state']=='conflict'
assert s.handle({'op':'pause'})['state']=='conflict'
review = s.handle({'op':'inspect-conflict'})
assert review['files']==['main.tex']
change(web, 'conclusion', 'remote conclusion')
push(web)
assert s.handle({'op':'resolve','accept_current_resolution':True})['state']=='waiting'
assert s.handle({'op':'inspect-conflict'})['remote']==review['remote']
fresh = s.handle({'op':'inspect-conflict', 'refresh':True})
assert fresh['remote']!=review['remote']
change(local,'local title','combined title')
change(local,'conclusion','remote conclusion')
assert s.handle({'op':'resolve','accept_current_resolution':True})['state']=='synced'
print('Multi-window application, peer veto, dirty protection, quiet and conflict refresh checks passed')
