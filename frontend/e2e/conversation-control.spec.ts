// UI-C01–07: actual owner HTTP/PostgreSQL commands; CONTROLLED is not live Telegram.
// Worker journeys extend messaging.spec so its seeded PENDING image is observed
// before any shared worker drain. Native cases also use owner reconcile and the
// finite TEST policy capability; they never drain the shared worker.
import { expect, test, type APIRequestContext, type APIResponse, type Page, type Response, type Route } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { requireSafeResult, safeDiagnostic } from './safe-diagnostic';
import { ControlBody, ControlOperation, ControlReceipt, ControlState, parseControlReceipt, parseControlState } from '../src/conversation-control-api';
import { ReconcileBody, ReconcileReceipt, parseHumanContext, parseReconcileReceipt, reconcileBody, serializeReconcile } from '../src/human-context-api';

const envPath=process.env.ASM_BROWSER_ENV_FILE,fixturePath=process.env.ASM_BROWSER_FIXTURE_FILE,inventoryPath=process.env.ASM_BROWSER_MESSAGING_FILE,passwordPath=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!envPath||!fixturePath||!inventoryPath||!passwordPath)throw new Error('E2E_SAFE_FAILURE:CONTROL_PRIVATE_FILES_REQUIRED');
function privateJson(path:string){try{return JSON.parse(readFileSync(path,'utf8'));}catch{throw new Error('E2E_SAFE_FAILURE:CONTROL_FIXTURE_OUTPUT');}}
const fixtures:Record<string,{workspace_id:string;login:string}>=privateJson(fixturePath).messaging_fixtures;
const inventory:Record<string,{conversation_id:string;client_id:string;alternate_conversation_id:string;alternate_client_id:string}>=privateJson(inventoryPath);
const password=readFileSync(passwordPath,'utf8'),origin='http://127.0.0.1:8080';
const context=(preset:string,alternate=false)=>({workspace:fixtures[preset].workspace_id,conversation:alternate?inventory[preset].alternate_conversation_id:inventory[preset].conversation_id,client:alternate?inventory[preset].alternate_client_id:inventory[preset].client_id});
const path=(preset:string,route='control',alternate=false)=>{const c=context(preset,alternate);return `/api/v1/workspaces/${c.workspace}/conversations/${c.conversation}/${route}`;};
const region=(page:Page)=>page.getByRole('region',{name:'Управление диалогом',exact:true});
const body=(s:ControlState):ControlBody=>({expected_client_id:s.client_id,expected_control_generation:s.control_generation,expected_context_version:s.context_version});
const http=async(operation:()=>Promise<APIResponse>)=>requireSafeResult(await safeDiagnostic('MESSAGING_HTTP_FAILED',operation));
const json=async(response:APIResponse|Response)=>requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json()));
const proceed=async(route:Route)=>requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_CONTINUE_FAILED',()=>route.continue()));
async function csrf(request:APIRequestContext){const r=await http(()=>request.get('/api/v1/auth/session'));expect(r.status()).toBe(200);return (await json(r)).csrf_token as string;}
async function state(request:APIRequestContext,preset:string,alternate=false){const r=await http(()=>request.get(path(preset,'control',alternate)));expect(r.status()).toBe(200);return parseControlState(await json(r),context(preset,alternate));}
async function command(request:APIRequestContext,preset:string,operation:ControlOperation,value:ControlBody,key:string=randomUUID(),token?:string,alternate=false){return http(()=>request.post(path(preset,operation==='RESUME'?'resume':'takeover',alternate),{headers:{Origin:origin,'X-CSRF-Token':token!,'Idempotency-Key':key},data:value}));}
async function helper(preset:string,action='control-stats'):Promise<Record<string,number>>{
  const args=['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`];
  args.push('browser-provision','python','scripts/m2_4_browser_fixture.py','--preset',preset,'--action',action);
  if(action==='native-enable'||action==='native-pause'){
    // Actual Git identity from the later C0 clean-source gate, not a fabricated
    // accepted profile. Operator deployment/drain acceptance remains separate.
    const root=resolve(process.cwd(),'..');
    const clean=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('git',['status','--porcelain'],{cwd:root,timeout:10000,maxBuffer:65536})));
    if(clean.stdout!=='')throw new Error('E2E_SAFE_FAILURE:NATIVE_DIRTY_SOURCE');
    const tree=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('git',['rev-parse','HEAD^{tree}'],{cwd:root,timeout:10000,maxBuffer:1024})));
    const value=tree.stdout.trim();if(!/^[0-9a-f]{40}$/.test(value))throw new Error('E2E_SAFE_FAILURE:NATIVE_SOURCE_TREE');args.push('--source-tree',value);
  }
  const r=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:65536})));
  try{return JSON.parse(r.stdout);}catch{throw new Error('E2E_SAFE_FAILURE:CONTROL_FIXTURE_OUTPUT');}
}
function counts(before:Record<string,number>,after:Record<string,number>,controls:number){
  for(const key of ['control_receipts','control_audit_events'])expect(after[key]-before[key]).toBe(controls);
  for(const key of ['messages','receipts','audit_events','outbox_events','jobs'])expect(after[key]-before[key]).toBe(0);
}
async function choose(page:Page,preset:string,alternate=false){
  if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==fixtures[preset].workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures[preset].workspace_id);
  await page.getByTestId(`conversation-${context(preset,alternate).conversation}`).click();
  await expect(page.getByTestId(`conversation-${context(preset,alternate).conversation}`)).toHaveAttribute('aria-pressed','true');
  await expect(region(page).getByText(/^(Управление у мастера|Автоматика разрешена)$/)).toBeVisible();
}
async function login(page:Page,preset:string){await page.getByLabel('Логин').fill(fixtures[preset].login);await page.getByLabel('Пароль').fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await choose(page,preset);}
async function signIn(page:Page,preset:string){await page.goto('/');await login(page,preset);}
async function clickControl(page:Page,preset:string,operation:ControlOperation){
  const route=operation==='RESUME'?'resume':'takeover';
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,route));
  const button=region(page).getByRole('button',{name:operation==='RESUME'?'Разрешить автоматику':'Забрать управление',exact:true});
  await button.click();
  const r=await pending;expect(r.status()).toBe(200);
  const original=requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>JSON.parse(r.request().postData()!))) as ControlBody;
  const receipt=parseControlReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())),context(preset),operation,original);
  await expect(region(page).getByRole('button',{name:'Забрать управление',exact:true})).toBeEnabled();return receipt;
}

