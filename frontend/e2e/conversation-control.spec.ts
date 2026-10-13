// UI-C01–07: actual owner HTTP/PostgreSQL commands; CONTROLLED is not live Telegram.
import { expect, test, type APIRequestContext, type APIResponse, type Page, type Route } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { requireSafeResult, safeDiagnostic } from './safe-diagnostic';
import { ControlBody, ControlOperation, ControlReceipt, ControlState, parseControlReceipt, parseControlState } from '../src/conversation-control-api';

const envPath=process.env.ASM_BROWSER_ENV_FILE,fixturePath=process.env.ASM_BROWSER_FIXTURE_FILE,inventoryPath=process.env.ASM_BROWSER_MESSAGING_FILE,passwordPath=process.env.ASM_BROWSER_PASSWORD_FILE,counterDir=process.env.ASM_BROWSER_COUNTER_DIR;
if(!envPath||!fixturePath||!inventoryPath||!passwordPath||!counterDir)throw new Error('E2E_SAFE_FAILURE:CONTROL_PRIVATE_FILES_REQUIRED');
function privateJson(path:string){try{return JSON.parse(readFileSync(path,'utf8'));}catch{throw new Error('E2E_SAFE_FAILURE:CONTROL_FIXTURE_OUTPUT');}}
const fixtures:Record<string,{workspace_id:string;login:string}>=privateJson(fixturePath).messaging_fixtures;
const inventory:Record<string,{conversation_id:string;client_id:string;alternate_conversation_id:string;alternate_client_id:string}>=privateJson(inventoryPath);
const password=readFileSync(passwordPath,'utf8'),origin='http://127.0.0.1:8080';
const context=(preset:string,alternate=false)=>({workspace:fixtures[preset].workspace_id,conversation:alternate?inventory[preset].alternate_conversation_id:inventory[preset].conversation_id,client:alternate?inventory[preset].alternate_client_id:inventory[preset].client_id});
const path=(preset:string,route='control',alternate=false)=>{const c=context(preset,alternate);return `/api/v1/workspaces/${c.workspace}/conversations/${c.conversation}/${route}`;};
const region=(page:Page)=>page.getByRole('region',{name:'Управление диалогом',exact:true});
const body=(s:ControlState):ControlBody=>({expected_client_id:s.client_id,expected_control_generation:s.control_generation,expected_context_version:s.context_version});
const http=async(operation:()=>Promise<APIResponse>)=>requireSafeResult(await safeDiagnostic('MESSAGING_HTTP_FAILED',operation));
const json=async(response:APIResponse)=>requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json()));
const proceed=async(route:Route)=>requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_CONTINUE_FAILED',()=>route.continue()));
async function csrf(request:APIRequestContext){const r=await http(()=>request.get('/api/v1/auth/session'));expect(r.status()).toBe(200);return (await json(r)).csrf_token as string;}
async function state(request:APIRequestContext,preset:string,alternate=false){const r=await http(()=>request.get(path(preset,'control',alternate)));expect(r.status()).toBe(200);return parseControlState(await json(r),context(preset,alternate));}
async function command(request:APIRequestContext,preset:string,operation:ControlOperation,value:ControlBody,key:string=randomUUID(),token?:string,alternate=false){return http(()=>request.post(path(preset,operation==='RESUME'?'resume':'takeover',alternate),{headers:{Origin:origin,'X-CSRF-Token':token!,'Idempotency-Key':key},data:value}));}
async function helper(preset:string,action='control-stats',runtime=false):Promise<Record<string,number>>{
  const args=['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`];
  if(runtime)args.push('-v',`${counterDir}:/run/m2-browser-counters:rw`);
  args.push(runtime?'browser-runtime':'browser-provision','python',runtime?'scripts/m2_4_browser_worker.py':'scripts/m2_4_browser_fixture.py','--preset',preset,'--action',action);
  const r=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:65536})));
  try{return JSON.parse(r.stdout);}catch{throw new Error('E2E_SAFE_FAILURE:CONTROL_FIXTURE_OUTPUT');}
}
function counts(before:Record<string,number>,after:Record<string,number>,controls:number,manual=0){
  for(const key of ['control_receipts','control_audit_events'])expect(after[key]-before[key]).toBe(controls);
  for(const key of ['messages','receipts','audit_events','outbox_events','jobs'])expect(after[key]-before[key]).toBe(manual);
}
async function choose(page:Page,preset:string,alternate=false){
  if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==fixtures[preset].workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures[preset].workspace_id);
  await page.getByTestId(`conversation-${context(preset,alternate).conversation}`).click();
  await expect(page.getByTestId(`conversation-${context(preset,alternate).conversation}`)).toHaveAttribute('aria-pressed','true');
  await expect(region(page).getByText(/^(Управление у мастера|Автоматика разрешена)$/)).toBeVisible();
}
async function login(page:Page,preset:string){await page.getByLabel('Логин').fill(fixtures[preset].login);await page.getByLabel('Пароль').fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await choose(page,preset);}
async function signIn(page:Page,preset:string){await page.goto('/');await login(page,preset);}
async function clickControl(page:Page,preset:string,operation:ControlOperation,keyboard=false){
  const route=operation==='RESUME'?'resume':'takeover';
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path(preset,route));
  const button=region(page).getByRole('button',{name:operation==='RESUME'?'Разрешить автоматику':'Забрать управление',exact:true});
  if(keyboard){await region(page).getByRole('button',{name:'Забрать управление'}).focus();await page.keyboard.press('Tab');await expect(button).toBeFocused();await page.keyboard.press('Enter');}else await button.click();
  const r=await pending;expect(r.status()).toBe(200);
  const original=requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>JSON.parse(r.request().postData()!))) as ControlBody;
  const receipt=parseControlReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())),context(preset),operation,original);
  await expect(region(page).getByRole('button',{name:'Забрать управление',exact:true})).toBeEnabled();return receipt;
}

