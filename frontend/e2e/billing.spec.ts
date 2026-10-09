import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { requireSafeResult, safeDiagnostic, type SafeResult } from './safe-diagnostic';
import { parseBilling, parseAuditPage, type AuditItem, type Billing } from '../src/billing-api';

const passwordPath = process.env.ASM_BROWSER_PASSWORD_FILE;
const fixturePath = process.env.ASM_BROWSER_FIXTURE_FILE;
const envPath = process.env.ASM_BROWSER_ENV_FILE;
if (!passwordPath || !fixturePath || !envPath) throw new Error('Private browser fixture files required');
const password = readFileSync(passwordPath,'utf8');
const fixtures: Record<string,{workspace_id:string;user_account_id:string}> = (() => { try { return JSON.parse(readFileSync(fixturePath,'utf8')).billing_fixtures; } catch { throw new Error('E2E_SAFE_FAILURE:FIXTURE_JSON'); } })();
const origin='http://127.0.0.1:8080';
const path=(preset:string,suffix:string)=>`/api/v1/workspaces/${fixtures[preset].workspace_id}/${suffix}`;
async function json(response: import('@playwright/test').APIResponse) { return requireSafeResult(await safeDiagnostic('BILLING_BODY_FAILED',()=>response.json())); }
async function http(operation:()=>Promise<import('@playwright/test').APIResponse>) { return requireSafeResult(await safeDiagnostic('BILLING_HTTP_FAILED',operation)); }
async function session(request:APIRequestContext) { const r=await http(()=>request.get('/api/v1/auth/session')); expect(r.status()).toBe(200); return await json(r) as {csrf_token:string}; }
async function read(request:APIRequestContext,preset:string):Promise<Billing> { const r=await http(()=>request.get(path(preset,'billing'))); expect(r.status()).toBe(200); return parseBilling(await json(r)); }
async function patch(request:APIRequestContext,preset:string,version:string,name:string,csrf:string,key=randomUUID()) {
  return http(()=>request.patch(path(preset,'billing-account'),{headers:{Origin:origin,'X-CSRF-Token':csrf,'Idempotency-Key':key},data:{expected_version:version,contact_display_name:name}}));
}
async function stats(preset:string,action='stats'):Promise<{version:string;receipts:number;contact_events:number}> {
  const result=requireSafeResult(await safeDiagnostic('BILLING_FIXTURE_FAILED',()=>promisify(execFile)('docker',['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-provision','python','scripts/m1_3_browser_fixture.py','--preset',preset,'--action',action],{cwd:resolve(process.cwd(),'..'),timeout:20_000,maxBuffer:64*1024})));
  try { return JSON.parse(result.stdout); } catch { throw new Error('E2E_SAFE_FAILURE:BILLING_FIXTURE_OUTPUT'); }
}
async function signIn(page:Page,preset:string) {
  await page.goto('/'); await page.getByLabel('Логин').fill(`browser.m13-${preset}`); await page.getByLabel('Пароль').fill(password); await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled();
}
async function save(page:Page,name:string) {
  await page.getByLabel('Имя контакта').fill(name); await page.getByRole('button',{name:'Сохранить контакт'}).click(); await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled();
}
async function audit(request:APIRequestContext,preset:string) {
  const r=await http(()=>request.get(path(preset,'audit-events?limit=10'))); expect(r.status()).toBe(200); return parseAuditPage(await json(r));
}
async function auditRendered(region:Locator,items:AuditItem[],cursor:string|null) {
  await expect(region.locator('ol > li')).toHaveCount(items.length);
  await expect(region.locator('ol > li time')).toHaveText(items.map(item=>item.occurred_at));
  await expect(region.getByText('Загружаем историю…')).toHaveCount(0);
  await expect(region.getByRole('button',{name:'Обновить историю',exact:true})).toBeEnabled();
  const more=region.getByRole('button',{name:'Загрузить ещё',exact:true});
  if(cursor===null){await expect(more).toHaveCount(0);await expect(region.getByText('Конец истории.')).toBeVisible();}
  else {await expect(more).toBeEnabled();await expect(region.getByText('Конец истории.')).toHaveCount(0);}
}