test('two actual tabs reject stale intent; delayed prior-conversation GET cannot replace current state',async({page,context:browser})=>{
  const preset='ctrl_stale';await signIn(page,preset);const other=await browser.newPage();await other.goto('/');await choose(other,preset);
  const initial=await state(page.request,preset),before=await helper(preset);await clickControl(page,preset,'RESUME');
  let posts=0;other.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===path(preset,'takeover'))posts++;});
  const stale=other.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'takeover'));
  await region(other).getByRole('button',{name:'Забрать управление'}).click();expect((await stale).status()).toBe(409);
  await expect(region(other).getByText(/Состояние изменилось/)).toBeVisible();await expect(region(other).getByText('Автоматика разрешена',{exact:true})).toBeVisible();expect(posts).toBe(1);counts(before,await helper(preset),1);
  await clickControl(other,preset,'TAKEOVER');expect(posts).toBe(2);expect(BigInt((await state(page.request,preset)).control_generation)-BigInt(initial.control_generation)).toBe(2n);
  const alternative=await command(page.request,preset,'RESUME',body(await state(page.request,preset,true)),randomUUID(),await csrf(page.request),true);expect(alternative.status()).toBe(200);
  let release!:()=>void,started!:()=>void;const gate=new Promise<void>(r=>{release=r;}),seen=new Promise<void>(r=>{started=r;});
  await page.route(`**${path(preset)}`,async route=>{const real=requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch()));started();await gate;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_RELEASE_FAILED',()=>route.fulfill({response:real})));});
  try{await region(page).getByRole('button',{name:'Обновить режим'}).click();await seen;await choose(page,preset,true);release();await page.unrouteAll({behavior:'wait'});await expect(region(page).getByText('Автоматика разрешена',{exact:true})).toBeVisible();expect((await state(page.request,preset,true)).control_generation).toBe('2');}
  finally{release();await page.unrouteAll({behavior:'wait'});await other.close();}
});

