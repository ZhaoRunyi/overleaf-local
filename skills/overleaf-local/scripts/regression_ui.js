const fs = require('fs');
const path = require('path');
const assert = require('assert');
const {execFileSync} = require('child_process');
const {registerConflicts} = require(path.resolve(process.argv[2], 'extension/conflicts'));
const root = fs.mkdtempSync('/tmp/overleaf-ui-test-');
process.on('exit', () => fs.rmSync(root, {recursive:true, force:true}));
function git(...args) {return execFileSync('git', ['-C', root, ...args], {encoding:'utf8'}).trim();}
git('init', '-q');
git('config','user.name','Test');
git('config','user.email','test@localhost');
const file = path.join(root,'main.tex');
fs.writeFileSync(file,'base\n\nunchanged\n');
git('add','.'); git('commit','-qm','base');
const base=git('rev-parse','HEAD');
fs.writeFileSync(file,'remote\n\nunchanged\n');
git('commit','-qam','remote');
const remote=git('rev-parse','HEAD');
fs.writeFileSync(file,'local\n\nunchanged\n');
const storage = new Map();
const context = {subscriptions:[],workspaceState:{get:key=>storage.get(key),update:async(key,value)=>storage.set(key,value)}};
const commands = {};
const errors = [];
const warnings = [];
const opened = [];
const requests = [];
const docs = new Map();
let action;
let confirmation;
let published;
let onSave;
const vscode = {
  Uri:{from:data=>({...data,fsPath:data.path}),file:filename=>({scheme:'file',fsPath:filename,path:filename})},
  Range:class {constructor(start,end){this.start=start;this.end=end;}},
  WorkspaceEdit:class {constructor(){this.edits=[];}replace(uri,range,text){this.edits.push({uri,text});}},
  ProgressLocation:{Notification:15},
  workspace:{textDocuments:[],
    onDidSaveTextDocument:callback=>{onSave=callback;return {dispose(){}};},
    registerTextDocumentContentProvider:(scheme,provider)=>({dispose(){}}),
    openTextDocument:async filename=>{
      filename=typeof filename==='string'?filename:filename.fsPath;
      if(!docs.has(filename)) {
        const document={uri:vscode.Uri.file(filename),isDirty:false,text:fs.readFileSync(filename,'utf8'),
          getText(){return this.text;},positionAt:index=>index,
          async save(){fs.writeFileSync(filename,this.text);this.isDirty=false;return true;}};
        docs.set(filename,document);vscode.workspace.textDocuments.push(document);
      }
      return docs.get(filename);
    },
    applyEdit:async edit=>{for(const item of edit.edits){const doc=docs.get(item.uri.fsPath);doc.text=item.text;doc.isDirty=true;}return true;}
  },
  window:{showErrorMessage:message=>errors.push(message),
    showWarningMessage:async(message,options)=>{warnings.push(message);return options&&options.modal?confirmation:undefined;},
    showInformationMessage:async()=>undefined,
    showQuickPick:async items=>items.find(item=>item.side===action||item.command===action),
    withProgress:async(options,callback)=>callback(),showTextDocument:async()=>{},
    tabGroups:{all:[],close:async()=>true}},
  commands:{registerCommand:(name,callback)=>{commands[name]=callback;return {dispose(){}};},
    executeCommand:async(name,...args)=>{
      if(name==='_open.mergeEditor')opened.push(args[0]);
      else return commands[name]();
    }}
};
async function request(payload){
  requests.push(payload);
  if(payload.op==='inspect-conflict')return {state:'conflict',base,remote,files:['main.tex']};
  published=payload;return {state:'synced',message:'done'};
}
registerConflicts(vscode,context,{repo:root,git_config:'/dev/null',files:['main.tex']},request,{appendLine(){}});
(async()=>{
  await commands['overleafLocal' + process.argv[3] + '.resolve']();
  assert.equal(errors.length,0);
  assert.equal(requests[0].refresh,undefined);
  assert.equal(opened[0].input1.title,'Overleaf');
  assert.equal(opened[0].input2.title,'本地');
  assert(opened[0].output.fsPath.startsWith('/tmp/overleaf-local-merge-'));
  assert.equal(fs.readFileSync(file,'utf8'),'local\n\nunchanged\n');
  const resultPath=opened[0].output.fsPath;
  assert(fs.readFileSync(resultPath,'utf8').includes('<<<<<<< 本地'));
  await commands['overleafLocal' + process.argv[3] + '.acceptResolution']();
  assert(errors.pop().includes('未解决的冲突'));
  assert(!published);
  // Reopening must preserve the user's draft.
  fs.writeFileSync(resultPath,'partially reviewed\n');
  await commands['overleafLocal' + process.argv[3] + '.resolve']();
  assert.equal(opened[1].output.fsPath,resultPath);
  assert.equal(fs.readFileSync(resultPath,'utf8'),'partially reviewed\n');
  // Explicit whole-file remote selection only edits the draft.
  action='remote';confirmation='采用此版本';
  await commands['overleafLocal' + process.argv[3] + '.conflictActions']();
  assert.equal(fs.readFileSync(resultPath,'utf8'),'remote\n\nunchanged\n');
  assert.equal(fs.readFileSync(file,'utf8'),'local\n\nunchanged\n');
  assert(!published);
  docs.get(resultPath).isDirty=true;
  await commands['overleafLocal' + process.argv[3] + '.continueResolution']();
  assert(warnings.at(-1).includes('完成合并并保存'));
  assert(!published);
  await commands['overleafLocal' + process.argv[3] + '.acceptResolution']();
  assert(errors.pop().includes('保存结果'));
  docs.get(resultPath).isDirty=false;
  onSave(docs.get(resultPath));
  confirmation='确认写回并同步';
  await commands['overleafLocal' + process.argv[3] + '.continueResolution']();
  assert.equal(published.reviewed_remote,remote);
  assert.equal(Buffer.from(published.changes[0].before,'base64').toString(),'local\n\nunchanged\n');
  assert.equal(Buffer.from(published.changes[0].after,'base64').toString(),'remote\n\nunchanged\n');
  assert.equal(storage.get('paperMergeSession'),undefined);
  assert.equal(errors.length,0);
  console.log('PASS native-merge command arguments, cached view, source untouched, draft reuse, explicit whole-file choice, unresolved/unsaved guards, confirmed submission. UI rendering is mocked.');
})().catch(error=>{console.error(error);process.exitCode=1;});