test('@narrow owner UPDATE/NOOP, zero, fresh GET/reload, real Audit pagination and keyboard',async({page})=>{
  await signIn(page,'happy'); await expect(page.getByText('Лимит: 0')).toBeVisible();
  const before=await read(page.request,'happy'); const name=`Contact ${randomUUID()}`;
  await page.getByLabel('Имя контакта').fill(name); await page.getByLabel('Имя контакта').press('Tab'); await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeFocused(); await page.keyboard.press('Enter');
  await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled();
  let actual=await read(page.request,'happy'); expect(actual.account.contact_display_name===name).toBe(true); expect(BigInt(actual.account.version)-BigInt(before.account.version)).toBe(1n);
  const afterUpdate=await stats('happy'); await save(page,`  ${name}  `); await expect(page.getByText('Изменений нет. Версия и Audit сохранены.')).toBeVisible();
  const afterNoop=await stats('happy'); expect(afterNoop.version).toBe(afterUpdate.version); expect(afterNoop.contact_events).toBe(afterUpdate.contact_events); expect(afterNoop.receipts-afterUpdate.receipts).toBe(1);
  const auth=await session(page.request);
  // Populate history with real authenticated commands, never fabricated Audit rows.
  for(let n=0;n<10;n++){const response=await patch(page.request,'happy',actual.account.version,`History ${randomUUID()}`,auth.csrf_token);expect(response.status()).toBe(200);actual=await read(page.request,'happy');}
  await page.reload(); await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled();
  expect((await page.getByTestId('current-contact').textContent())===actual.account.contact_display_name).toBe(true);
  const region=page.getByRole('region',{name:'Audit',exact:true}); expect((await region.textContent())?.includes(actual.account.contact_display_name)).toBe(false);
  const first=await audit(page.request,'happy'); expect(first.items.length).toBe(10); expect(first.next_cursor!==null).toBe(true);
  await test.step('Audit pages settle after headers, including removal of the last-page button',async()=>{
    await auditRendered(region,first.items,first.next_cursor);
    // C0-CI-AUDIT-01: headers/body arrival does not imply the consumer has
    // rendered the page. Hold only its JSON processing; keep the real response.
    let decoded=0, release=()=>{};
    let processing=Promise.resolve();
    await page.exposeFunction('pauseAuditPage',async()=>{decoded++;await processing;});
    await page.evaluate(auditPath=>{
      const json=Response.prototype.json;
      Response.prototype.json=async function(){
        const body:unknown=await json.call(this);
        const url=new URL(this.url);
        if(url.pathname===auditPath&&url.searchParams.has('cursor'))
          await (window as unknown as {pauseAuditPage:()=>Promise<void>}).pauseAuditPage();
        return body;
      };
    },path('happy','audit-events'));
    const items=[...first.items]; let cursor=first.next_cursor, pages=0;
    try {
      while(cursor!==null){
        processing=new Promise<void>(resolve=>{release=resolve;});
        const pagingResponse=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname===path('happy','audit-events'));
        await region.getByRole('button',{name:'Загрузить ещё',exact:true}).click();
        const loaded=await pagingResponse; expect(loaded.status()).toBe(200);
        const query=new URL(loaded.url()).searchParams;
        expect(query.getAll('limit')).toEqual(['10']); expect(query.getAll('cursor').length===1&&query.get('cursor')===cursor).toBe(true);
        const next=parseAuditPage(requireSafeResult(await safeDiagnostic('BILLING_BODY_FAILED',()=>loaded.json())));
        await expect.poll(()=>decoded).toBe(++pages);
        // This is the stale DOM that admitted the old count()/enabled loop.
        await expect(region.getByText('Загружаем историю…')).toBeVisible();
        await expect(region.getByRole('button',{name:'Загрузить ещё',exact:true})).toBeDisabled();
        await expect(region.locator('ol > li')).toHaveCount(items.length);
        release();
        items.push(...next.items); expect(new Set(items.map(item=>item.audit_event_id)).size).toBe(items.length);
        await auditRendered(region,items,next.next_cursor);
        cursor=next.next_cursor;
      }
    } finally {release();}
    await expect(region.getByText('Конец истории.')).toBeVisible();
    const refreshed=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname===path('happy','audit-events'));
    await region.getByRole('button',{name:'Обновить историю',exact:true}).click();
    const response=await refreshed; expect(response.status()).toBe(200);
    expect(new URL(response.url()).searchParams.toString()).toBe('limit=10');
    const current=parseAuditPage(requireSafeResult(await safeDiagnostic('BILLING_BODY_FAILED',()=>response.json())));
    expect(current).toEqual(first);
    await auditRendered(region,current.items,current.next_cursor);
    await expect(region.locator('ol > li')).toHaveCount(10);
  });
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  expect(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length,cookie:document.cookie}))).toEqual({local:0,session:0,cookie:''});
});