test('committed control response loss -> login/CSRF recovery -> same key/body REPLAY and one receipt/Audit',async({page})=>{
  const preset='ctrl_recovery';await signIn(page,preset);const before=await helper(preset);let attempts=0,originalBody:string|null=null,key:string|undefined,first:ControlReceipt|undefined,identical=true;
  await page.route(`**${path(preset,'resume')}`,async route=>{
    attempts++;const request=route.request();
    if(attempts>1){identical=identical&&request.postData()===originalBody&&request.headers()['idempotency-key']===key;await proceed(route);return;}
    originalBody=request.postData();key=request.headers()['idempotency-key'];const real=requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch()));expect(real.status()).toBe(200);
    first=parseControlReceipt(await json(real),context(preset),'RESUME',JSON.parse(originalBody!));requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));
  });
  try{
    await region(page).getByRole('button',{name:'Разрешить автоматику'}).click();await expect(region(page).getByText(/Результат изменения режима неизвестен/)).toBeVisible();expect(attempts).toBe(1);
    const committed=await helper(preset);counts(before,committed,1);
    const newer=await command(page.request,preset,'TAKEOVER',body(await state(page.request,preset)),randomUUID(),await csrf(page.request));expect(newer.status()).toBe(200);
    const afterNewer=await helper(preset);counts(committed,afterNewer,1);
    await page.context().clearCookies();await region(page).getByRole('button',{name:'Проверить сессию для операции'}).click();await login(page,preset);
    const renderedCsrf=await csrf(page.request);const rotate=await http(()=>page.request.post('/api/v1/auth/rotate',{headers:{Origin:origin,'X-CSRF-Token':renderedCsrf},data:{}}));expect(rotate.status()).toBe(200);
    const rejected=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'resume'));
    await region(page).getByRole('button',{name:'Повторить исходную операцию'}).click();expect((await rejected).status()).toBe(403);
    await expect(region(page).getByRole('button',{name:'Повторить исходную операцию'})).toBeEnabled();
    const replayed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'resume'));
    await region(page).getByRole('button',{name:'Повторить исходную операцию'}).click();const response=await replayed;expect(response.status()).toBe(200);
    const replay=parseControlReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json())),context(preset),'RESUME',JSON.parse(originalBody!));expect(replay.outcome).toBe('REPLAY');expect(JSON.stringify(replay.result)===JSON.stringify(first?.result)).toBe(true);
    await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();expect(attempts).toBe(3);expect(identical).toBe(true);counts(afterNewer,await helper(preset),0);
  }finally{await page.unrouteAll({behavior:'wait'});originalBody=null;key=undefined;first=undefined;}
});

