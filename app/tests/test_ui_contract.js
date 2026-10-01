#!/usr/bin/env node
'use strict';

/*
 * Node VM view-template contract smoke test. This is deliberately NOT a browser
 * test: there is no DOM layout, CSS engine, pointer interaction or screenshot.
 * It renders real view functions against a captured, actual server data set.
 *
 * node tests/test_ui_contract.js /absolute/path/to/preview_data.json
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

async function main() {
  const fixturePath = process.argv[2];
  assert.ok(fixturePath, 'Pass the JSON written by scripts/capture_preview.py.');
  const data = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const appDir = path.resolve(__dirname, '..');
  const nodes = new Map(['#app', '#modal-root', '#toast-region'].map(id => [id, {
    innerHTML: '', children: [], attributes: {}, append(child) { this.children.push(child); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute(name) { delete this.attributes[name]; },
  }]));
  const themeMeta = {content: '#f4f5f7'};
  const documentElement = {dataset: {}, style: {}, attributes: {},
    setAttribute(name, value) { this.attributes[name] = String(value); if (name === 'data-theme') this.dataset.theme = String(value); },
    removeAttribute(name) { delete this.attributes[name]; if (name === 'data-theme') delete this.dataset.theme; },
  };
  const storedValues = new Map([['axiom.theme', 'dark']]);
  const localStorage = {getItem(key) { return storedValues.get(key) ?? null; }, setItem(key, value) { storedValues.set(key, String(value)); }};
  const sessionValues = new Map();
  const sessionStorage = {getItem(key) { return sessionValues.get(key) ?? null; }, setItem(key, value) { sessionValues.set(key, String(value)); }, removeItem(key) { sessionValues.delete(key); }};
  const document = {
    hidden: false, activeElement: null, documentElement,
    querySelector(selector) { return selector === 'meta[name="theme-color"]' ? themeMeta : nodes.get(selector) || null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    createElement() { return {innerHTML: '', className: '', attributes: {},
      setAttribute(name, value) { this.attributes[name] = String(value); },
      removeAttribute(name) { delete this.attributes[name]; },
      remove() {}, click() {}}; },
  };
  const context = vm.createContext({
    window: {AXIOM_PREVIEW_DATA: data, localStorage, sessionStorage, innerWidth: 1440, innerHeight: 900,
      matchMedia() { return {matches: false}; }, addEventListener() {}},
    document,
    location: {hash: '', reload() {}},
    requestAnimationFrame() {},
    setTimeout(callback) { if (typeof callback === 'function') callback(); return 1; },
    clearTimeout() {}, setInterval() {}, clearInterval() {},
    confirm() { return false; },
    fetch() { throw new Error('VM smoke test must never contact a service.'); },
    console,
  });
  const evaluate = code => vm.runInContext(code, context, {timeout: 5000});
  evaluate(fs.readFileSync(path.join(appDir, 'public', 'icons.js'), 'utf8'));
  const appSource = fs.readFileSync(path.join(appDir, 'public', 'app.js'), 'utf8');
  evaluate(appSource);
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(evaluate('state.template && state.data'), 'Bootstrap must resolve from the recorded data.');
  assert.ok(!nodes.get('#app').innerHTML.includes('Workspace unavailable'), 'Bootstrap may not display its error fallback.');

  const counts = {routeRenders: 0,runRenders: 0,inspectorRenders: 0,mappingModals: 0,evidenceModals: 0,effectModals: 0,repairModals: 0};
  const inspect = selector => {
    const content = nodes.get(selector).innerHTML;
    assert.ok(content.length > 100, `Missing view HTML in ${selector}`);
    assert.ok(!/\bundefined\b|\bNaN\b/.test(content), `Unresolved field in ${selector}`);
    return content;
  };
  const initialHtml = inspect('#app');
  assert.match(initialHtml, /class="skip-link" href="#page-content"/, 'Keyboard users receive a main-content skip link.');
  assert.match(initialHtml, /id="page-content" tabindex="-1"/, 'The single-page route target can receive programmatic focus.');
  assert.equal(evaluate('state.theme'), 'dark', 'The saved night theme is restored before the first app render.');
  assert.equal(documentElement.dataset.theme, 'dark', 'The night theme is applied to the document root.');
  assert.equal(documentElement.style.colorScheme, 'dark', 'Native controls use the selected dark color scheme.');
  assert.equal(themeMeta.content, '#0e131b', 'Night mode updates the browser theme color.');
  assert.match(initialHtml, /data-action="toggle-theme"[^>]*aria-pressed="true"/, 'The theme toggle exposes its current state.');
  await evaluate("onAction('toggle-theme')");
  assert.equal(storedValues.get('axiom.theme'), 'light', 'Changing the theme persists the explicit preference.');
  assert.equal(documentElement.dataset.theme, 'light', 'The theme toggle updates the root immediately.');
  assert.equal(themeMeta.content, '#f4f5f7', 'Day mode restores the light browser theme color.');
  delete documentElement.dataset.theme;
  assert.equal(evaluate('preferredTheme()'), 'light', 'A later load can restore the persisted theme.');
  documentElement.dataset.theme = 'light';
  evaluate("toast('Something failed',true);toast('Saved',false);");
  assert.equal(nodes.get('#toast-region').children.at(-2).attributes.role, 'alert', 'Error feedback is announced immediately.');
  assert.equal(nodes.get('#toast-region').children.at(-1).attributes.role, 'status', 'Success feedback uses a non-interrupting status.');
  for (let roleIndex = 0; roleIndex < data.users.length; roleIndex++) {
    evaluate(`state.data.user=state.data.users[${roleIndex}];state.experiments=state.data.experiments||[];state.audit=state.data.audit||[];`);
    for (const route of ['studio','agents','runs','schedules','review','lab','connections','audit']) {
      evaluate(`state.route=${JSON.stringify(route)};state.run=null;state.runId=null;state.selected=null;state.panel='assistant';render();`);
      inspect('#app');
      counts.routeRenders++;
    }
    for (let runIndex = 0; runIndex < data.runs.length; runIndex++) {
      evaluate(`state.route='runs';state.run=state.data.runs[${runIndex}];state.runId=state.run.id;render();`);
      assert.ok(inspect('#app').includes(data.runs[runIndex].id), 'Run view must identify its pinned record.');
      counts.runRenders++;
    }
  }
  evaluate(`globalThis.__scheduleTemplate=state.data.templates.find(template=>template.publishedVersion&&template.status!=='archived');
    state.data.schedules=[{id:'schedule_ui_contract',name:'Protected daily review',templateId:__scheduleTemplate.id,
      templateName:__scheduleTemplate.name,templateVersion:__scheduleTemplate.publishedVersion,status:'paused',frequency:'daily',
      localStart:'2026-10-02T09:00',timezone:'Asia/Kolkata',nextRunAt:'2026-10-02T03:30:00Z',lastRunAt:null,lastRunId:null,
      runCount:0,missedCount:0,revision:3,scenario:'happy',input:{apiToken:'[REDACTED]'},inputRedacted:true,
      overlapPolicy:'skip',allowedActions:['edit','archive','run','resume'],actionPolicy:[
        {action:'edit',allowed:true,reason:'Administrator role is eligible.'},{action:'archive',allowed:true,reason:'Administrator role is eligible.'},
        {action:'run',allowed:true,reason:'Operations role is eligible.'},{action:'resume',allowed:true,reason:'Operations role is eligible.'}]}];
    state.data.user=state.data.users.find(user=>user.role==='admin')||state.data.users[0];state.route='schedules';render();`);
  const scheduleHtml = inspect('#app');
  assert.match(scheduleHtml, /Protected daily review/, 'The schedules route renders durable schedule records.');
  assert.match(scheduleHtml, /data-schedule-action="resume"/, 'A paused schedule exposes its server-authorized resume action.');
  assert.equal(evaluate("scheduleInputContainsRedaction({apiToken:'[REDACTED]'})"), true,
    'Masked schedule input is detected defensively even without the explicit server flag.');
  evaluate('scheduleModal(state.data.schedules[0])');
  const protectedScheduleModal = inspect('#modal-root');
  assert.match(protectedScheduleModal, /id="schedule-input"[^>]*readonly/, 'Protected schedule input cannot be edited as masked text.');
  assert.match(protectedScheduleModal, /id="schedule-template"[^>]*disabled/, 'Protected input cannot be silently rebound to another workflow.');
  assert.match(protectedScheduleModal, /Protected values are hidden and retained/, 'The schedule editor explains preserve-on-update behavior.');
  assert.match(protectedScheduleModal, /Create a replacement schedule to change the workflow or its input/, 'The schedule editor explains how to replace a protected binding.');
  const pendingRunNow = JSON.parse(evaluate('JSON.stringify(scheduleRunNowOperation(state.data.schedules[0]))'));
  assert.equal(pendingRunNow.expectedRevision, 3, 'Run now binds the request to the displayed schedule revision.');
  assert.match(pendingRunNow.idempotencyKey, /^[A-Za-z0-9._:-]{1,128}$/, 'Run now creates a server-compatible idempotency key.');
  assert.ok(sessionValues.has('axiom.schedule-run-now.v1:schedule_ui_contract'), 'The pending run-now identity survives a page reload in session storage.');
  evaluate('scheduleRunNowMemory.clear()');
  assert.deepEqual(JSON.parse(evaluate("JSON.stringify(readScheduleRunNowOperation('schedule_ui_contract'))")), pendingRunNow,
    'A rerender or reload reuses the exact pending run-now request.');
  sessionValues.set('axiom.schedule-run-now.v1:schedule_ui_contract', JSON.stringify({idempotencyKey:'unsafe key',expectedRevision:3,extra:true}));
  evaluate('scheduleRunNowMemory.clear()');
  assert.equal(evaluate("readScheduleRunNowOperation('schedule_ui_contract')"), null, 'Malformed stored retry state is ignored safely.');
  assert.equal(sessionValues.has('axiom.schedule-run-now.v1:schedule_ui_contract'), false, 'Malformed stored retry state is removed.');
  evaluate("writeScheduleRunNowOperation('schedule_ui_contract',{idempotencyKey:'retry-safe-1',expectedRevision:3})");
  evaluate("clearScheduleRunNowOperation('schedule_ui_contract')");
  assert.equal(sessionValues.has('axiom.schedule-run-now.v1:schedule_ui_contract'), false, 'A resolved run-now request clears its stored retry identity.');
  const nonAdminIndex = data.users.findIndex(user => user.role !== 'admin');
  assert.notEqual(nonAdminIndex, -1, 'The captured data must include a non-administrator role.');
  evaluate(`state.template=__scheduleTemplate;state.data.user=state.data.users[${nonAdminIndex}];`);
  for (const [viewName, html] of [['Studio', evaluate('studio()')], ['Runs', evaluate('runsPage()')]]) {
    const entry = html.match(/<button[^>]*data-schedule-create="true"[^>]*>/)?.[0];
    assert.ok(entry, `${viewName} exposes a discoverable scheduling entry point.`);
    assert.match(entry, /aria-disabled="true"/, `${viewName} keeps the denied schedule control focusable.`);
    assert.match(entry, /data-action-denied="Administrator role required\./, `${viewName} explains the administrator requirement.`);
    assert.doesNotMatch(entry, /data-action="new-schedule"/, `${viewName} does not expose an active create action to non-administrators.`);
  }
  evaluate("state.data.user=state.data.users.find(user=>user.role==='admin')||state.data.users[0]");
  for (const [viewName, html] of [['Studio', evaluate('studio()')], ['Runs', evaluate('runsPage()')]]) {
    const entry = html.match(/<button[^>]*data-schedule-create="true"[^>]*>/)?.[0];
    assert.match(entry, /data-action="new-schedule"/, `${viewName} enables schedule creation for an administrator.`);
    assert.doesNotMatch(entry, /aria-disabled="true"/, `${viewName} administrator entry point is active.`);
  }
  evaluate('state.scheduleEditor.dirty=true');
  assert.equal(evaluate('closeModal()'), false, 'Canceling an unsaved schedule editor requires explicit discard confirmation.');
  assert.ok(nodes.get('#modal-root').innerHTML, 'Declining discard keeps the schedule editor open.');
  evaluate('globalThis.__originalConfirm=confirm;globalThis.confirm=()=>true;closeModal();globalThis.confirm=__originalConfirm;delete globalThis.__originalConfirm;delete globalThis.__scheduleTemplate;');
  assert.match(appSource, /if\(state\.scheduleEditor\?\.inputRedacted\)\{delete payload\.input;payload\.inputMode='preserve';\}/,
    'Protected schedule updates explicitly preserve server input without resubmitting masked values.');
  assert.doesNotMatch(evaluate('performScheduleAction.toString()'), /dataset\.idempotencyKey/,
    'Run-now retry identity is never tied to a transient button element.');
  assert.match(evaluate('performScheduleAction.toString()'), /error\?\.structured===true/,
    'Structured server rejections clear stale retry state while ambiguous transport failures retain it.');
  assert.match(evaluate('api.toString()'), /error\.structured=true/,
    'HTTP API errors are marked so retry handling can distinguish them from ambiguous transport failures.');
  assert.match(appSource, /method:'DELETE',body:\{expectedRevision:schedule\.revision\}/,
    'Archiving binds the action to the schedule revision displayed to the user.');
  assert.match(appSource, /beforeunload[\s\S]*?updateScheduleEditorDirty\(\)/,
    'Browser navigation protects unsaved schedule edits.');
  evaluate(`globalThis.__connectionsBeforeContract=clone(state.data.connections);
    state.data.connections=[{id:'fixture-ticket',name:'Local ticket store',type:'local-fixture',status:'revoked',generation:4,
      sideEffects:'write',allowedOperations:['ticket.create'],description:'Local only'}];state.route='connections';render();`);
  const connectionHtml = inspect('#app');
  for (const visible of ['Revoked','Generation 4','local-fixture','ticket.create']) {
    assert.ok(connectionHtml.includes(visible), `Connection authority view must render ${visible}.`);
  }
  for (const provider of ['Slack','Jira','Confluence','REST / OpenAPI','Webhook','MCP server']) {
    assert.ok(connectionHtml.includes(provider), `Connection catalog must explain ${provider} support.`);
  }
  assert.match(connectionHtml, /Credentials stay server-side/, 'Connection setup explains the credential boundary.');
  assert.match(connectionHtml, /Developer-reviewed import required/, 'OpenAPI inspection is labeled non-executable instead of appearing connected.');
  assert.match(connectionHtml, /MCP client integration required/, 'Unavailable MCP execution is labeled instead of appearing connected.');
  evaluate(`globalThis.__connectionUserBefore=state.data.user;globalThis.__connectionCatalogBefore=state.data.connectionCatalog;
    state.data.user=state.data.users.find(user=>user.role==='admin');
    state.data.connectionCatalog=[
      {id:'jira-cloud',available:true,setup:{enabled:true,fields:['id','name','baseUrls','auth','allowedOperations']},secretRefSchemes:['env']},
      {id:'generic-rest',available:true,setup:{enabled:true},secretRefSchemes:['env']}
    ];`);
  evaluate("connectionSetupModal('jira-cloud')");
  const jiraSetupHtml = inspect('#modal-root');
  assert.match(jiraSetupHtml, /data-connection-secret-ref="true"/, 'Secret-like authority is collected only as a server-side reference.');
  assert.match(jiraSetupHtml, /env:AXIOM_JIRA_API_TOKEN/, 'The local setup uses the advertised env reference scheme.');
  assert.doesNotMatch(jiraSetupHtml, /type="password"/, 'The local reference must not invite raw secret entry without an encrypted vault.');
  assert.match(jiraSetupHtml, /Register bounded connection/, 'An installed connector exposes one purposeful setup action.');
  assert.match(jiraSetupHtml, /data-connection-operation=/, 'Connection setup requires an explicit operation boundary.');
  assert.match(jiraSetupHtml, /Write · exact review/, 'Write operations retain their exact-review boundary.');
  evaluate('closeModal()');
  evaluate("connectionSetupModal('generic-rest')");
  const openApiSetupHtml = inspect('#modal-root');
  assert.match(openApiSetupHtml, /OpenAPI 3\.1 JSON document/, 'Administrators can submit one bounded OpenAPI document for inspection.');
  assert.match(openApiSetupHtml, /data-openapi-inspect/, 'The inspect-only flow exposes one purposeful validation action.');
  assert.match(openApiSetupHtml, /does not fetch references/, 'OpenAPI inspection states its network and authority boundary.');
  assert.match(openApiSetupHtml, /Developer review remains mandatory/, 'Generic REST states the executable-schema review boundary.');
  assert.doesNotMatch(openApiSetupHtml, /data-connect-provider=/, 'Inspect-only providers expose no dead Connect action.');
  const openApiResultHtml = evaluate(`openApiInspectionResult({
    documentHash:'4e9f4f7f',executable:false,activation:'developer-review-required',
    report:{title:'Widget API',openapiVersion:'3.1.0',sourceVersion:'2026-09',
      activationWarning:'Every operation still needs explicit developer classification.',
      candidates:[{candidateId:'rest.getWidget',description:'Read one widget.',method:'GET',pathTemplate:'widgets/{widgetId}',
        reviewState:'unclassified',requiredReviewFields:['effect','requiredScopes','approvalRequired']}]}
  })`);
  assert.match(openApiResultHtml, /rest\.getWidget/, 'Inspection results show candidate operations.');
  assert.match(openApiResultHtml, /Unclassified/, 'Inspection results never infer an operation effect.');
  assert.match(openApiResultHtml, /Every operation still needs explicit developer classification/, 'Inspection results surface activation warnings.');
  assert.match(openApiResultHtml, /No connection, capability, credential, or executable adapter was created/, 'Inspection results retain the non-executable boundary.');
  const textareaField = evaluate(`connectionSetupField({id:'reviewedJson',label:'Reviewed JSON',type:'textarea'},
    {id:'future-reviewed-provider',secretRefSchemes:['env']},'none')`);
  assert.match(textareaField, /<textarea[^>]*data-connection-field="reviewedJson"/, 'A future server-reviewed import flow can advertise bounded textarea input without browser fetching.');
  evaluate('closeModal()');
  const connectionCreateSource = evaluate('createConnection.toString()');
  assert.match(connectionCreateSource, /secretRefs/, 'Provisioning serializes secret references.');
  assert.doesNotMatch(connectionCreateSource, /credentials/, 'Provisioning never serializes raw credential values.');
  const disconnectedCapability = evaluate(`factoryToolOption({id:'slack.messages.send',effect:'write',description:'Send a message',
    verification:{externalIntegration:true},adapterBinding:{providerId:'slack',transport:'https',operation:'slack.messages.send'},authorization:{scope:'chat:write'}},[],'')`);
  assert.match(disconnectedCapability, /Setup required/, 'Agent capability selection exposes missing external authority.');
  assert.match(disconnectedCapability, /chat:write/, 'Agent capability selection exposes authorization scope.');
  evaluate('state.data.user=__connectionUserBefore;state.data.connectionCatalog=__connectionCatalogBefore;delete globalThis.__connectionUserBefore;delete globalThis.__connectionCatalogBefore;');
  evaluate('state.data.connections=__connectionsBeforeContract;delete globalThis.__connectionsBeforeContract;');
  const openingTag = (html, attribute, value) => {
    const match = html.match(new RegExp(`<button[^>]*${attribute}="${value}"[^>]*>`));
    assert.ok(match, `Missing ${attribute}=${value} button.`);
    return match[0];
  };
  const optionTag = (html, value) => {
    const match = html.match(new RegExp(`<option[^>]*value="${value}"[^>]*>`));
    assert.ok(match, `Missing option value=${value}.`);
    return match[0];
  };
  const styles = fs.readFileSync(path.join(appDir, 'public', 'styles.css'), 'utf8');
  assert.match(styles, /\.node-menu-trigger\{position:absolute/, 'The visible node action button must not change graph-card geometry.');
  assert.match(styles, /@media\(max-width:880px\)[\s\S]*?\.studio-header-actions \.btn\.save-btn\{display:inline-flex\}/,
    'Saving a workflow remains available on tablet and mobile layouts.');
  assert.match(styles, /:root\[data-theme="dark"\] \.canvas-pane/, 'Night mode covers the workflow canvas and not only the page shell.');
  assert.match(styles, /\.btn\.action-role-handoff:hover\{/, 'Reviewer handoff actions expose a visible hover state.');
  assert.match(styles, /\.btn\.action-role-handoff:focus-visible\{/, 'Reviewer handoff actions expose a keyboard focus state.');
  assert.match(styles, /\.btn\.action-denied\[aria-disabled="true"\]:hover\{/, 'Denied controls can reveal their explanation on hover without becoming executable.');

  evaluate(`globalThis.__builderBefore={template:state.template,user:state.data.user,dirty:state.dirty,undo:state.undo,redo:state.redo,
    selected:state.selected,panel:state.panel,palette:state.palette,pendingPlacement:state.pendingPlacement,contextMenu:state.contextMenu,
    mobilePanel:state.mobilePanel,linkFrom:state.linkFrom,route:state.route};
    state.data.user=state.data.users.find(user=>user.role==='admin');
    state.template={id:'builder-contract',name:'Builder contract',description:'UI authoring test',status:'draft',draftRevision:1,publishedVersion:null,nodes:[],edges:[]};
    state.dirty=false;state.undo=[];state.redo=[];state.selected=null;state.panel='assistant';state.palette=false;state.pendingPlacement=null;state.contextMenu=null;state.linkFrom=null;state.route='studio';`);
  const blankStudio = evaluate('studio()');
  assert.match(blankStudio, /class="blank-editor"/, 'A blank workflow has a purposeful starting state.');
  assert.doesNotMatch(openingTag(blankStudio, 'data-action', 'palette'), /disabled/, 'A blank workflow exposes an enabled Add control.');
  assert.match(blankStudio, /Add your first step/, 'The blank-canvas action clearly starts the workflow.');
  evaluate(`globalThis.__firstBuilderNode=addNodeToDraft('intake',{x:413,y:271}).id;`);
  assert.deepEqual(JSON.parse(evaluate(`JSON.stringify({nodes:state.template.nodes.length,edges:state.template.edges.length,
    x:state.template.nodes[0].x,y:state.template.nodes[0].y,selected:state.selected,dirty:state.dirty})`)),
    {nodes:1,edges:0,x:415,y:270,selected:evaluate('__firstBuilderNode'),dirty:true},
    'The first step is placed on the grid and selected without creating a stray connection.');
  evaluate(`globalThis.__secondBuilderNode=addNodeToDraft('enrich',{sourceId:__firstBuilderNode}).id;
    state.template.nodes.find(node=>node.id===__secondBuilderNode).label='X'.repeat(120);
    state.template.nodes.find(node=>node.id===__secondBuilderNode).config.nested={value:1};
    globalThis.__copyBuilderNode=duplicateNodeInDraft(__secondBuilderNode).id;
    state.template.nodes.find(node=>node.id===__copyBuilderNode).config.nested.value=2;`);
  const builderState = JSON.parse(evaluate(`JSON.stringify({nodes:state.template.nodes.length,edges:state.template.edges,
    copy:state.template.nodes.find(node=>node.id===__copyBuilderNode),source:state.template.nodes.find(node=>node.id===__secondBuilderNode),undo:state.undo.length})`));
  assert.equal(builderState.nodes, 3, 'Adding and duplicating steps grows the draft predictably.');
  assert.equal(builderState.edges.length, 1, 'Only Add connected creates a connection; duplicate does not copy edges.');
  assert.equal(builderState.edges[0].source, evaluate('__firstBuilderNode'));
  assert.equal(builderState.edges[0].target, evaluate('__secondBuilderNode'));
  assert.match(builderState.copy.id, /^[A-Za-z0-9_-]{1,80}$/, 'Generated step IDs meet the server contract.');
  assert.ok(builderState.copy.label.length <= 120, 'Duplicated labels cannot exceed the server limit.');
  assert.equal(builderState.source.config.nested.value, 1, 'Duplicated configuration is deep-copied.');
  assert.ok(builderState.undo >= 3, 'Each authoring operation can be undone.');
  assert.deepEqual(JSON.parse(evaluate("JSON.stringify(defaultNodeConfig(agent('outcome')))")), {
    executionMode:'automatic',executorRole:'contributor',approvalRequired:false,approverRole:'reviewer',timeoutSeconds:30,retries:2,
    outcome:'completed',reason:'Workflow completed successfully.',
  }, 'Control steps receive saveable defaults when placed.');

  evaluate(`state.contextMenu={type:'node',nodeId:__firstBuilderNode,x:30,y:30};`);
  const nodeMenu = evaluate('contextMenuView()');
  for (const action of ['configure-node','rename-node','add-after-node','duplicate-node','connect-node','map-node','inspect-node-agent','edit-node-agent','remove-node']) {
    assert.ok(nodeMenu.includes(`data-context-action="${action}"`), `Node menu is missing ${action}.`);
  }
  assert.ok(!evaluate("graph(state.template,{nodes:[]})").includes('data-node-menu='), 'Pinned run graphs do not expose draft mutation menus.');
  evaluate(`state.data.user=state.data.users.find(user=>user.role==='reviewer');state.contextMenu={type:'node',nodeId:__firstBuilderNode,x:30,y:30};`);
  const reviewerMenu = evaluate('contextMenuView()');
  assert.match(openingTag(reviewerMenu, 'data-context-action', 'rename-node'), /disabled/, 'Reviewers cannot rename draft steps.');
  assert.match(openingTag(reviewerMenu, 'data-context-action', 'remove-node'), /disabled/, 'Reviewers cannot remove draft steps.');
  assert.doesNotMatch(openingTag(reviewerMenu, 'data-context-action', 'configure-node'), /disabled/, 'Reviewers may inspect step configuration.');
  assert.doesNotMatch(openingTag(reviewerMenu, 'data-context-action', 'inspect-node-agent'), /disabled/, 'Reviewers may inspect agent contracts.');
  assert.match(evaluate('editingBanner(false)'), /data-switch-user="author"/, 'A read-only reviewer can switch directly to the editing account.');
  evaluate('state.dirty=false;');
  await evaluate("switchDevelopmentUser('author')");
  assert.equal(evaluate('state.data.user.role'), 'admin', 'The banner account action restores authoring permission.');
  evaluate(`state.contextMenu={type:'node',nodeId:__firstBuilderNode,x:30,y:30};`);
  await evaluate("handleContextAction('connect-node')");
  assert.equal(evaluate('state.linkFrom'), evaluate('__firstBuilderNode'), 'Connect from this step enters connection mode.');
  evaluate(`state.contextMenu={type:'node',nodeId:__firstBuilderNode,x:30,y:30};`);
  await evaluate("handleContextAction('add-after-node')");
  assert.equal(evaluate('state.pendingPlacement.sourceId'), evaluate('__firstBuilderNode'), 'Add connected remembers its source step.');
  assert.equal(evaluate('state.palette'), true, 'Add connected opens the reusable-agent picker.');
  evaluate(`state.contextMenu={type:'node',nodeId:__firstBuilderNode,x:30,y:30};`);
  await evaluate("handleContextAction('remove-node')");
  assert.match(inspect('#modal-root'), /Remove this step\?/, 'Removing a node always asks for confirmation.');
  evaluate(`closeModal();state.contextMenu={type:'canvas',x:20,y:20};closeContextMenu(false);`);
  assert.equal(evaluate('state.contextMenu'), null, 'A context menu can be dismissed without mutating the workflow.');
  evaluate(`state.template=__builderBefore.template;state.data.user=__builderBefore.user;state.dirty=__builderBefore.dirty;state.undo=__builderBefore.undo;state.redo=__builderBefore.redo;
    state.selected=__builderBefore.selected;state.panel=__builderBefore.panel;state.palette=__builderBefore.palette;state.pendingPlacement=__builderBefore.pendingPlacement;
    state.contextMenu=__builderBefore.contextMenu;state.mobilePanel=__builderBefore.mobilePanel;state.linkFrom=__builderBefore.linkFrom;state.route=__builderBefore.route;
    delete globalThis.__builderBefore;delete globalThis.__firstBuilderNode;delete globalThis.__secondBuilderNode;delete globalThis.__copyBuilderNode;`);

  const requiredScenarioIds = ['happy','missing_input','dependency_timeout','approval_rejection','approval_expiry',
    'revoked_role','duplicate_callback','conflicting_evidence','lost_acknowledgement','malicious_content'];
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(scenarios.map(item=>item.id))')), requiredScenarioIds,
    'The Rehearsal Lab must expose the canonical versioned ten-case catalog in order.');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify([...fixtureScenarios])')), ['happy','lost_acknowledgement'],
    'Fixture execution is restricted to the two server-approved safe cases.');
  const demoTemplates = data.templates.filter(template=>template.seed?.kind==='demonstration');
  assert.equal(demoTemplates.length, 5, 'The workspace must expose five persistent demonstration workflows.');
  for (const template of demoTemplates) {
    const sample = JSON.parse(evaluate(`JSON.stringify(sampleInput(${JSON.stringify(template.id)}))`));
    assert.deepEqual(sample, template.exampleInput, `${template.id} must supply its own realistic task example.`);
    const validation = await evaluate(`api('/api/templates/${template.id}/validate')`);
    assert.equal(validation.valid, true, `${template.id} must use its own captured validation result.`);
  }
  const scopedTemplate = demoTemplates[0];
  const scopedRun = data.runs.find(run=>run.templateId===scopedTemplate.id);
  const foreignRun = data.runs.find(run=>run.mode==='simulation'&&run.templateId!==scopedTemplate.id);
  evaluate(`globalThis.__templateBeforeLabScope=state.template;setTemplate(state.data.templates.find(item=>item.id===${JSON.stringify(scopedTemplate.id)}));state.experiments=state.data.experiments||[];state.route='lab';render();`);
  const scopedLabHtml = inspect('#app');
  assert.ok(scopedRun && scopedLabHtml.includes(scopedRun.id), 'The Lab must show runs for the selected workflow.');
  assert.ok(!foreignRun || !scopedLabHtml.includes(foreignRun.id), 'The Lab must hide simulations from other workflows.');
  assert.ok(scopedLabHtml.includes(scopedTemplate.name), 'The Lab must name the selected workflow.');
  evaluate('setTemplate(__templateBeforeLabScope);delete globalThis.__templateBeforeLabScope;');
  evaluate(`globalThis.__templateStatusBeforeReview=state.template.status;
    globalThis.__userBeforeReview=state.data.user;
    state.data.user=state.data.users.find(user=>user.role==='admin');
    state.template.status='in_review';state.route='studio';render();`);
  const inReviewStudioHtml = inspect('#app');
  assert.match(openingTag(inReviewStudioHtml, 'data-action', 'archive-template'),
    /disabled[^>]*Publish the submitted candidate before archiving it/,
    'A frozen candidate cannot be archived before its review is resolved.');
  evaluate('state.template.status=__templateStatusBeforeReview;state.data.user=__userBeforeReview;delete globalThis.__templateStatusBeforeReview;delete globalThis.__userBeforeReview;');
  evaluate(`globalThis.__templateStatusBeforeArchive=state.template.status;
    globalThis.__listedTemplateBeforeArchive=state.data.templates.find(item=>item.id===state.template.id)?.status;
    state.template.status='archived';
    const listed=state.data.templates.find(item=>item.id===state.template.id);if(listed)listed.status='archived';
    state.route='studio';state.run=null;state.runId=null;render();`);
  const archivedStudioHtml = inspect('#app');
  assert.ok(archivedStudioHtml.includes(`${data.templates[0].name} · archived`) || /· archived<\/option>/.test(archivedStudioHtml),
    'The template selector visibly marks an archived workflow.');
  assert.match(openingTag(archivedStudioHtml, 'data-action', 'start-run'),
    /disabled[^>]*Restore this archived template before starting a task/,
    'An archived template cannot start a workflow from Studio.');
  evaluate("state.route='lab';state.experiments=[];render();");
  const archivedLabHtml = inspect('#app');
  assert.match(openingTag(archivedLabHtml, 'data-action', 'experiment'),
    /disabled[^>]*Restore this archived template before rehearsing it/,
    'An archived template cannot start the required rehearsal suite.');
  for (const id of requiredScenarioIds) {
    assert.match(openingTag(archivedLabHtml, 'data-scenario', id),
      /disabled[^>]*Restore this archived template before rehearsing it/,
      `An archived template cannot start the ${id} rehearsal.`);
  }
  evaluate('startRunModal()');
  const archivedStartHtml = inspect('#modal-root');
  assert.match(optionTag(archivedStartHtml, evaluate('state.template.id')), /disabled/,
    'Archived templates are disabled in task-entry selection as a second guard.');
  assert.match(archivedStartHtml, /· archived<\/option>/,
    'Task entry visibly labels an archived template.');
  evaluate(`closeModal();state.template.status=__templateStatusBeforeArchive;
    {const listed=state.data.templates.find(item=>item.id===state.template.id);if(listed)listed.status=__listedTemplateBeforeArchive;}
    delete globalThis.__templateStatusBeforeArchive;delete globalThis.__listedTemplateBeforeArchive;`);
  evaluate(`(()=>{
    const originals={query:document.querySelector,templates:state.data.templates};
    const archived={id:'selector-archived',name:'Archived',status:'archived',publishedVersion:1,inputSchema:{type:'object'}},
      unpublished={id:'selector-draft',name:'Draft',status:'draft',inputSchema:{type:'object'}},
      published={id:'selector-published',name:'Published',status:'draft',publishedVersion:2,inputSchema:{type:'object'},
        versions:[{version:2,status:'published',snapshot:{inputSchema:{type:'object'}}}]};
    state.data.templates=[archived,unpublished,published];
    const mode={value:'fixture'},template={value:archived.id,options:[archived,unpublished,published].map(item=>({value:item.id,disabled:false})),
      get selectedOptions(){return this.options.filter(option=>option.value===this.value);}},
      scenario={value:'missing_input',options:scenarios.map(item=>({value:item.id,disabled:false})),
        get selectedOptions(){return this.options.filter(option=>option.value===this.value);}},
      textarea={value:'{}',closest(){return null;}};
    document.querySelector=function(query){
      if(query==='#run-mode')return mode;if(query==='#run-template')return template;if(query==='#run-scenario')return scenario;
      if(query==='#run-input')return textarea;if(query==='#schema-task-fields')return null;return originals.query(query);
    };
    try{
      syncRunStartOptions();
      const fixture={selected:template.value,archived:template.options[0].disabled,unpublished:template.options[1].disabled,
        published:template.options[2].disabled,scenario:scenario.value,missingDisabled:scenario.options.find(item=>item.value==='missing_input').disabled};
      mode.value='simulation';template.value=archived.id;syncRunStartOptions();
      globalThis.__runSelectorRules={fixture,simulation:{selected:template.value,archived:template.options[0].disabled,
        unpublished:template.options[1].disabled,published:template.options[2].disabled}};
    }finally{document.querySelector=originals.query;state.data.templates=originals.templates;}
  })()`);
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(__runSelectorRules)')), {
    fixture:{selected:'selector-published',archived:true,unpublished:true,published:false,scenario:'happy',missingDisabled:true},
    simulation:{selected:'selector-draft',archived:true,unpublished:false,published:false},
  }, 'Mode changes keep archived workflows disabled, enforce publication for fixtures, and select an eligible workflow.');
  evaluate('delete globalThis.__runSelectorRules');
  evaluate("state.route='lab';state.experiments=[];render();");
  const labHtml = inspect('#app');
  assert.equal((labHtml.match(/data-scenario=/g) || []).length, 10, 'The Lab renders exactly ten single-scenario actions.');
  assert.ok(!openingTag(labHtml, 'data-action', 'experiment').includes('disabled'),
    'An active template can start the required rehearsal suite.');
  for (const id of requiredScenarioIds) {
    assert.ok(!openingTag(labHtml, 'data-scenario', id).includes('disabled'),
      `An active template can start the ${id} rehearsal.`);
  }
  evaluate('startRunModal()');
  const startRunHtml = inspect('#modal-root');
  openingTag(startRunHtml, 'data-action', 'find-template');
  const artifactInput = startRunHtml.match(/<input[^>]*id="run-artifacts"[^>]*>/)?.[0] || '';
  assert.match(artifactInput, /type="file"/, 'Task attachments use a file input.');
  assert.match(artifactInput, /\bmultiple\b/, 'Task entry accepts its bounded set of attachments together.');
  for (const extension of ['.json','.txt','.csv']) assert.ok(artifactInput.includes(extension),
    `Task attachment input must retain ${extension} support.`);
  assert.match(startRunHtml, /Files are hashed and stored locally\. Their content is not executed or included in default exports\./,
    'Task entry explains attachment storage and export boundaries.');
  await assert.rejects(async()=>evaluate(`(async()=>{const originalQuery=document.querySelector;
    document.querySelector=query=>query==='#run-artifacts'?{files:[
      {name:'one.txt',type:'text/plain',size:184320},{name:'two.txt',type:'text/plain',size:184320},
      {name:'three.txt',type:'text/plain',size:184320}]}:originalQuery(query);
    try{return await readTaskArtifacts();}finally{document.querySelector=originalQuery;}})()`), /512 KiB total/,
    'Task entry rejects an attachment set above the server aggregate limit before reading file content.');
  const templateMatches = await evaluate("api('/api/templates/find?q=service')");
  assert.ok(templateMatches.matches.every(item=>item.published_version),
    'The task-entry finder offers published templates only.');
  for (const id of requiredScenarioIds) {
    const option = optionTag(startRunHtml, id);
    assert.equal(/\bdisabled\b/.test(option), !['happy','lost_acknowledgement'].includes(id),
      `Fixture restriction is incorrect for ${id}.`);
  }
  evaluate(`(()=>{
    const publishedSchema={type:'object',required:['subject','amount','priority','profile'],properties:{
      requestId:{type:'string'},subject:{type:'string',maxLength:120},amount:{type:'number',minimum:0,maximum:100000},
      priority:{type:'string',enum:['normal','urgent']},notes:{type:'string'},
      profile:{type:'object',required:['displayName'],properties:{displayName:{type:'string'},nickname:{type:'string'},metadata:{type:'object'}}},
      tags:{type:'array',items:{type:'string'}},nullableNote:{type:['string','null']}}};
    const draftSchema={type:'object',required:['draftOnly'],properties:{draftOnly:{type:'string'}}};
    state.data.templates.push({id:'ui-schema-contract',name:'Schema contract',status:'draft',publishedVersion:3,
      inputSchema:draftSchema,versions:[{version:3,status:'published',snapshot:{inputSchema:{type:'object',required:['legacyOnly'],properties:{legacyOnly:{type:'string'}}}}}],
      releaseCompatibility:{'3':{snapshot:{inputSchema:publishedSchema}}}});
    const originalQuery=document.querySelector;
    const textarea={value:JSON.stringify({subject:'Current subject',amount:25,priority:'normal',
      profile:{displayName:'Current name',metadata:{source:'raw'}},tags:['one'],nullableNote:null}),
      closest(){return {insertAdjacentHTML(position,html){globalThis.__taskFieldMarkup=html;}};}};
    const selector={value:'ui-schema-contract'},mode={value:'fixture'};
    document.querySelector=function(query){
      if(query==='#run-input')return textarea;
      if(query==='#run-template')return selector;
      if(query==='#run-mode')return mode;
      if(query==='#schema-task-fields')return null;
      return originalQuery(query);
    };
    try{
      decorateTaskInputForm();
      globalThis.__publishedTaskFieldMarkup=globalThis.__taskFieldMarkup;
      mode.value='simulation';decorateTaskInputForm();
      globalThis.__draftTaskFieldMarkup=globalThis.__taskFieldMarkup;
    }finally{
      document.querySelector=originalQuery;
      state.data.templates=state.data.templates.filter(item=>item.id!=='ui-schema-contract');
    }
  })()`);
  const taskFieldMarkup = evaluate('__publishedTaskFieldMarkup');
  assert.match(taskFieldMarkup, /Task fields from the published contract/,
    'Fixture entry renders controls from the pinned published contract.');
  const draftTaskFieldMarkup = evaluate('__draftTaskFieldMarkup');
  assert.match(draftTaskFieldMarkup, /Task fields from the draft contract/,
    'Simulation entry renders controls from the current draft contract.');
  assert.ok(draftTaskFieldMarkup.includes('data-task-field="draftOnly"') && !draftTaskFieldMarkup.includes('data-task-field="subject"'),
    'Changing to simulation replaces pinned-release controls with draft controls.');
  assert.ok(!taskFieldMarkup.includes('data-task-field="requestId"'),
    'The server-owned request identifier is never exposed as an editable task field.');
  assert.ok(!taskFieldMarkup.includes('data-task-field="legacyOnly"'),
    'Fixture entry uses the server-bound executable compatibility snapshot, not stale historical fields.');
  const taskControl = field => taskFieldMarkup.match(new RegExp(`<(?:input|select)[^>]*data-task-field="${field}"[^>]*>`))?.[0] || '';
  assert.match(taskControl('subject'), /required[^>]*aria-required="true"/,
    'Required string fields retain browser and assistive-technology semantics.');
  for (const attribute of ['type="number"','step="any"','min="0"','max="100000"']) {
    assert.ok(taskControl('amount').includes(attribute), `Numeric task fields must retain ${attribute}.`);
  }
  assert.match(taskControl('priority'), /data-task-enum="true"[^>]*required[^>]*aria-required="true"/,
    'Enumerated task fields render as required bounded choices.');
  assert.ok(!/\brequired\b/.test(taskControl('notes')), 'Optional task fields remain optional.');
  assert.match(taskControl('profile.displayName'), /required[^>]*aria-required="true"/,
    'A nested field is required only when its complete parent path and the field are required.');
  assert.ok(!/\brequired\b/.test(taskControl('profile.nickname')), 'Optional nested fields remain optional.');
  for (const field of ['profile.metadata','tags','nullableNote']) {
    assert.equal(taskControl(field), '', `${field} must remain in raw JSON instead of an unsafe scalar control.`);
  }
  evaluate(`(()=>{const input={subject:'Before',profile:{displayName:'Name',metadata:{source:'raw'}},tags:['one'],nullableNote:null};
    setTaskField(input,'subject','After');globalThis.__preservedComplexInput=input;})()`);
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(__preservedComplexInput)')), {
    subject:'After',profile:{displayName:'Name',metadata:{source:'raw'}},tags:['one'],nullableNote:null,
  }, 'Updating a safe scalar field preserves complex JSON values exactly.');
  evaluate('delete globalThis.__taskFieldMarkup;delete globalThis.__publishedTaskFieldMarkup;delete globalThis.__draftTaskFieldMarkup;delete globalThis.__preservedComplexInput');
  evaluate('closeModal()');
  evaluate("state.data.user=state.data.users.find(u=>u.role==='admin');state.template.status='in_review';state.route='agents';render();");
  assert.ok(!openingTag(inspect('#app'), 'data-action', 'new-agent').includes('disabled'),
    'An administrator can register an agent independently of the selected template review state.');
  evaluate("state.data.user=state.data.users.find(u=>u.role==='reviewer');render();");
  assert.match(openingTag(inspect('#app'), 'data-action', 'new-agent'), /disabled[^>]*Administrator role required/,
    'Non-admin users receive an explicit registry permission reason.');

  evaluate("state.template.status='draft';state.route='studio';");
  await evaluate('reviewRelease()');
  let publish = openingTag(inspect('#modal-root'), 'data-action', 'publish-release');
  assert.match(publish, /disabled[^>]*Submit the candidate for review before publishing/,
    'A reviewer cannot publish a draft that is not in review.');
  assert.equal(nodes.get('#app').attributes.inert, '', 'Opening a modal makes the app background inert.');
  assert.equal(nodes.get('#app').attributes['aria-hidden'], 'true', 'Opening a modal hides the background from assistive technology.');
  evaluate('closeModal()');
  assert.ok(!('inert' in nodes.get('#app').attributes), 'Closing a modal restores background interaction.');
  assert.ok(!('aria-hidden' in nodes.get('#app').attributes), 'Closing a modal restores the accessibility tree.');
  let restoredFocus = 0;
  const opener = {id: 'test-opener', tagName: 'BUTTON', isConnected: true,
    focus() { restoredFocus++; }, closest(selector) { return selector === '#app' ? nodes.get('#app') : null; },
    getAttribute() { return null; }};
  document.activeElement = opener;
  evaluate("modal('Focus check','<p>Accessible dialog</p>');closeModal();");
  assert.equal(restoredFocus, 1, 'Closing a modal restores its opener when that control still exists.');
  evaluate("state.renderedKey=state.route+'/'+(state.runId||'');render();");
  assert.equal(restoredFocus, 2, 'A same-page render preserves the focused control when it still exists.');
  document.activeElement = null;
  evaluate("state.template.status='in_review';");
  await evaluate('reviewRelease()');
  publish = openingTag(inspect('#modal-root'), 'data-action', 'publish-release');
  assert.ok(!publish.includes('disabled'), 'A reviewer can publish an in-review candidate.');
  evaluate('closeModal()');

  const waitingHtml = evaluate(`(()=>{const originalRun=state.run;const run=clone(state.data.runs[0]);
    run.status='waiting_execution';run.allowedActions=['execute','remind'];run.nodes[0].status='waiting_execution';
    state.run=run;const html=runDetail();state.run=originalRun;return html;})()`);
  assert.ok(openingTag(waitingHtml, 'data-run-remind', data.runs[0].nodes[0].nodeId),
    'Manual execution waits expose the same reminder action as approval waits.');
  const lifecyclePolicy = JSON.parse(evaluate(`(()=>{const originalRun=state.run,run=clone(state.data.runs[0]),approval=run.nodes[0],manual=run.nodes[1];
    run.status='waiting_approval';approval.status='waiting_approval';manual.status='waiting_execution';
    run.allowedActions=['approve','reject','remind','execute','cancel'];
    run.actionPolicy=[
      {action:'approve',nodeId:approval.nodeId,allowed:false,reason:'Reviewer role required.'},
      {action:'reject',nodeId:approval.nodeId,allowed:false,reason:'Reviewer role required.'},
      {action:'remind',nodeId:approval.nodeId,allowed:false,reason:'Initiator or eligible role required.'},
      {action:'execute',nodeId:manual.nodeId,allowed:true,reason:'Contributor role is eligible.'},
      {action:'remind',nodeId:manual.nodeId,allowed:true,reason:'Eligible to capture a scoped reminder.'},
      {action:'cancel',nodeId:null,allowed:false,reason:'Initiator or operations role required.'}];
    state.run=run;const html=runDetail();run.status='failed';const terminalHtml=runDetail();state.run=originalRun;
    const tag=(attribute,value)=>html.match(new RegExp('<button[^>]*'+attribute+'="'+value+'"[^>]*>'))?.[0]||'';
    return JSON.stringify({approve:tag('data-run-approve',approval.nodeId),reject:tag('data-run-reject',approval.nodeId),
      approvalReminder:tag('data-run-remind',approval.nodeId),execute:tag('data-run-execute',manual.nodeId),
      manualReminder:tag('data-run-remind',manual.nodeId),cancel:tag('data-action','cancel-run'),terminalHasCancel:terminalHtml.includes('data-action="cancel-run"')});})()`));
  for (const action of ['approve','reject','approvalReminder','cancel']) {
    assert.match(lifecyclePolicy[action], /aria-disabled="true"/, `${action} must expose the server's denied action policy.`);
    assert.match(lifecyclePolicy[action], /data-action-denied=/, `${action} must remain focusable and explain why it is denied.`);
    assert.doesNotMatch(lifecyclePolicy[action], /\sdisabled(?:\s|>)/, `${action} must not become an inert native-disabled control.`);
  }
  for (const action of ['execute','manualReminder']) {
    assert.doesNotMatch(lifecyclePolicy[action], /aria-disabled|data-action-denied|\sdisabled(?:\s|>)/, `${action} must follow the server's allowed action policy.`);
  }
  assert.equal(lifecyclePolicy.terminalHasCancel, false, 'Terminal failed runs do not expose a cancellation action the server rejects.');
  const approvalHandoff = JSON.parse(evaluate(`(()=>{const originalRun=state.run,originalUser=state.data.user,run=clone(state.data.runs[0]),approval=run.nodes[0];
    state.data.user=state.data.users.find(user=>user.role==='admin');run.status='waiting_approval';approval.status='waiting_approval';
    run.actionPolicy=[{action:'approve',nodeId:approval.nodeId,allowed:false,reason:'Reviewer role required.'},
      {action:'reject',nodeId:approval.nodeId,allowed:false,reason:'Reviewer role required.'},
      {action:'remind',nodeId:approval.nodeId,allowed:true,reason:'Eligible to capture a reminder.'},
      {action:'cancel',nodeId:null,allowed:true,reason:'Initiator may cancel.'}];
    state.run=run;const html=runDetail(),tag=html.match(new RegExp('<button[^>]*data-run-approve="'+approval.nodeId+'"[^>]*>'))?.[0]||'';
    state.run=originalRun;state.data.user=originalUser;return JSON.stringify({tag,hasReason:html.includes('Reviewer role required.'),hasInstruction:html.includes('switch to Reviewer and continue to the required review')});})()`));
  assert.match(approvalHandoff.tag, /data-role-handoff="reviewer"/, 'A denied approval offers an explicit reviewer-account handoff.');
  assert.match(approvalHandoff.tag, /data-intended-action="approve"/, 'The handoff retains the exact requested action.');
  assert.match(approvalHandoff.tag, /data-action-node-id=/, 'The handoff remains scoped to the waiting node.');
  assert.match(approvalHandoff.tag, /action-role-handoff/, 'The reviewer handoff has an interactive visual state.');
  assert.doesNotMatch(approvalHandoff.tag, /\sdisabled(?:\s|>)/, 'The reviewer handoff is clickable instead of natively disabled.');
  assert.equal(approvalHandoff.hasReason, true, 'The server denial reason is visible beside the workflow action.');
  assert.equal(approvalHandoff.hasInstruction, true, 'The workflow explains that approval still continues to a review step.');

  const factoryHandoff = JSON.parse(evaluate(`(()=>{const originalFactory=state.factory,originalUser=state.data.user;
    state.data.user=state.data.users.find(user=>user.role==='admin');state.factory={run:{id:'factory-approval',status:'awaiting_approval',allowedActions:[]}};
    const denied=factoryPendingAction({toolId:'jira.issues.create',actionHash:'${'c'.repeat(64)}',contentHash:'${'c'.repeat(64)}',arguments:{summary:'Prepared incident'}});
    state.data.user=state.data.users.find(user=>user.role==='reviewer');state.factory.run.allowedActions=['approve','reject'];
    const allowed=factoryPendingAction({toolId:'jira.issues.create',actionHash:'${'c'.repeat(64)}',contentHash:'${'c'.repeat(64)}',arguments:{summary:'Prepared incident'}});
    state.factory=originalFactory;state.data.user=originalUser;return JSON.stringify({denied,allowed});})()`));
  const factoryReviewDenied = openingTag(factoryHandoff.denied, 'data-action', 'factory-review-action');
  assert.match(factoryReviewDenied, /data-role-handoff="reviewer"/, 'Factory exact-action review offers the same reviewer handoff.');
  assert.doesNotMatch(factoryReviewDenied, /\sdisabled(?:\s|>)/, 'Factory reviewer handoff remains clickable.');
  assert.match(factoryHandoff.denied, /Reviewer role required\./, 'Factory exact-action review visibly explains the denial.');
  assert.match(factoryHandoff.denied, /inspect the exact action/, 'Factory handoff promises review, never automatic approval.');
  const factoryReviewAllowed = openingTag(factoryHandoff.allowed, 'data-action', 'factory-review-action');
  assert.doesNotMatch(factoryReviewAllowed, /aria-disabled|data-role-handoff|\sdisabled(?:\s|>)/, 'Server-authorized Factory approval opens directly for a reviewer.');
  const factoryContinuation = JSON.parse(await evaluate(`(async()=>{const originalFactory=state.factory,originalCatalog=state.data.agentFactory,originalUser=state.data.user,originalRoute=state.route,
      prepared={toolId:'jira.issues.create',actionHash:'${'f'.repeat(64)}',contentHash:'${'f'.repeat(64)}',arguments:{summary:'Factory handoff exact payload'}},
      run={id:'factory-handoff-run',specId:'factory-handoff-spec',specName:'Factory handoff agent',status:'awaiting_approval',allowedActions:['approve','reject'],pendingAction:prepared};
    state.data.user=state.data.users.find(user=>user.role==='admin');state.route='runs';state.data.agentFactory={specs:[],tools:[],runs:[run],scenarios:[],provider:{configured:false}};
    state.factory=null;const f=factoryState();f.runs=[run];f.run=run;f.selectedRunId=run.id;f.loaded=true;
    const element={dataset:{roleHandoff:'reviewer',intendedAction:'factory-review-action',action:'factory-review-action'},disabled:false,
      setAttribute(){},removeAttribute(){}};await continueActionAsRole(element);
    const result={role:state.data.user.role,runId:factoryState().run.id,status:factoryState().run.status,modal:document.querySelector('#modal-root').innerHTML};
    closeModal();state.factory=originalFactory;state.data.agentFactory=originalCatalog;state.data.user=originalUser;state.route=originalRoute;return JSON.stringify(result);})()`));
  assert.equal(factoryContinuation.role, 'reviewer', 'Factory action handoff changes to the required reviewer account.');
  assert.equal(factoryContinuation.runId, 'factory-handoff-run', 'Factory action handoff reloads the exact same durable session.');
  assert.equal(factoryContinuation.status, 'awaiting_approval', 'Factory role switching never approves the prepared action automatically.');
  assert.match(factoryContinuation.modal, /Factory handoff exact payload/, 'The reloaded Factory review retains its exact payload.');
  assert.match(factoryContinuation.modal, /data-factory-decision="approve"/, 'Factory approval still requires a separate explicit confirmation.');
  evaluate(`(()=>{const run=clone(state.data.runs[0]),node=run.nodes[0];node.status='waiting_approval';
    node.approvalPacket={actions:[{effectId:'effect-write-1',nodeId:'write',label:'Create work item',operationGeneration:1,
      actionTarget:{method:'create',resource:'jira-work-item',connectionId:'fixture-ticket'},
      payload:{subject:'Exact subject'},actionFingerprint:'${'a'.repeat(64)}',approvalEnvelopeHash:'${'b'.repeat(64)}'}]};
    state.run=run;decisionModal(node.nodeId,'approve');})()`);
  const decisionHtml = inspect('#modal-root');
  assert.match(decisionHtml, /Exact subject/, 'Approval shows the exact prepared payload.');
  assert.match(decisionHtml, /Action fingerprint/, 'Approval shows its action binding.');
  assert.match(decisionHtml, /Effect effect-write-1/, 'Approval shows the exact effect reference.');
  assert.ok(!openingTag(decisionHtml, 'data-confirm-decision', 'approve').includes('disabled'),
    'A complete prepared-action packet can be approved.');
  const preparedReference = JSON.parse(evaluate(`JSON.stringify(preparedActionReference({effectId:'effect-write-1',nodeId:'write',
    operationGeneration:1,actionFingerprint:'${'a'.repeat(64)}',approvalEnvelopeHash:'${'b'.repeat(64)}'}))`));
  assert.deepEqual(preparedReference, {effectId:'effect-write-1',nodeId:'write',operationGeneration:1,
    actionFingerprint:'a'.repeat(64),approvalEnvelopeHash:'b'.repeat(64)},
    'Approval submission retains every exact prepared-action reference.');
  evaluate(`(()=>{const node=state.run.nodes[0];delete node.approvalPacket.actions[0].effectId;
    decisionModal(node.nodeId,'approve');})()`);
  const incompleteDecisionHtml = inspect('#modal-root');
  assert.match(incompleteDecisionHtml, /packet is incomplete/i,
    'An incomplete prepared-action packet produces a visible blocking explanation.');
  assert.match(openingTag(incompleteDecisionHtml, 'data-confirm-decision', 'approve'), /disabled/,
    'An incomplete prepared-action packet cannot be approved.');
  evaluate(`(()=>{const node=state.run.nodes[0];decisionModal(node.nodeId,'reject');})()`);
  assert.match(inspect('#modal-root'), /id="decision-comment"[^>]*required[^>]*aria-required="true"/,
    'The rejection reason is exposed as required to browsers and assistive technology.');
  const handoffContinuation = JSON.parse(await evaluate(`(async()=>{closeModal();const originalRun=state.run,originalRunId=state.runId,originalUser=state.data.user,originalRoute=state.route,
      run=clone(state.data.runs[0]),node=run.nodes[0];
    state.data.user=state.data.users.find(user=>user.role==='admin');state.route='runs';state.runId=run.id;state.run=run;run.status='waiting_approval';node.status='waiting_approval';
    node.approvalPacket={actions:[{effectId:'effect-handoff-1',nodeId:node.nodeId,label:'Prepared handoff action',operationGeneration:1,
      actionTarget:{method:'create',resource:'jira-work-item',connectionId:'fixture-ticket'},payload:{summary:'Handoff exact payload'},
      actionFingerprint:'${'d'.repeat(64)}',approvalEnvelopeHash:'${'e'.repeat(64)}'}]};
    run.actionPolicy=[{action:'approve',nodeId:node.nodeId,allowed:true,reason:'Reviewer may inspect this action.'}];
    const element={dataset:{roleHandoff:'reviewer',intendedAction:'approve',actionNodeId:node.nodeId},disabled:false,
      setAttribute(){},removeAttribute(){}};await continueActionAsRole(element);
    const result={role:state.data.user.role,runId:state.run.id,status:state.run.nodes[0].status,modal:document.querySelector('#modal-root').innerHTML};
    closeModal();state.run=originalRun;state.runId=originalRunId;state.data.user=originalUser;state.route=originalRoute;return JSON.stringify(result);})()`));
  assert.equal(handoffContinuation.role, 'reviewer', 'The action handoff changes to the required local reviewer account.');
  assert.equal(handoffContinuation.runId, data.runs[0].id, 'The handoff retains the exact workflow run.');
  assert.equal(handoffContinuation.status, 'waiting_approval', 'Switching roles does not approve the action automatically.');
  assert.match(handoffContinuation.modal, /Handoff exact payload/, 'The continued review shows the exact prepared payload.');
  assert.match(handoffContinuation.modal, /data-confirm-decision="approve"/, 'The reviewer must still explicitly confirm the action.');
  evaluate('closeModal();state.run=null;');

  evaluate(`reminderModal({deliveryStatus:'sent',status:'captured',provider:'local-notification-capture',
    connectionId:'fixture-outbox',connectionGeneration:3,deepLink:'/#review',subject:'Action requested',
    body:'Captured locally; no external email was sent.',recipients:[{id:'reviewer-local',name:'Riley Reviewer',role:'reviewer'}]})`);
  const reminderHtml = inspect('#modal-root');
  for (const visible of ['Sent to local capture','No email or external message was sent','Riley Reviewer','Reviewer',
    'local-notification-capture','fixture-outbox','generation 3','/#review']) {
    assert.ok(reminderHtml.includes(visible), `Reminder receipt must render ${visible}.`);
  }
  evaluate('closeModal()');

  evaluate("state.pollStale=true;state.pollError='offline';state.route='runs';state.runId=null;render();");
  assert.match(inspect('#app'), /Reconnecting/,
    'Polling failures produce a visible reconnecting status.');
  evaluate('state.pollStale=false;state.pollError="";render();');

  const graphHtml = evaluate('graph(state.template)');
  assert.ok(graphHtml.includes('class="graph-node-select'), 'Graph nodes retain an explicit keyboard-selectable control.');
  assert.ok(!/<div class="graph-node[^"]*"[^>]*(?:data-node|data-step-data|role="button")/.test(graphHtml),
    'Graph wrappers are non-interactive so their port buttons are not nested controls.');
  for (const control of graphHtml.match(/<button[^>]*class="graph-node-select[\s\S]*?<\/button>/g) || []) {
    assert.equal((control.match(/<button/g) || []).length, 1, 'A graph node selection button cannot contain another button.');
  }
  evaluate(`globalThis.__templateBeforeMappingTest=clone(state.template);
    globalThis.__agentsBeforeMappingTest=clone(state.data.agents);
    state.template.inputSchema={type:'object',properties:{taskId:{type:'string'},attempt:{type:'integer'},
      customer:{type:'object',properties:{tier:{type:'string'}}}}};
    const intakeAgent=state.data.agents.find(item=>item.id==='intake');
    intakeAgent.inputSchema={type:'object',properties:{intakeOnly:{type:'string'}}};
    intakeAgent.outputSchema={type:'object',properties:{normalizedRequest:{type:'object'}}};
    const csrAgent=state.data.agents.find(item=>item.id==='csr');
    csrAgent.inputSchema={type:'object',properties:{inputOnlyTrap:{type:'string'}}};
    csrAgent.outputSchema={type:'object',properties:{riskScore:{type:'number'},risk:{type:'object',properties:{score:{type:'number'}}}}};
    const approvalAgent=state.data.agents.find(item=>item.id==='approval');
    approvalAgent.outputSchema={type:'object',properties:{approved:{type:'boolean'}}};
    const enrichAgent=state.data.agents.find(item=>item.id==='enrich');
    enrichAgent.outputSchema={type:'object',properties:{notUpstream:{type:'string'}}};
    const ticketAgent=state.data.agents.find(item=>item.id==='ticket');
    ticketAgent.inputSchema={type:'object',properties:{summary:{type:'string'},amount:{type:['number','null']},
      request:{type:'object',properties:{summary:{type:'string'}}}}};
    state.selected='ticket';`);
  const declaredCatalog = JSON.parse(evaluate("JSON.stringify(mappingSourceCatalog(state.template.nodes.find(item=>item.id==='ticket')))") );
  const declaredPaths = declaredCatalog.sources.map(source=>source.path);
  for (const path of ['input.taskId','input.attempt','input.customer.tier','nodes.intake.output.normalizedRequest',
    'nodes.csr.output.riskScore','nodes.csr.output.risk.score','nodes.approval.output.approved']) {
    assert.ok(declaredPaths.includes(path), `Typed mapping choices must include ${path}.`);
  }
  for (const path of ['input.intakeOnly','nodes.csr.output.inputOnlyTrap','nodes.enrich.output.notUpstream']) {
    assert.ok(!declaredPaths.includes(path), `Mapping choices must not derive ${path} from an input schema or non-upstream agent.`);
  }
  evaluate("state.template.edges.push({id:'mapping-bypass-test',source:'intake',target:'ticket'});");
  const bypassCatalog = JSON.parse(evaluate("JSON.stringify(mappingSourceCatalog(state.template.nodes.find(item=>item.id==='ticket')))"));
  const bypassPaths = bypassCatalog.sources.map(source=>source.path);
  assert.ok(bypassPaths.includes('nodes.intake.output.normalizedRequest'),
    'A source that dominates every route remains available.');
  assert.ok(!bypassPaths.includes('nodes.csr.output.riskScore') && !bypassPaths.includes('nodes.approval.output.approved'),
    'Branch-local upstream outputs are hidden when a route can bypass them.');
  assert.ok(bypassCatalog.unavailable.some(source=>source.path==='nodes.csr.output.riskScore'),
    'Path-unavailable declared fields are retained as an explainable exclusion.');
  evaluate("state.template.edges=state.template.edges.filter(edge=>edge.id!=='mapping-bypass-test');");
  evaluate('mappingModal()');
  const declaredMappingHtml = inspect('#modal-root');
  for (const visible of ['input.taskId','input.customer.tier','string · Template input','nodes.csr.output.riskScore',
    'nodes.csr.output.risk.score','number · Prepare CSR request','Target · string','Target · number | null','request.summary']) {
    assert.ok(declaredMappingHtml.includes(visible), `Typed mapping UI must render ${visible}.`);
  }
  const stringSources = declaredMappingHtml.match(/<datalist id="mapping-sources-0">([\s\S]*?)<\/datalist>/)?.[1] || '';
  const numberSources = declaredMappingHtml.match(/<datalist id="mapping-sources-1">([\s\S]*?)<\/datalist>/)?.[1] || '';
  assert.ok(stringSources.includes('input.taskId') && !stringSources.includes('nodes.csr.output.riskScore'),
    'String targets suggest only type-compatible declared sources.');
  assert.ok(numberSources.includes('input.attempt') && numberSources.includes('nodes.csr.output.riskScore') && !numberSources.includes('input.taskId'),
    'Number targets accept integer and number sources while excluding strings.');
  assert.match(declaredMappingHtml, /upstream and available on every path/i,
    'The mapping dialog explains the server path-availability requirement.');
  assert.match(declaredMappingHtml, /never evaluated as executable expressions/i,
    'The mapping dialog explains that source paths are data, not code.');
  counts.mappingModals++;
  evaluate('closeModal();delete state.template.inputSchema;mappingModal();');
  const fallbackMappingHtml = inspect('#modal-root');
  assert.ok(fallbackMappingHtml.includes('input.caseId') && fallbackMappingHtml.includes('string · Current request'),
    'Templates without an input schema fall back to typed current request fields.');
  assert.ok(!fallbackMappingHtml.includes('input.intakeOnly'),
    'The current-request fallback never borrows fields from the intake agent input schema.');
  counts.mappingModals++;
  evaluate(`closeModal();state.template=__templateBeforeMappingTest;state.data.agents=__agentsBeforeMappingTest;
    delete globalThis.__templateBeforeMappingTest;delete globalThis.__agentsBeforeMappingTest;state.selected=null;`);
  evaluate("state.template.status='draft';state.data.user=state.data.users.find(u=>u.role==='admin');state.route='studio';state.run=null;state.runId=null;render();");
  evaluate("state.data.user=state.data.users.find(u=>u.role==='admin');state.route='studio';state.panel='node';");
  for (const node of data.templates[0].nodes) {
    evaluate(`state.selected=${JSON.stringify(node.id)};render();`);
    inspect('#app');
    counts.inspectorRenders++;
  }
  const normalizedCondition = JSON.parse(evaluate(`JSON.stringify(normalizeControlConfig('condition',{
    rule:'{"op":"gte","path":"amount","value":100}',mergeId:'join-test'}))`));
  assert.deepEqual(normalizedCondition, {rule:{op:'gte',path:'amount',value:100},mergeId:'join-test'},
    'Condition rules are parsed as JSON data and retain the paired merge.');
  assert.deepEqual(JSON.parse(evaluate("JSON.stringify(normalizeControlConfig('parallel',{joinId:'join-test'}))")),
    {joinId:'join-test'}, 'Parallel splits retain their paired Join.');
  assert.deepEqual(JSON.parse(evaluate("JSON.stringify(normalizeControlConfig('join',{joinMode:'all'}))")),
    {joinMode:'all'}, 'Join configuration records the deterministic all-branches mode.');
  assert.deepEqual(JSON.parse(evaluate("JSON.stringify(normalizeControlConfig('outcome',{outcome:'rejected',reason:'Policy failed'}))")),
    {outcome:'rejected',reason:'Policy failed'}, 'Outcome configuration records both status and reason.');
  assert.throws(() => evaluate("normalizeControlConfig('condition',{rule:'not-json',mergeId:'join-test'})"), /valid JSON/,
    'Malformed rule JSON is rejected before it can enter the draft.');
  assert.doesNotMatch(appSource, /\beval\s*\(|\bFunction\s*\(/,
    'The frontend must never evaluate condition input as executable JavaScript.');
  const runExportStart = appSource.indexOf("case'export-run':");
  const runExportAction = runExportStart < 0 ? '' : appSource.slice(runExportStart, appSource.indexOf('break;', runExportStart));
  assert.ok(runExportAction.includes("/export`,{method:'POST',body:{}})"),
    'Run export must use the audited POST endpoint rather than an unaudited read request.');
  assert.match(runExportAction, /prepared and audited/i,
    'Successful run export feedback must state that the export was audited.');

  evaluate(`globalThis.__templateBeforeControlTest=clone(state.template);
    for(const item of [
      {id:'condition-test-agent',implementationId:'condition',name:'Condition',kind:'control',sideEffects:'none',inputSchema:{},outputSchema:{}},
      {id:'parallel-test-agent',implementationId:'parallel',name:'Parallel split',kind:'control',sideEffects:'none',inputSchema:{},outputSchema:{}},
      {id:'join-test-agent',implementationId:'join',name:'Join',kind:'control',sideEffects:'none',inputSchema:{},outputSchema:{}},
      {id:'outcome-test-agent',implementationId:'outcome',name:'Outcome',kind:'control',sideEffects:'none',inputSchema:{},outputSchema:{}}
    ])if(!state.data.agents.some(agent=>agent.id===item.id))state.data.agents.push(item);
    state.template.nodes.push(
      {id:'condition-test',agentId:'condition-test-agent',label:'Choose path',x:0,y:0,config:{rule:{op:'exists',path:'customerId'},mergeId:'join-test'}},
      {id:'branch-a-test',agentId:'intake',label:'Match path',x:0,y:0,config:{}},
      {id:'branch-b-test',agentId:'intake',label:'Default path',x:0,y:0,config:{}},
      {id:'parallel-test',agentId:'parallel-test-agent',label:'Parallel',x:0,y:0,config:{joinId:'join-test'}},
      {id:'join-test',agentId:'join-test-agent',label:'Join',x:0,y:0,config:{joinMode:'all'}},
      {id:'outcome-test',agentId:'outcome-test-agent',label:'Outcome',x:0,y:0,config:{outcome:'rejected',reason:'Policy failed'}});
    state.template.edges.push(
      {id:'condition-match-test',source:'condition-test',target:'branch-a-test',branch:'match'},
      {id:'condition-default-test',source:'condition-test',target:'branch-b-test',branch:'default'});`);
  for (const [nodeId, fields] of [
    ['condition-test',['control-rule','control-merge','control-match-target','control-default-target']],
    ['parallel-test',['control-join']],
    ['join-test',['control-join-mode']],
    ['outcome-test',['control-outcome-status','control-outcome-reason']],
  ]) {
    evaluate(`state.selected=${JSON.stringify(nodeId)};controlConfigModal();`);
    const html = inspect('#modal-root');
    for (const field of fields) assert.ok(html.includes(`id="${field}"`), `${nodeId} is missing ${field}.`);
    evaluate('closeModal()');
  }
  evaluate('state.template=__templateBeforeControlTest;delete globalThis.__templateBeforeControlTest;state.selected=null;');

  const firstRunId = data.runs[0].id;
  assert.deepEqual(JSON.parse(evaluate(`JSON.stringify(Object.fromEntries(
    ['prepared','dispatched','acknowledged','unknown','suppressed','expired'].map(status=>[status,statuses[status]])))`)), {
    prepared:'amber',dispatched:'blue',acknowledged:'green',unknown:'red',suppressed:'blue',expired:'red',
  }, 'Every durable effect lifecycle state has an intentional status color.');
  evaluate(`state.data.runEvidence??={};state.data.runEvidence[${JSON.stringify(firstRunId)}]??={runId:${JSON.stringify(firstRunId)},templateVersion:1,items:[],decisions:[]};
    state.data.runEvidence[${JSON.stringify(firstRunId)}].evidenceGraph={
      sources:[{id:'source:test'}],transformations:[],evidence:[{id:'evidence:test'}],decisionPackets:[],
      claims:[{id:'claim:test',text:'Recorded workflow outcome',claim_type:'run-outcome',value:'completed',status:'supported',supporting_evidence_ids:['evidence:test'],conflicting_evidence_ids:[]}],
      actionReceipts:[{id:'receipt:test',state:'acknowledged',action_fingerprint:'receipt-fingerprint',operation_key:'operation-test',provider_reference:'TICKET-1'}]};
    state.data.runEffects??={};state.data.runEffects[${JSON.stringify(firstRunId)}]={runId:${JSON.stringify(firstRunId)},summary:{total:1,states:{acknowledged:1}},effects:[{
      id:'effect:test',nodeId:'ticket',state:'acknowledged',actionFingerprint:'effect-fingerprint',approvalEnvelopeHash:'approval-binding',operationKey:'operation-test',operationGeneration:1,resourceId:'TICKET-1',payload:{secret:'TOP-SECRET-PAYLOAD'}}]};`);
  evaluate('state.run=state.data.runs[0];state.runId=state.run.id;');
  assert.ok(evaluate('runDetail()').includes('data-action="run-effects"'), 'A run exposes its effect ledger from the pinned graph view.');
  await evaluate('effectsModal()');
  const effectHtml = inspect('#modal-root');
  for (const visible of ['Acknowledged','effect-fingerprint','approval-binding']) assert.ok(effectHtml.includes(visible), `Effect view must show ${visible}.`);
  assert.ok(!effectHtml.includes('TOP-SECRET-PAYLOAD') && !effectHtml.includes('&quot;secret&quot;'),
    'Effect view uses an allowlist and never renders effect payloads or secrets.');
  counts.effectModals++;
  evaluate('closeModal()');
  for (let runIndex = 0; runIndex < data.runs.length; runIndex++) {
    evaluate(`state.run=state.data.runs[${runIndex}];state.runId=state.run.id;`);
    await evaluate('evidenceModal()');
    const evidenceHtml = inspect('#modal-root');
    assert.ok(evidenceHtml.includes(data.runs[runIndex].id));
    if (runIndex === 0) {
      for (const visible of ['Evidence graph claims','Recorded workflow outcome','Action receipts','receipt-fingerprint']) {
        assert.ok(evidenceHtml.includes(visible), `Evidence graph must render ${visible}.`);
      }
    }
    counts.evidenceModals++;
    if (data.repairs?.[data.runs[runIndex].id]) {
      await evaluate('repairModal()');
      inspect('#modal-root');
      counts.repairModals++;
    }
  }
  const capturedValidation = await evaluate("api('/api/templates/'+state.template.id+'/validate')");
  assert.equal(capturedValidation.valid, (data.capturedValidations?.[data.templates[0].id] || data.capturedValidation || data.validation).valid,
    'Preview validation must return the captured server result.');
  const capturedDiff = await evaluate("api('/api/templates/'+state.template.id+'/diff')");
  assert.ok(Array.isArray(capturedDiff.changes), 'Preview release comparison must return captured changes.');
  evaluate(`globalThis.__originalApi=api;globalThis.__experimentBody=null;
    api=async(path,options={})=>{
      if(path==='/api/experiments'&&options.method==='POST'){
        globalThis.__experimentBody=clone(options.body);return {runs:Array(10).fill('run')};
      }
      if(path==='/api/runs')return clone(state.data.runs);
      if(path.startsWith('/api/experiments?'))return [];
      throw new Error('Unexpected API request in experiment contract: '+path);
    };
    state.route='lab';state.run=null;state.runId=null;state.dirty=false;`);
  await evaluate("onAction('experiment')");
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(__experimentBody)')),
    {templateId:evaluate('templateId()'),suite:'required'},
    'The suite action explicitly requests the canonical required suite.');
  evaluate('api=__originalApi;delete globalThis.__originalApi;delete globalThis.__experimentBody;');
  let mutationRejected = false;
  try { await evaluate("api('/api/runs',{method:'POST',body:{}})"); }
  catch (error) { mutationRejected = /preview/i.test(error.message); }
  assert.ok(mutationRejected, 'The offline preview must reject write operations.');
  console.log(JSON.stringify({status:'passed',kind:'Node VM view-template contract smoke; not a browser test',...counts,capturedValidationAndDiff:true,mutationRejected},null,2));
}

main().catch(error => { console.error(error.stack || error); process.exitCode=1; });