test('stale edit from another real session requires explicit new intention',async({page,playwright})=>{
  await signIn(page,'stale'); const before=await read(page.request,'stale'); await page.getByLabel('Имя контакта').fill('Browser stale draft');
  const other=await playwright.request.newContext({baseURL:origin});
  try {
    const bootstrap=await http(()=>other.post('/api/v1/auth/bootstrap',{headers:{Origin:origin,'X-CSRF-Bootstrap':'1'},data:{}})); expect(bootstrap.status()).toBe(200);
    const challenge=await json(bootstrap); const login=await http(()=>other.post('/api/v1/auth/login',{headers:{Origin:origin,'X-CSRF-Token':challenge.csrf_token},data:{login:'browser.m13-stale',password}})); expect(login.status()).toBe(200); const auth=await json(login);
    const changed=await patch(other,'stale',before.account.version,'Concurrent committed contact',auth.csrf_token); expect(changed.status()).toBe(200);
    const conflict=page.waitForResponse(r=>r.request().method()==='PATCH'); await page.getByRole('button',{name:'Сохранить контакт'}).click(); expect((await conflict).status()).toBe(409);
    await expect(page.getByText(/Конфликт версии/)).toBeVisible(); await expect(page.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled(); await expect(page.getByLabel('Имя контакта')).toHaveValue('Browser stale draft');
    const current=await read(page.request,'stale'); expect(current.account.contact_display_name==='Concurrent committed contact').toBe(true); expect(BigInt(current.account.version)-BigInt(before.account.version)).toBe(1n);
    await page.getByRole('button',{name:'Сохранить контакт'}).click(); await expect(page.getByText('Сохранение подтверждено. Текущее состояние получено.')).toBeVisible(); const final=await read(page.request,'stale'); expect(final.account.contact_display_name==='Browser stale draft').toBe(true); expect(BigInt(final.account.version)-BigInt(before.account.version)).toBe(2n);
  } finally { await other.dispose(); }
});

test('lost delivery after real commit recovers auth/CSRF and same body/key without duplicate',async({page})=>{
  await signIn(page,'recovery'); const before=await stats('recovery'); let attempts=0, firstBody:string|null=null, firstKey:string|undefined, identical=true;
  let complete!: (result:SafeResult<number>)=>void;
  const committed=new Promise<SafeResult<number>>(r=>{complete=r;});
  const pattern='**/api/v1/workspaces/*/billing-account';
  await page.route(pattern,async route=>{
    attempts++; const request=route.request();
    if(attempts>1){identical=identical&&request.postData()===firstBody&&request.headers()['idempotency-key']===firstKey; const continued=await safeDiagnostic('BILLING_ROUTE_CONTINUE_FAILED',()=>route.continue()); if(!continued.ok)complete(continued);return;}
    firstBody=request.postData();firstKey=request.headers()['idempotency-key'];
    const response=await safeDiagnostic('BILLING_ROUTE_FETCH_FAILED',()=>route.fetch({timeout:10_000}));
    const aborted=await safeDiagnostic('BILLING_ROUTE_ABORT_FAILED',()=>route.abort('failed'));
    complete(!response.ok?response:!aborted.ok?aborted:{ok:true,value:response.value.status()});
  });
  try {
    await page.getByLabel('Имя контакта').fill('Committed but response lost'); await page.getByRole('button',{name:'Сохранить контакт'}).click();
    const commitStatus=requireSafeResult(await Promise.race([committed,new Promise<SafeResult<number>>(r=>{const timer=setTimeout(()=>r({ok:false,code:'BILLING_CALLBACK_TIMEOUT'}),12_000);committed.finally(()=>clearTimeout(timer));})])); expect(commitStatus).toBe(200);
    await expect(page.getByText(/Результат сохранения неизвестен/)).toBeVisible(); expect(attempts).toBe(1); const committedState=await stats('recovery'); expect(BigInt(committedState.version)-BigInt(before.version)).toBe(1n);
    const recovered=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/auth/session');
    await page.getByRole('button',{name:'Проверить сессию для повтора'}).click(); expect((await recovered).status()).toBe(200);
    await expect(page.getByRole('button',{name:'Повторить исходное сохранение'})).toBeEnabled(); await page.getByRole('button',{name:'Повторить исходное сохранение'}).click();
    await expect(page.getByText('Сохранение подтверждено. Текущее состояние получено.')).toBeVisible(); expect(attempts).toBe(2); expect(identical).toBe(true);
    const after=await stats('recovery'); expect(after.version).toBe(committedState.version); expect(after.receipts-before.receipts).toBe(1); expect(after.contact_events-before.contact_events).toBe(1);
    const current=await read(page.request,'recovery'); expect(current.account.contact_display_name==='Committed but response lost').toBe(true);
  } finally { await page.unrouteAll({behavior:'wait'}); firstBody=null;firstKey=undefined; }
});

test('authenticated foreign Workspace denial and live owner downgrade hide billing/Audit',async({page})=>{
  await signIn(page,'isolation'); const auth=await session(page.request); const foreign=await stats('foreign');
  for(const suffix of ['billing','audit-events?limit=10']) {const r=await http(()=>page.request.get(path('foreign',suffix))); expect(r.status()).toBe(403); expect(JSON.stringify(await json(r))==='{"error":{"code":"ACCESS_DENIED"}}').toBe(true);}
  const denied=await patch(page.request,'foreign','1','Forbidden',auth.csrf_token); expect(denied.status()).toBe(403); expect(await stats('foreign')).toEqual(foreign);
  await stats('isolation','downgrade'); await page.getByRole('button',{name:'Обновить подписку'}).click(); await expect(page.getByText('Нет доступа к данным владельца')).toBeVisible();
  await expect(page.getByLabel('Имя контакта')).toHaveCount(0); await expect(page.getByRole('region',{name:'Audit',exact:true})).toHaveCount(0);
  for(const suffix of ['billing','audit-events?limit=10']) {const r=await http(()=>page.request.get(path('isolation',suffix))); expect(r.status()).toBe(403);}
  const write=await patch(page.request,'isolation','1','Forbidden',auth.csrf_token); expect(write.status()).toBe(403);
  const businesses=await http(()=>page.request.get(path('isolation','businesses'))); expect(businesses.status()).toBe(200);
  await page.reload(); await expect(page.getByText('ACTIVE SESSION')).toBeVisible(); await expect(page.getByRole('region',{name:'Панель владельца'})).toHaveCount(0);
});

for(const preset of ['inactive','restricted','mode_inactive']) test(`real ${preset} state preserves contact/auth/Business rights`,async({page})=>{
  await signIn(page,preset); const state=await read(page.request,preset);
  if(preset==='inactive'){expect(state.subscription===null&&state.availability==='INACTIVE'&&state.mode_active).toBe(true);await expect(page.getByText(/текущей подписки нет/)).toBeVisible();}
  else if(preset==='mode_inactive'){expect(state.subscription!==null&&!state.mode_active).toBe(true);await expect(page.getByText('NORMAL · не действует')).toBeVisible();}
  else {expect(state.mode==='SUSPENDED'&&state.mode_active).toBe(true);await expect(page.getByText('SUSPENDED · действует')).toBeVisible();}
  expect(state.decisions.every(d=>d.type==='DISABLED')).toBe(true); await save(page,`Administration ${preset}`); const current=await read(page.request,preset); expect(BigInt(current.account.version)-BigInt(state.account.version)).toBe(1n);
  const business=await http(()=>page.request.get(path(preset,'businesses')));expect(business.status()).toBe(200); await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.getByText(/Выход выполнен/)).toBeVisible();
});