test('valid200 plus failed GET is read-only recovery; old Resume replay never overwrites newer HUMAN',async({page})=>{
  const preset='ctrl_read';await signIn(page,preset);const initial=await state(page.request,preset),token=await csrf(page.request),before=await helper(preset);let posts=0,failed=false;
  page.on('request',r=>{if(r.method()==='POST'&&/\/(resume|takeover)$/.test(new URL(r.url()).pathname))posts++;});
  await page.route(`**${path(preset)}`,async route=>{if(!failed){failed=true;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));}else await proceed(route);});
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'resume'));
  await region(page).getByRole('button',{name:'Разрешить автоматику'}).click();const accepted=await response;expect(accepted.status()).toBe(200);const key=accepted.request().headers()['idempotency-key'];
  await expect(region(page).getByText('Операция подтверждена. Повторяется только чтение режима.')).toBeVisible();expect(await region(page).getByRole('button',{name:'Повторить исходную операцию'}).count()).toBe(0);
  const newer=await command(page.request,preset,'TAKEOVER',body(await state(page.request,preset)),randomUUID(),token);expect(newer.status()).toBe(200);
  // Receipt replay does not write; only the current GET may set the shown mode.
  const replay=await command(page.request,preset,'RESUME',body(initial),key,token);expect(replay.status()).toBe(200);expect((await json(replay)).outcome).toBe('REPLAY');
  await region(page).getByRole('button',{name:'Повторить чтение режима'}).click();await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();expect(posts).toBe(1);counts(before,await helper(preset),2);
  await page.unrouteAll({behavior:'wait'});
});

test('OWNER revoke denies CONTROL and clears shared protected views; Workspace remains isolated',async({page})=>{
  const preset='ctrl_revoked';await signIn(page,preset);const own=await state(page.request,preset),token=await csrf(page.request),before=await helper(preset);
  const foreign=await http(()=>page.request.get(path('foreign')));expect(foreign.status()).toBe(403);
  expect((await command(page.request,'foreign','TAKEOVER',body(own),randomUUID(),token)).status()).toBe(403);
  await helper(preset,'downgrade');await region(page).getByRole('button',{name:'Обновить режим'}).click();await expect(page.getByRole('region',{name:'Переписка',exact:true})).toHaveCount(0);await expect(region(page)).toHaveCount(0);await expect(page.getByRole('region',{name:'Audit',exact:true})).toHaveCount(0);
  expect((await command(page.request,preset,'TAKEOVER',body(own),randomUUID(),token)).status()).toBe(403);counts(before,await helper(preset),0);
  await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.isolation_peer.workspace_id);await choose(page,'isolation_peer');await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();
});

for(const [preset,action] of [['ctrl_inactive','disable'],['ctrl_restricted','restrict']] as const)test(`Takeover remains available in actual ${preset}, Resume is server-denied`,async({page})=>{
  await signIn(page,preset);await helper(preset,action);const before=await helper(preset);await clickControl(page,preset,'TAKEOVER');
  const denied=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'resume'));
  await region(page).getByRole('button',{name:'Разрешить автоматику'}).click();expect((await denied).status()).toBe(409);await expect(region(page).getByText(/Сервер не разрешил автоматику/)).toBeVisible();await expect(region(page).getByRole('button',{name:'Забрать управление'})).toBeEnabled();counts(before,await helper(preset),1);
});

