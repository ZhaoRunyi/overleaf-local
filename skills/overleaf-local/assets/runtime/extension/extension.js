const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const net = require('net');
const {spawn} = require('child_process');
const {registerConflicts} = require('./conflicts');
const home = require('./deployment.json').home;
const config = JSON.parse(fs.readFileSync(path.join(home, 'config.json'), 'utf8'));
const allowed = new Set(config.files.map(name => path.join(config.repo, name)));
const binaryExtensions = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.eps', '.zip']);

function isBinary(filename, contents) {
  return binaryExtensions.has(path.extname(filename).toLowerCase()) || contents.includes(0);
}

function request(payload) {
  return new Promise((resolve, reject) => {
    const connection = net.createConnection(path.join(config.runtime, 'service.sock'));
    let buffer = '';
    connection.setTimeout(90000);
    connection.on('connect', () => connection.write(JSON.stringify(payload) + '\n'));
    connection.on('data', data => {
      buffer += data.toString();
      if (buffer.includes('\n')) {
        try { resolve(JSON.parse(buffer.split('\n')[0])); } catch (error) { reject(error); }
        connection.end();
      }
    });
    connection.on('timeout', () => connection.destroy(new Error('Sync request timed out')));
    connection.on('error', reject);
  });
}

function dirtyDocuments() {
  return vscode.workspace.textDocuments.filter(document =>
    document.uri.scheme === 'file' && allowed.has(document.uri.fsPath) && document.isDirty
  ).map(document => document.uri.fsPath);
}

function checkUpdate(changes) {
  if (dirtyDocuments().length) throw new Error('Unsaved paper edits; update deferred');
  for (const change of changes) {
    const filename = path.join(config.repo, change.path);
    if (!allowed.has(filename)) throw new Error('File outside upload allowlist');
    const before = Buffer.from(change.before, 'base64');
    if (!fs.readFileSync(filename).equals(before)) throw new Error('Saved file changed; retry merge');
    const document = vscode.workspace.textDocuments.find(item => item.uri.fsPath === filename);
    if (document && !isBinary(filename, before) &&
        (document.isDirty || !Buffer.from(document.getText()).equals(before))) {
      throw new Error('Another editor has newer or stale text; wait for reload or save');
    }
  }
  return {ok: true};
}

async function applyChanges(changes, testRoot) {
  if (dirtyDocuments().length) throw new Error('Unsaved paper edits; remote update deferred');
  const documents = [];
  const binary = [];
  for (const change of changes) {
    const filename = testRoot ? path.join(testRoot, change.path) : path.join(config.repo, change.path);
    if (!testRoot && !allowed.has(filename)) throw new Error('File outside upload allowlist');
    if (testRoot && path.dirname(filename) !== testRoot) throw new Error('Invalid test path');
    const before = Buffer.from(change.before, 'base64');
    const after = Buffer.from(change.after, 'base64');
    if (!fs.readFileSync(filename).equals(before)) throw new Error('Local file changed; retry merge');
    if (isBinary(filename, before) || isBinary(filename, after)) {
      binary.push({filename, before, after});
      continue;
    }
    const document = await vscode.workspace.openTextDocument(filename);
    if (document.isDirty || !Buffer.from(document.getText()).equals(before)) {
      throw new Error('Editor buffer differs from the merge base; update deferred');
    }
    documents.push({document, before, after, version: document.version});
  }
  // Build and submit one text WorkspaceEdit after all asynchronous document loads.
  const edit = new vscode.WorkspaceEdit();
  for (const {document, before, after, version} of documents) {
    if (document.isDirty || document.version !== version ||
        !fs.readFileSync(document.uri.fsPath).equals(before)) {
      throw new Error('New edit detected before applying merge');
    }
    edit.replace(document.uri, new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length)), after.toString('utf8'));
  }
  if (documents.length && !await vscode.workspace.applyEdit(edit)) {
    throw new Error('VS Code refused the versioned workspace edit');
  }
  for (const {document, before, after} of documents) {
    if (!Buffer.from(document.getText()).equals(after)) {
      throw new Error('New editor input preserved; save it and retry synchronization');
    }
    // Do not overwrite an external save that raced with the editor update.
    const disk = fs.readFileSync(document.uri.fsPath);
    if (!disk.equals(before) && !disk.equals(after)) throw new Error('Concurrent external save; update deferred');
    if (!await document.save()) throw new Error('VS Code could not save the merged document');
    if (!fs.readFileSync(document.uri.fsPath).equals(after)) throw new Error('Save changed the merged contents; retry');
  }
  for (const {filename, before, after} of binary) {
    if (!fs.readFileSync(filename).equals(before)) throw new Error('Figure changed during merge');
    // No asynchronous boundary between comparison and this small figure write.
    fs.writeFileSync(filename, after);
  }
  return {ok: true};
}