test('browser credentialed CORS PATCH and disallowed-header preflight without mutation',async({page})=>{
  await signIn(page,'foreign'); const current=await read(page.request,'foreign'); const auth=await session(page.request); const before=await stats('foreign');
  const url=`http://127.0.0.1:8000${path('foreign','billing-account')}`;
  // Chromium preflights may have no frame and are filtered by Playwright's page
  // response events. Observe real network metadata via CDP, without interception.
  const network=await page.context().newCDPSession(page); const preflights:number[]=[]; const corsErrors:string[]=[];
  await network.send('Network.enable');
  network.on('Network.responseReceived',event=>{if(event.type==='Preflight'&&event.response.url===url)preflights.push(event.response.status);});
  network.on('Network.loadingFailed',event=>{if(event.corsErrorStatus)corsErrors.push(event.corsErrorStatus.corsError);});
  try {
    const positive=await page.evaluate(async({url,body,csrf,key})=>{try {const response=await fetch(url,{method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:JSON.stringify(body)});return response.status;}catch{return 0;}},{url,body:{expected_version:current.account.version,contact_display_name:'CORS committed'},csrf:auth.csrf_token,key:randomUUID()});
    expect(positive).toBe(200); await expect.poll(()=>preflights.includes(200)).toBe(true); const actual=await read(page.request,'foreign');expect(actual.account.contact_display_name==='CORS committed').toBe(true);
    const rejected=await page.evaluate(async({url,body,csrf,key})=>{try {await fetch(url,{method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key,'X-Disallowed':'1'},body:JSON.stringify(body)});return false;}catch{return true;}},{url,body:{expected_version:actual.account.version,contact_display_name:'Must not commit'},csrf:auth.csrf_token,key:randomUUID()});
    expect(rejected).toBe(true);await expect.poll(()=>preflights.includes(400)).toBe(true);await expect.poll(()=>corsErrors.some(code=>code.includes('Preflight'))).toBe(true);
    const after=await stats('foreign');expect(BigInt(after.version)-BigInt(before.version)).toBe(1n);expect(after.receipts-before.receipts).toBe(1);expect(after.contact_events-before.contact_events).toBe(1);
  } finally {await network.detach();}
});