// NC-UI01–05, source-only future carrier. Every accepted reconciliation below is
// an actual owner HTTP commit; route handlers delay/drop real replies only.
const nativeRegion=(page:Page)=>page.getByRole('region',{name:'Сверка контекста',exact:true});
const savedRegion=(page:Page)=>page.getByRole('region',{name:'Сохранённый контекст',exact:true});
const nativePreset=(project:string)=>project==='chromium-narrow'?'native_narrow':'native_happy';
async function nativeState(request:APIRequestContext,preset:string){const r=await http(()=>request.get(path(preset,'human-context')));expect(r.status()).toBe(200);return parseHumanContext(await json(r),context(preset));}
async function nativePost(request:APIRequestContext,preset:string,value:ReconcileBody,key=randomUUID(),token?:string){return http(()=>request.post(path(preset,'human-context/reconcile'),{headers:{Origin:origin,'Content-Type':'application/json','X-CSRF-Token':token??'','Idempotency-Key':key},data:serializeReconcile(value)}));}
async function prepareContext(page:Page,text:string){
  const panel=nativeRegion(page);await expect(panel.getByRole('button',{name:'Обновить контекст',exact:true})).toBeEnabled();await expect(panel.getByRole('button',{name:'Обновить наблюдения',exact:true})).toBeEnabled();
  await panel.getByLabel('Новый полный контекст',{exact:true}).fill(text);await panel.getByLabel('Подтверждаю полную замену или отзыв прежнего контекста',{exact:true}).check();await panel.getByLabel('Я сверил доступный контекст и существенные договорённости',{exact:true}).check();await expect(panel.getByRole('button',{name:'Сохранить сверенный контекст',exact:true})).toBeEnabled();
}
async function saveContext(page:Page,preset:string,text:string){
  await prepareContext(page,text);const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));
  await nativeRegion(page).getByRole('button',{name:'Сохранить сверенный контекст',exact:true}).click();const r=await pending;expect(r.status()).toBe(200);const value=requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>JSON.parse(r.request().postData()!))) as ReconcileBody;
  const receipt=parseReconcileReceipt(await json(r),context(preset),value);await expect(savedRegion(page).getByText(text,{exact:true})).toBeVisible();await expect(nativeRegion(page).getByRole('button',{name:'Сохранить сверенный контекст',exact:true})).toBeDisabled();return receipt;
}
function nativeCounts(before:Record<string,number>,after:Record<string,number>,revisions:number,controls=0,policies=0){
  counts(before,after,controls);for(const key of ['reconciliations','reconciliation_audit'])expect(after[key]-before[key]).toBe(revisions);for(const key of ['policy_receipts','policy_audit'])expect(after[key]-before[key]).toBe(policies);
}

