const fs = require('fs');
const path = require('path');
const {execFile} = require('child_process');

function git(config, args, allowConflicts = false) {
  return new Promise((resolve, reject) => {
    execFile('git', ['-C', config.repo, ...args],
      {env: {...process.env, GIT_CONFIG_GLOBAL: config.git_config}, maxBuffer: 16 * 1024 * 1024},
      (error, stdout) => {
        if (error && !(allowConflicts && Number.isInteger(error.code) && error.code > 0 && error.code < 128)) {
          reject(new Error('无法读取本地冲突快照；论文未改动。'));
        } else resolve(stdout);
      });
  });
}

function registerConflicts(vscode, context, config, request, output) {
  let session = context.workspaceState.get('paperMergeSession');
  const snapshot = filename => vscode.Uri.from({scheme: 'ol-__PROJECT__-snapshot',
    path: filename, query: ''});
  context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider('ol-__PROJECT__-snapshot', {
    provideTextDocumentContent(uri) {
      if (!/^\/tmp\/overleaf-local-merge-[^/]+\/(base|local|remote)-\d+\.tex$/.test(uri.path)) {
        throw new Error('Invalid conflict snapshot');
      }
      return fs.readFileSync(uri.path, 'utf8');
    }
  }));

  async function saveSession() {
    await context.workspaceState.update('paperMergeSession', session);
  }

  async function chooseFile() {
    if (!session) throw new Error('请先点击“查看冲突”。');
    return session.files.length === 1 ? session.files[0] :
      vscode.window.showQuickPick(session.files, {placeHolder: '选择需要解决的文件'});
  }

  async function prepare(file) {
    if (session.drafts[file]) return session.drafts[file];
    const textExtensions = new Set(['.tex', '.bib', '.sty', '.cls', '.bst', '.txt', '.md', '.svg']);
    if (!config.files.includes(file) || !textExtensions.has(path.extname(file).toLowerCase())) {
      throw new Error('此文件不能作为文本合并，请保留冲突并单独审核图片。');
    }
    const filename = path.join(config.repo, file);
    const document = await vscode.workspace.openTextDocument(filename);
    if (document.isDirty || document.getText() !== fs.readFileSync(filename, 'utf8')) {
      throw new Error('请先保存本地修改，再打开合并草稿。');
    }
    const before = document.getText();
    const [base, remote] = await Promise.all([
      git(config, ['show', `${session.base}:${file}`]),
      git(config, ['show', `${session.remote}:${file}`])
    ]);
    const index = session.files.indexOf(file);
    const draft = Object.fromEntries(['base', 'local', 'remote', 'result'].map(kind =>
      [kind, path.join(session.directory, `${kind}-${index}.tex`)]));
    fs.writeFileSync(draft.base, base);
    fs.writeFileSync(draft.local, before);
    fs.writeFileSync(draft.remote, remote);
    const merged = await git(config, ['merge-file', '-p', '--diff3',
      '-L', '本地', '-L', '共同祖先', '-L', 'Overleaf', draft.local, draft.base, draft.remote], true);
    fs.writeFileSync(draft.result, merged);
    session.drafts[file] = draft;
    await saveSession();
    return draft;
  }

  async function openMerge(file) {
    const draft = await prepare(file);
    await vscode.commands.executeCommand('_open.mergeEditor', {
      base: snapshot(draft.base),
      input1: {uri: snapshot(draft.remote), title: 'Overleaf', description: '网页版本'},
      input2: {uri: snapshot(draft.local), title: '本地', description: '本地保存的版本'},
      output: vscode.Uri.file(draft.result)
    });
    vscode.window.showInformationMessage(
      '逐处点击“接受 Overleaf”或“接受 本地”，检查下方结果并完成合并。最后点击底栏“提交合并结果”；草稿不会自动上传。',
      '整份文件选择版本').then(choice => {
        if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.conflictActions');
      });
  }

  function register(name, callback) {
    context.subscriptions.push(vscode.commands.registerCommand('overleafLocal__PROJECT__.' + name, async () => {
      try { await callback(); }
      catch (error) { vscode.window.showErrorMessage(`Paper Sync: ${error.message}`); }
    }));
  }

  function draftReady() {
    return session && session.files.every(file => {
      const draft = session.drafts[file];
      if (!draft || !fs.existsSync(draft.result)) return false;
      if (vscode.workspace.textDocuments.some(document => document.uri.fsPath === draft.result && document.isDirty)) return false;
      return !/^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)( |$)/m.test(fs.readFileSync(draft.result, 'utf8'));
    });
  }

  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(document => {
    if (!session || !Object.values(session.drafts).some(draft => draft.result === document.uri.fsPath) || !draftReady()) return;
    vscode.window.showInformationMessage(
      '合并结果已保存，但尚未上传。下一步点击“提交并同步”；也可以回到论文点击“保存并同步”。',
      '提交并同步').then(choice => {
        if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.acceptResolution');
      });
  }));

  register('continueResolution', async () => {
    if (draftReady()) {
      await vscode.commands.executeCommand('overleafLocal__PROJECT__.acceptResolution');
      return;
    }
    const choice = await vscode.window.showWarningMessage(
      '冲突还未完成提交。请逐处选择本地或 Overleaf，完成合并并保存；之后再点“保存并同步”即可提交。',
      '继续处理冲突');
    if (choice) await vscode.commands.executeCommand('overleafLocal__PROJECT__.resolve');
  });

  register('resolve', async () => {
    const started = Date.now();
    const result = await request({op: 'inspect-conflict'});
    if (!result.files || !result.files.length) {
      vscode.window.showWarningMessage(`没有可打开的冲突文件：${result.message || '请检查同步状态'}`);
      return;
    }
    const localChanged = session && Object.entries(session.drafts).some(([file, draft]) =>
      !fs.existsSync(draft.local) || !fs.existsSync(path.join(config.repo, file)) ||
      !fs.readFileSync(draft.local).equals(fs.readFileSync(path.join(config.repo, file))));
    if (!session || session.remote !== result.remote || session.base !== result.base || localChanged ||
        !fs.existsSync(session.directory)) {
      if (session) vscode.window.showWarningMessage('源版本已变化，将建立新合并草稿；旧草稿仍保留在原标签页和临时目录中。');
      session = {...result, directory: fs.mkdtempSync('/tmp/overleaf-local-merge-'), drafts: {}};
      await saveSession();
    }
    const file = await chooseFile();
    if (file) await openMerge(file);
    output.appendLine(`本地冲突快照准备并派发编辑器打开请求：${Date.now() - started} ms（不含界面绘制）`);
  });

  register('conflictActions', async () => {
    const action = await vscode.window.showQuickPick([
      {label: '逐处选择本地 / Overleaf', command: 'resolve'},
      {label: '整份文件采用本地', side: 'local'},
      {label: '整份文件采用 Overleaf', side: 'remote'},
      {label: '提交合并结果', command: 'acceptResolution'},
      {label: '重新拉取 Overleaf 版本', command: 'refreshConflict'}
    ], {placeHolder: '逐处选择只处理冲突；整份采用会舍弃该文件另一侧的修改'});
    if (!action) return;
    if (action.command) return vscode.commands.executeCommand('overleafLocal__PROJECT__.' + action.command);
    if (!session) await vscode.commands.executeCommand('overleafLocal__PROJECT__.resolve');
    const file = await chooseFile();
    if (!file) return;
    const draft = await prepare(file);
    const confirmed = await vscode.window.showWarningMessage(
      `${file}：${action.label}，会替换这份合并草稿，包括已合并的修改。尚不上传。`,
      {modal: true}, '采用此版本');
    if (confirmed !== '采用此版本') return;
    // Close the native merge view first, so an unsaved merge-result model cannot overwrite this choice.
    const tabs = vscode.window.tabGroups.all.flatMap(group => group.tabs).filter(tab =>
      tab.input && tab.input.result && tab.input.result.fsPath === draft.result);
    if (tabs.length && !await vscode.window.tabGroups.close(tabs)) return;
    const document = await vscode.workspace.openTextDocument(draft.result);
    const edit = new vscode.WorkspaceEdit();
    edit.replace(document.uri, new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length)),
      fs.readFileSync(draft[action.side], 'utf8'));
    if (!await vscode.workspace.applyEdit(edit) || !await document.save()) throw new Error('无法保存合并草稿。');
    await vscode.window.showTextDocument(document, {preview: false});
    vscode.window.showInformationMessage('已更新合并草稿；检查后点击“提交合并结果”才会写回论文并上传。');
  });

  register('refreshConflict', async () => {
    const result = await vscode.window.withProgress({location: vscode.ProgressLocation.Notification,
      title: '正在获取 Overleaf 最新版本…'}, () => request({op: 'inspect-conflict', refresh: true}));
    if (result.state !== 'conflict') throw new Error(result.message);
    await vscode.commands.executeCommand('overleafLocal__PROJECT__.resolve');
  });

  register('acceptResolution', async () => {
    if (!session || session.files.some(file => !session.drafts[file])) {
      throw new Error('请先逐个打开并审核所有冲突文件。');
    }
    const changes = [];
    for (const file of session.files) {
      const draft = session.drafts[file];
      if (vscode.workspace.textDocuments.some(document => document.uri.fsPath === draft.result && document.isDirty)) {
        throw new Error('请先在合并编辑器完成合并并保存结果，再提交。');
      }
      const after = fs.readFileSync(draft.result);
      if (/^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)( |$)/m.test(after.toString())) {
        throw new Error('合并草稿仍有未解决的冲突，请逐处选择本地或 Overleaf。');
      }
      changes.push({path: file, before: fs.readFileSync(draft.local).toString('base64'), after: after.toString('base64')});
    }
    const answer = await vscode.window.showWarningMessage(
      '确认所有合并草稿是最终版本？将写回论文并上传；提交前会核验本地和 Overleaf 均未在审核期间改变。',
      {modal: true}, '确认写回并同步');
    if (answer !== '确认写回并同步') return;
    const state = await vscode.window.withProgress({location: vscode.ProgressLocation.Notification,
      title: '正在核验并提交合并结果…'}, () => request({op: 'resolve', accept_current_resolution: true,
      reviewed_remote: session.remote, changes}));
    output.appendLine(JSON.stringify(state, null, 2));
    if (state.state === 'synced') {
      session = undefined;
      await saveSession();
      vscode.window.showInformationMessage('合并结果已写回，本地与 Overleaf 已同步。');
    } else vscode.window.showWarningMessage(`未完成同步，草稿已保留：${state.message}`, '重新检查冲突').then(choice => {
      if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.refreshConflict');
    });
  });
}

module.exports = {registerConflicts};