test('@narrow CONTROL HUMAN -> keyboard Resume -> AI -> Takeover -> HUMAN; manual stays HUMAN',async({page})=>{
  const preset='ctrl_happy';await signIn(page,preset);const before=await helper(preset),initial=await state(page.request,preset);
  let posts=0;page.on('request',r=>{if(r.method()==='POST'&&/\/(resume|takeover)$/.test(new URL(r.url()).pathname))posts++;});
  await region(page).getByRole('button',{name:'Обновить режим'}).click();await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();expect(posts).toBe(0);
  await clickControl(page,preset,'RESUME',true);await expect(region(page).getByText('Автоматика разрешена',{exact:true})).toBeVisible();
  await clickControl(page,preset,'TAKEOVER');await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();
  const value=await state(page.request,preset);expect(BigInt(value.control_generation)-BigInt(initial.control_generation)).toBe(2n);
  await page.getByLabel('Ручной текстовый ответ').fill(`  Control manual e\u0301 🎨 ${randomUUID()}\n`);
  await page.getByRole('button',{name:'Проверить и отправить',exact:true}).click();await expect(page.getByRole('button',{name:'Проверить и отправить',exact:true})).toBeEnabled();
  await expect(region(page).getByText('Управление у мастера',{exact:true})).toBeVisible();const final=await state(page.request,preset);expect(final.control_mode).toBe('HUMAN');expect(BigInt(final.control_generation)-BigInt(initial.control_generation)).toBe(3n);expect(BigInt(final.context_version)-BigInt(initial.context_version)).toBe(1n);
  counts(before,await helper(preset),2,1);await helper(preset,'success',true);expect(posts).toBe(2);
  await page.reload();await choose(page,preset);expect(posts).toBe(2);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
});

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

test('actual UNKNOWN survives Takeover and replacement worker without resend',async({page})=>{
  const preset='ctrl_unknown';await signIn(page,preset);await page.getByLabel('Ручной текстовый ответ').fill('CONTROL unknown delivery');await page.getByRole('button',{name:'Проверить и отправить',exact:true}).click();await expect(page.getByRole('button',{name:'Проверить и отправить',exact:true})).toBeEnabled();
  const ran=await helper(preset,'unknown',true);expect(ran.calls).toBe(1);expect(ran.effects).toBe(1);await region(page).getByRole('button',{name:'Обновить режим'}).click();await expect(region(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();
  await clickControl(page,preset,'TAKEOVER');await expect(region(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();expect(await region(page).getByRole('button',{name:/resend|повтор.*отправ/i}).count()).toBe(0);
  const restarted=await helper(preset,'recover',true);expect(restarted.calls).toBe(1);expect(restarted.effects).toBe(1);expect(restarted.worked).toBe(0);await page.reload();await choose(page,preset);await expect(region(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();
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