test('NC-UI01 @narrow: bootstrap Takeover -> full reconcile -> separate explicit Resume, no send',async({page},info)=>{
  const preset=nativePreset(info.project.name);await signIn(page,preset);const before=await helper(preset,'native-stats');expect((await nativeState(page.request,preset)).policy).toBe('OFF_UNUSED');
  // Legacy AI then ENABLE requires the actual bootstrap flow. No fixture R/G/V.
  await clickControl(page,preset,'RESUME');await helper(preset,'native-enable');await nativeRegion(page).getByRole('button',{name:'Обновить контекст',exact:true}).click();await expect(region(page).getByRole('button',{name:'Разрешить автоматику'})).toBeDisabled();
  await clickControl(page,preset,'TAKEOVER');let contextPosts=0;page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'))contextPosts++;});const input=nativeRegion(page).getByLabel('Новый полный контекст',{exact:true});await input.fill('line one');await input.press('End');await input.press('Enter');await expect(input).toHaveValue('line one\n');expect(contextPosts).toBe(0);const text='  Полный контекст владельца\ne\u0301 🎨  ';const receipt=await saveContext(page,preset,text);const current=await nativeState(page.request,preset);expect(current.current_revision?.revision_id).toBe(receipt.result.revision_id);expect(current.control_mode).toBe('HUMAN');expect(contextPosts).toBe(1);
  await expect(region(page).getByRole('button',{name:'Разрешить автоматику'})).toBeEnabled();nativeCounts(before,await helper(preset,'native-stats'),1,2,1);await clickControl(page,preset,'RESUME');expect((await nativeState(page.request,preset)).control_mode).toBe('AI');nativeCounts(before,await helper(preset,'native-stats'),1,3,1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('NC-UI02 @narrow: two tabs stale full CAS requires fresh explicit replacement, never merges old facts',async({page,context:browser},info)=>{
  const preset=nativePreset(info.project.name);await signIn(page,preset);await clickControl(page,preset,'TAKEOVER');const other=await browser.newPage();await other.goto('/');await choose(other,preset);const before=await helper(preset,'native-stats');
  try{
    await prepareContext(other,'Stale tab intention');await saveContext(page,preset,'Replacement R2');const stale=other.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));await nativeRegion(other).getByRole('button',{name:'Сохранить сверенный контекст',exact:true}).click();expect((await stale).status()).toBe(409);
    await expect(nativeRegion(other).getByText('Повтор остановлен. Завершите ожидание и сделайте новый явный выбор.',{exact:true})).toBeVisible();nativeCounts(before,await helper(preset,'native-stats'),1);await nativeRegion(other).getByRole('button',{name:'Завершить ожидание контекста без повтора'}).click();
    await expect(savedRegion(other).getByText('Replacement R2',{exact:true})).toBeVisible();await expect(nativeRegion(other).getByRole('button',{name:'Сохранить сверенный контекст',exact:true})).toBeDisabled();await saveContext(other,preset,'New explicit R3');expect((await nativeState(other.request,preset)).current_revision?.text).toBe('New explicit R3');nativeCounts(before,await helper(preset,'native-stats'),2);
  }finally{await other.close();}
});

test('NC-UI03 @narrow: committed response loss, newer R, login/CSRF and frozen old replay display current R only',async({page},info)=>{
  const preset=nativePreset(info.project.name);await signIn(page,preset);const before=await helper(preset,'native-stats');let attempts=0,original:string|null=null,key:string|undefined,first:ReconcileReceipt|undefined,identical=true;
  await page.route(`**${path(preset,'human-context/reconcile')}`,async route=>{
    attempts++;const r=route.request();if(attempts>1){identical=identical&&r.postData()===original&&r.headers()['idempotency-key']===key;await proceed(route);return;}
    original=r.postData();key=r.headers()['idempotency-key'];const real=requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch()));expect(real.status()).toBe(200);first=parseReconcileReceipt(await json(real),context(preset),JSON.parse(original!));requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));
  });
  try{
    await prepareContext(page,'Lost accepted R4');await nativeRegion(page).getByRole('button',{name:'Сохранить сверенный контекст',exact:true}).click();await expect(nativeRegion(page).getByText(/Результат сохранения неизвестен/)).toBeVisible();nativeCounts(before,await helper(preset,'native-stats'),1);
    const newerBody=reconcileBody(await nativeState(page.request,preset),'OWNER_TEXT','Current newer R5','NONE');const newer=await nativePost(page.request,preset,newerBody,randomUUID(),await csrf(page.request));expect(newer.status()).toBe(200);parseReconcileReceipt(await json(newer),context(preset),newerBody);
    await page.context().clearCookies();await nativeRegion(page).getByRole('button',{name:'Проверить сессию для контекста'}).click();await login(page,preset);const token=await csrf(page.request);expect((await http(()=>page.request.post('/api/v1/auth/rotate',{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}))).status()).toBe(200);
    const rejected=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));await nativeRegion(page).getByRole('button',{name:'Повторить исходное сохранение контекста'}).click();expect((await rejected).status()).toBe(403);await expect(nativeRegion(page).getByRole('button',{name:'Повторить исходное сохранение контекста'})).toBeEnabled();
    const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));await nativeRegion(page).getByRole('button',{name:'Повторить исходное сохранение контекста'}).click();const r=await pending;expect(r.status()).toBe(200);const replay=parseReconcileReceipt(await json(r),context(preset),JSON.parse(original!));expect(replay.outcome).toBe('REPLAY');expect(JSON.stringify(replay.result)===JSON.stringify(first?.result)).toBe(true);
    await expect(savedRegion(page).getByText('Current newer R5',{exact:true})).toBeVisible();expect(attempts).toBe(3);expect(identical).toBe(true);nativeCounts(before,await helper(preset,'native-stats'),2);
  }finally{await page.unrouteAll({behavior:'wait'});original=null;key=undefined;first=undefined;}
});