async function selfTest() {
  const directory = fs.mkdtempSync('/tmp/overleaf-local-editor-test-');
  const filename = path.join(directory, 'check.tex');
  fs.writeFileSync(filename, 'original\n');
  const document = await vscode.workspace.openTextDocument(filename);
  const edit = new vscode.WorkspaceEdit();
  edit.insert(document.uri, new vscode.Position(0, 0), 'unsaved ');
  await vscode.workspace.applyEdit(edit);
  const changes = [{path: 'check.tex', before: Buffer.from('original\n').toString('base64'),
    after: Buffer.from('remote\n').toString('base64')}];
  let blocked = false;
  try { await applyChanges(changes, directory); } catch (error) { blocked = true; }
  const preserved = document.getText() === 'unsaved original\n';
  await document.save();
  changes[0].before = Buffer.from('unsaved original\n').toString('base64');
  await applyChanges(changes, directory);
  const updated = fs.readFileSync(filename, 'utf8') === 'remote\n';
  const concurrent = [{path: 'check.tex', before: Buffer.from('original\n').toString('base64'), after: changes[0].after}];
  let staleBlocked = false;
  try { await applyChanges(concurrent, directory); } catch (error) { staleBlocked = true; }
  fs.rmSync(directory, {recursive: true});
  return {ok: blocked && preserved && updated && staleBlocked, dirtyBlocked: blocked, unsavedPreserved: preserved,
    cleanApplySucceeded: updated, staleBaseBlocked: staleBlocked};
}

