// Two installed entry points must not share manuscript scope or editor state.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const Module = require('module');
const workspace = {textDocuments: []};
const originalLoad = Module._load;
Module._load = function(name, parent, isMain) {
  if (name === 'vscode') return {workspace};
  return originalLoad.call(this, name, parent, isMain);
};
const deployments = process.argv.slice(2);
const configs = deployments.map(home => JSON.parse(fs.readFileSync(path.join(home, 'config.json'))));
const extensions = deployments.map(home => require(path.join(home, 'extension/extension.js')));
Module._load = originalLoad;
for (const config of configs) fs.writeFileSync(path.join(config.repo, 'main.tex'), 'source');
const changes = [{path: 'main.tex', before: Buffer.from('source').toString('base64')}];
for (const extension of extensions) assert(extension.checkUpdate(changes).ok);
workspace.textDocuments.push({uri: {scheme: 'file', fsPath: path.join(configs[0].repo, 'main.tex')}, isDirty: true});
assert.throws(() => extensions[0].checkUpdate(changes), /Unsaved/);
assert(extensions[1].checkUpdate(changes).ok);
assert.throws(() => extensions[1].checkUpdate([{path: '../outside.tex'}]), /outside/);
console.log('PASS: shared extension factory isolates two manuscript scopes and unsaved-buffer guards');