test('NC-UI04 @narrow: valid200 plus lost current GET permits reads only; reload sends nothing',async({page},info)=>{
  const preset=nativePreset(info.project.name);await signIn(page,preset);await prepareContext(page,'Accepted R6');const before=await helper(preset,'native-stats');let posts=0,failed=false;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'))posts++;});
  await page.route(`**${path(preset,'human-context')}`,async route=>{if(!failed){failed=true;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));}else await proceed(route);});
  try{
    const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));await nativeRegion(page).getByRole('button',{name:'Сохранить сверенный контекст',exact:true}).click();expect((await pending).status()).toBe(200);await expect(nativeRegion(page).getByText('Сохранение подтверждено. Повторяется только чтение.',{exact:true})).toBeVisible();await expect(nativeRegion(page).getByRole('button',{name:'Повторить исходное сохранение контекста'})).toHaveCount(0);
    const newerBody=reconcileBody(await nativeState(page.request,preset),'OWNER_TEXT','Current R7 after accepted R6','NONE');const newer=await nativePost(page.request,preset,newerBody,randomUUID(),await csrf(page.request));expect(newer.status()).toBe(200);parseReconcileReceipt(await json(newer),context(preset),newerBody);
    await nativeRegion(page).getByRole('button',{name:'Повторить чтение контекста'}).click();await expect(savedRegion(page).getByText('Current R7 after accepted R6',{exact:true})).toBeVisible();expect(posts).toBe(1);await page.reload();await choose(page,preset);await expect(savedRegion(page).getByText('Current R7 after accepted R6',{exact:true})).toBeVisible();expect(posts).toBe(1);nativeCounts(before,await helper(preset,'native-stats'),2);
  }finally{await page.unrouteAll({behavior:'wait'});}
});

test('NC-UI05 @narrow: PAUSED retains review/Takeover, unresolved holds Resume, isolation/revoke hide protected context',async({page},info)=>{
  const preset=nativePreset(info.project.name);await signIn(page,preset);await helper(preset,'native-pause');await nativeRegion(page).getByRole('button',{name:'Обновить контекст',exact:true}).click();await expect(nativeRegion(page).getByText('Автоматика приостановлена оператором',{exact:true})).toBeVisible();const before=await helper(preset,'native-stats');
  const panel=nativeRegion(page);await panel.getByLabel('Результат сверки',{exact:true}).selectOption('UNRESOLVED');await panel.getByLabel('Новый полный контекст',{exact:true}).fill('');await panel.getByLabel('Подтверждаю полную замену или отзыв прежнего контекста',{exact:true}).check();await panel.getByLabel('Я сверил доступный контекст и существенные договорённости',{exact:true}).check();const saved=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,'human-context/reconcile'));await panel.getByRole('button',{name:'Сохранить сверенный контекст',exact:true}).click();expect((await saved).status()).toBe(200);await expect(savedRegion(page).getByText('Вопросы остаются неразрешёнными',{exact:true})).toBeVisible();
  await expect(region(page).getByRole('button',{name:'Разрешить автоматику'})).toBeDisabled();await expect(region(page).getByRole('button',{name:'Забрать управление'})).toBeEnabled();const token=await csrf(page.request),current=await nativeState(page.request,preset);expect(current.coverage_status).toBe('UNRESOLVED');const denied=await command(page.request,preset,'RESUME',body(await state(page.request,preset)),randomUUID(),token);expect(denied.status()).toBe(409);expect((await json(denied)).error.code).toBe('CONTEXT_POLICY_PAUSED');
  expect((await http(()=>page.request.get(path('foreign','human-context')))).status()).toBe(403);expect((await nativePost(page.request,'foreign',reconcileBody(current,'UNRESOLVED',null,'NONE'),randomUUID(),token)).status()).toBe(403);nativeCounts(before,await helper(preset,'native-stats'),1);
  await helper(preset,'downgrade');await panel.getByRole('button',{name:'Обновить контекст',exact:true}).click();await expect(nativeRegion(page)).toHaveCount(0);await expect(page.getByRole('region',{name:'Переписка',exact:true})).toHaveCount(0);await expect(page.getByRole('region',{name:'Audit',exact:true})).toHaveCount(0);expect((await http(()=>page.request.get(path(preset,'human-context')))).status()).toBe(403);nativeCounts(before,await helper(preset,'native-stats'),1);
});