function activate(context) {
  const folders = vscode.workspace.workspaceFolders || [];
  if (!folders.some(folder => config.repo === folder.uri.fsPath || config.repo.startsWith(folder.uri.fsPath + '/'))) return;
  fs.mkdirSync(config.runtime, {recursive: true, mode: 0o700});
  const socketPath = path.join(config.runtime, `editor-${process.pid}.sock`);
  if (fs.existsSync(socketPath)) fs.unlinkSync(socketPath);
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  statusBar.command = 'overleafLocal__PROJECT__.menu';
  statusBar.text = '$(sync) Paper: starting';
  statusBar.show();
  const syncButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 11);
  syncButton.text = '$(cloud-upload) 保存并同步';
  syncButton.tooltip = '保存本窗口的论文修改，并与 Overleaf 双向同步';
  syncButton.command = 'overleafLocal__PROJECT__.saveSync';
  syncButton.show();
  const conflictButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 13);
  conflictButton.text = '$(git-merge) 冲突：选择本地 / Overleaf';
  conflictButton.command = 'overleafLocal__PROJECT__.conflictActions';
  const submitButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 12);
  submitButton.text = '$(check-all) 提交合并结果';
  submitButton.command = 'overleafLocal__PROJECT__.acceptResolution';
  const updateContext = editor => vscode.commands.executeCommand('setContext', 'overleafLocal__PROJECT__.active',
    Boolean(editor && allowed.has(editor.document.uri.fsPath)));
  updateContext(vscode.window.activeTextEditor);
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(updateContext));
  const output = vscode.window.createOutputChannel('Paper Sync');
  let lastState = '';
  let dirtySince = 0;
  let dirtyNotified = false;
  let busy = false;
  const server = net.createServer(connection => {
    let buffer = '';
    connection.on('data', async data => {
      buffer += data.toString();
      if (!buffer.includes('\n')) return;
      const line = buffer.split('\n')[0];
      buffer = '';
      try {
        const input = JSON.parse(line);
        if (input.op === 'status') {
          connection.end(JSON.stringify({repo: config.repo, dirty: dirtyDocuments(), busy,
            focused: vscode.window.state.focused, validate_updates: true}) + '\n');
          return;
        }
        if (busy) throw new Error('Editor operation already in progress');
        busy = true;
        let result;
        try {
          if (input.op === 'apply') result = await applyChanges(input.changes);
          else if (input.op === 'check-update') result = checkUpdate(input.changes);
          else if (input.op === 'self-test') result = await selfTest();
          else throw new Error('Unknown editor operation');
        } finally { busy = false; }
        connection.end(JSON.stringify(result) + '\n');
      } catch (error) {
        connection.end(JSON.stringify({ok: false, error: error.message}) + '\n');
      }
    });
  });
  server.listen(socketPath, () => fs.chmodSync(socketPath, 0o600));
  server.on('error', error => output.appendLine(error.message));
  const start = spawn('/bin/bash', [path.join(home, 'start.sh')], {stdio: 'ignore', detached: true});
  start.unref();
  context.subscriptions.push(vscode.commands.registerCommand('overleafLocal__PROJECT__.saveSync', async () => {
    try {
      let conflict = false;
      try { conflict = JSON.parse(fs.readFileSync(path.join(config.repo, '.git/overleaf-local-paused'), 'utf8')).reason === 'conflict'; }
      catch (error) { /* No recorded merge conflict. */ }
      if (conflict) {
        await vscode.commands.executeCommand('overleafLocal__PROJECT__.continueResolution');
        return;
      }
      for (const document of vscode.workspace.textDocuments) {
        if (allowed.has(document.uri.fsPath) && document.isDirty && !await document.save()) {
          throw new Error('文件未能保存，已停止同步；请先处理编辑器中的保存冲突。');
        }
      }
      await vscode.commands.executeCommand('overleafLocal__PROJECT__.sync');
    } catch (error) { vscode.window.showErrorMessage(`Paper Sync: ${error.message}`); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('overleafLocal__PROJECT__.menu', async () => {
    const items = [
      {label:'$(cloud-upload) 保存并同步', command:'saveSync'},
      {label:'$(sync) 立即同步已保存的内容', command:'sync'},
      {label:'$(check) 检查同步状态', command:'check'},
      {label:'$(debug-pause) 暂停自动同步', command:'pause'},
      {label:'$(play) 恢复自动同步', command:'resume'},
      {label:'$(diff) 查看冲突', command:'resolve'},
      {label:'$(git-merge) 冲突：选择本地 / Overleaf', command:'conflictActions'},
      {label:'$(check-all) 提交合并结果', command:'acceptResolution'}
    ];
    const choice = await vscode.window.showQuickPick(items, {placeHolder:'论文 ↔ Overleaf'});
    if (choice) await vscode.commands.executeCommand('overleafLocal__PROJECT__.' + choice.command);
  }));
  for (const operation of ['check', 'sync', 'pause', 'resume']) {
    context.subscriptions.push(vscode.commands.registerCommand(`overleafLocal__PROJECT__.${operation}`, async () => {
      try {
        const result = await request({op: operation});
        output.appendLine(JSON.stringify(result, null, 2));
        if (result.state === 'synced') vscode.window.showInformationMessage('Paper Sync：本地与 Overleaf 已同步。');
        else if (result.state === 'conflict') {
          await vscode.commands.executeCommand('overleafLocal__PROJECT__.continueResolution');
        }
        else if (result.state === 'error') vscode.window.showErrorMessage(`Paper Sync: ${result.message}`);
        else vscode.window.showWarningMessage(`Paper Sync: ${result.message}`, '同步管理').then(choice => {
          if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.menu');
        });
      } catch (error) { vscode.window.showErrorMessage(`Paper Sync: ${error.message}`); }
    }));
  }
  registerConflicts(vscode, context, config, request, output);
  const timer = setInterval(async () => {
    try {
      const state = await request({op: 'status'});
      // A failed submit may temporarily report waiting; the pause record still owns the conflict.
      let conflict = false;
      try { conflict = JSON.parse(fs.readFileSync(path.join(config.repo, '.git/overleaf-local-paused'), 'utf8')).reason === 'conflict'; }
      catch (error) { /* No recorded merge conflict. */ }
      for (const button of [conflictButton, submitButton]) {
        if (conflict) button.show();
        else button.hide();
      }
      const dirty = dirtyDocuments().length;
      statusBar.text = `$(sync) Paper: ${dirty ? 'unsaved' : state.state}`;
      statusBar.tooltip = `${state.message}\nLast remote check: ${state.checked_at ? new Date(state.checked_at * 1000).toLocaleTimeString() : 'not yet'}`;
      if (dirty || /Unsaved paper edits/.test(state.message)) {
        if (!dirtySince) dirtySince = Date.now();
        if (!dirtyNotified && Date.now() - dirtySince >= 10000) {
          dirtyNotified = true;
          vscode.window.showWarningMessage('Paper Sync 等待保存：某个窗口有未保存的论文修改，自动同步暂缓。', '保存并同步', '打开未保存文件').then(choice => {
            const filename = dirtyDocuments()[0];
            if (choice === '保存并同步') vscode.commands.executeCommand('overleafLocal__PROJECT__.saveSync');
            else if (choice && filename) vscode.window.showTextDocument(vscode.Uri.file(filename));
          });
        }
      } else {
        dirtySince = 0;
        dirtyNotified = false;
      }
      if (state.state !== lastState) {
        output.appendLine(`${new Date().toISOString()} ${state.state}: ${state.message}`);
        if (state.state === 'conflict') vscode.window.showWarningMessage('Paper Sync：两侧修改冲突，同步已暂停。', '查看冲突').then(choice => {
          if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.resolve');
        });
        if (state.state === 'error' || state.state === 'retry') vscode.window.showWarningMessage(`Paper Sync 暂未完成：${state.message}`, '同步管理').then(choice => {
          if (choice) vscode.commands.executeCommand('overleafLocal__PROJECT__.menu');
        });
        lastState = state.state;
      }
    } catch (error) { statusBar.text = '$(warning) Paper: offline'; }
  }, 3000);
  context.subscriptions.push(statusBar, syncButton, conflictButton, submitButton, output, {dispose: () => {
    clearInterval(timer);
    server.close();
    if (fs.existsSync(socketPath)) fs.unlinkSync(socketPath);
  }});
}

module.exports = {activate, applyChanges, checkUpdate};
