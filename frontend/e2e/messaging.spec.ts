// CONTROLLED boundary only: browser -> real owner API / PostgreSQL / private
// MinIO / accepted Worker. No happy-path JSON or canonical rows are fabricated.
import { expect, test, type APIRequestContext, type APIResponse, type Locator, type Page, type Route } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { requireSafeResult, safeDiagnostic, type SafeResult } from './safe-diagnostic';
import { parseMessage, parsePage, parseReceipt, type SendReceipt } from '../src/messaging-api';

const envPath=process.env.ASM_BROWSER_ENV_FILE, fixturePath=process.env.ASM_BROWSER_FIXTURE_FILE, inventoryPath=process.env.ASM_BROWSER_MESSAGING_FILE, passwordPath=process.env.ASM_BROWSER_PASSWORD_FILE, counterDir=process.env.ASM_BROWSER_COUNTER_DIR;
if(!envPath||!fixturePath||!inventoryPath||!passwordPath||!counterDir) throw new Error('E2E_SAFE_FAILURE:MESSAGING_PRIVATE_FILES_REQUIRED');
function privateJson(path:string) { try { return JSON.parse(readFileSync(path,'utf8')); } catch { throw new Error('E2E_SAFE_FAILURE:MESSAGING_FIXTURE_OUTPUT'); } }
const fixtures:Record<string,{workspace_id:string;user_account_id:string;login:string}>=privateJson(fixturePath).messaging_fixtures;
type Ref={conversation_id:string;message_id:string;file_id:string};
type Inventory={conversation_id:string;alternate_conversation_id:string;connection_ids:string[];conversation_ids:string[];message_ids:string[];images:{ready:Ref;failed?:Ref;pending?:Ref}};
const inventory:Record<string,Inventory>=privateJson(inventoryPath), password=readFileSync(passwordPath,'utf8');
const origin='http://127.0.0.1:8080';
const path=(preset:string,suffix:string)=>`/api/v1/workspaces/${fixtures[preset].workspace_id}/${suffix}`;
const messages=(preset:string,conversation=inventory[preset].conversation_id)=>path(preset,`conversations/${conversation}/messages`);
const grantPath=(preset:string,ref=inventory[preset].images.ready)=>`${messages(preset,ref.conversation_id)}/${ref.message_id}/files/${ref.file_id}/read-grant`;
const panel=(page:Page)=>page.getByRole('region',{name:'Переписка',exact:true});
const http=async(operation:()=>Promise<APIResponse>)=>requireSafeResult(await safeDiagnostic('MESSAGING_HTTP_FAILED',operation));
const json=async(response:APIResponse)=>requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json()));
const privateImageValue=async<T,>(operation:()=>Promise<T>)=>requireSafeResult(await safeDiagnostic('MESSAGING_PRIVATE_IMAGE_FAILED',operation));
async function loadedPrivateImage(image:Locator){
  // Locator assertions preview src on failure. Poll only booleans/numbers, and
  // replace probe exceptions before they can expose the signed bearer URL.
  await expect.poll(()=>privateImageValue(()=>image.isVisible())).toBe(true);
  await expect.poll(()=>privateImageValue(()=>image.evaluate(n=>(n as HTMLImageElement).naturalWidth))).toBe(23);
}
async function csrf(request:APIRequestContext) {const r=await http(()=>request.get('/api/v1/auth/session'));expect(r.status()).toBe(200);return (await json(r)).csrf_token as string;}
async function helper(preset:string,action:string,runtime=false):Promise<Record<string,number|boolean>> {
  const args=['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`];
  if(runtime)args.push('-v',`${counterDir}:/run/m2-browser-counters:rw`);
  args.push(runtime?'browser-runtime':'browser-provision','python',runtime?'scripts/m2_4_browser_worker.py':'scripts/m2_4_browser_fixture.py','--preset',preset,'--action',action);
  const r=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:65536})));
  try{return JSON.parse(r.stdout);}catch{throw new Error('E2E_SAFE_FAILURE:MESSAGING_FIXTURE_OUTPUT');}
}
function oneCommand(before:Record<string,number|boolean>,after:Record<string,number|boolean>) {for(const key of ['messages','receipts','audit_events','outbox_events','jobs'])expect(Number(after[key])-Number(before[key])).toBe(1);}
async function loginForm(page:Page,preset:string){await page.getByLabel('Логин').fill(fixtures[preset].login);await page.getByLabel('Пароль').fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(panel(page)).toBeVisible();}
async function choose(page:Page,preset:string,id=inventory[preset].conversation_id){
  const ws=fixtures[preset].workspace_id;if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==ws)await page.getByLabel('Workspace',{exact:true}).selectOption(ws);
  await expect(panel(page).getByRole('region',{name:'Диалоги',exact:true}).locator('li').first()).toBeVisible();
  const choice=page.getByTestId(`conversation-${id}`);
  while(!await choice.count()){const more=panel(page).getByRole('button',{name:'Ещё диалоги',exact:true});await expect(more).toBeVisible();await expect(more).toBeEnabled();await more.click();await expect(panel(page).getByText('Загружаем диалоги…',{exact:true})).toHaveCount(0);}
  await choice.click();await expect(panel(page).getByText('Загружаем сообщения…',{exact:true})).toHaveCount(0);await expect(panel(page).getByLabel('Ручной текстовый ответ')).toBeVisible();
}
async function signIn(page:Page,preset:string){await page.goto('/');await loginForm(page,preset);await choose(page,preset);await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeEnabled();}
async function history(request:APIRequestContext,preset:string,cursor:string|null=null){const r=await http(()=>request.get(`${messages(preset)}?limit=25${cursor===null?'':`&cursor=${encodeURIComponent(cursor)}`}`));expect(r.status()).toBe(200);return parsePage(await json(r),parseMessage);}
async function send(page:Page,text:string):Promise<SendReceipt>{
  await panel(page).getByLabel('Ручной текстовый ответ').fill(text);
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'));
  await panel(page).getByRole('button',{name:'Проверить и отправить'}).click();const r=await response;expect(r.status()).toBe(202);
  const receipt=parseReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())));
  await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeEnabled();return receipt;
}
async function refresh(page:Page){await panel(page).getByRole('button',{name:'Обновить сообщения'}).click();await expect(panel(page).getByText('Загружаем сообщения…',{exact:true})).toHaveCount(0);}
async function worker(preset:string,action='success'){return helper(preset,action,true);}
function row(page:Page,id:string){return page.getByTestId(`message-${id}`);}
const post=async(request:APIRequestContext,preset:string,text:string,key:string,token:string)=>http(()=>request.post(messages(preset),{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':key},data:{text}}));
async function safeContinue(route:Route){requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_CONTINUE_FAILED',()=>route.continue()));}

test('@narrow CONTROLLED incoming text/private image -> exact keyboard reply -> Worker current delivery',async({page},info)=>{
  test.setTimeout(60000);await signIn(page,'happy');
  await expect(panel(page).getByText('Incoming happy main — é 🎨',{exact:true})).toBeVisible();
  if(info.project.name==='chromium-desktop'){await expect(panel(page).getByText('Изображение загружается.')).toBeVisible();await expect(panel(page).getByText(/Изображение недоступно · INVALID_INPUT/)).toBeVisible();}
  const ready=row(page,inventory.happy.images.ready.message_id);const imageRequests:Promise<boolean>[]=[];
  page.on('request',request=>{if(request.resourceType()==='image'){imageRequests.push(request.allHeaders().then(h=>!h['x-csrf-token']&&!h.authorization&&!h.referer&&!h.cookie));}});
  await ready.getByRole('button',{name:'Открыть изображение'}).click();const img=ready.getByRole('img');await loadedPrivateImage(img);
  const signed=await privateImageValue(()=>img.getAttribute('src'));expect(!!signed).toBe(true);expect((await panel(page).textContent())!.includes(signed!)).toBe(false);expect(imageRequests.length>0).toBe(true);expect((await Promise.all(imageRequests)).every(Boolean)).toBe(true);
  const unsigned=new URL(signed!);unsigned.search='';const anonymous=await http(()=>page.request.get(unsigned.href));expect(anonymous.status()).toBe(403);
  const before=await helper('happy','stats'),calls=await worker('happy','stats');const text=`  Manual ${randomUUID()}\ne\u0301 🙂  `;let posts=0;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'))posts++;});
  const input=panel(page).getByLabel('Ручной текстовый ответ');await input.fill(text);await input.press('Enter');const exact=await input.inputValue();expect(exact===text+'\n').toBe(true);expect(posts).toBe(0);
  await input.press('Tab');await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeFocused();
  const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'));await page.keyboard.press('Enter');const r=await accepted;expect(r.status()).toBe(202);const receipt=parseReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())));
  await expect(row(page,receipt.message_id).getByText('В очереди',{exact:true})).toBeVisible();expect((await row(page,receipt.message_id).locator('.message-text').textContent())===exact).toBe(true);
  const ran=await worker('happy');expect(Number(ran.calls)-Number(calls.calls)).toBe(1);expect(Number(ran.effects)-Number(calls.effects)).toBe(1);await refresh(page);await expect(row(page,receipt.message_id).getByText('Канал принял',{exact:true})).toBeVisible();oneCommand(before,await helper('happy','stats'));
  await page.reload();await choose(page,'happy');expect(posts).toBe(1);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
});

test('real committed202 response loss -> login plus CSRF recovery -> one command and same receipt',async({page})=>{
  test.setTimeout(60000);await signIn(page,'recovery');const before=await helper('recovery','stats');let attempts=0,body:string|null=null,key:string|undefined,identical=true,first:SendReceipt|undefined;
  let complete!:(value:SafeResult<number>)=>void;const committed=new Promise<SafeResult<number>>(r=>{complete=r;});
  await page.route(`**${messages('recovery')}`,async route=>{
    if(route.request().method()!=='POST'){await safeContinue(route);return;}
    attempts++;if(attempts>1){identical=identical&&body===route.request().postData()&&key===route.request().headers()['idempotency-key'];await safeContinue(route);return;}
    body=route.request().postData();key=route.request().headers()['idempotency-key'];const result=await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch({timeout:10000}));
    if(result.ok){const parsed=await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>parseReceipt(await result.value.json()));if(parsed.ok)first=parsed.value;else{complete(parsed);return;}}
    const aborted=await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed'));complete(!result.ok?result:!aborted.ok?aborted:{ok:true,value:result.value.status()});
  });
  try{
    await panel(page).getByLabel('Ручной текстовый ответ').fill('  Lost202\né 🙂  ');await panel(page).getByRole('button',{name:'Проверить и отправить'}).click();expect(requireSafeResult(await committed)).toBe(202);await expect(panel(page).getByText(/Результат запроса неизвестен/)).toBeVisible();oneCommand(before,await helper('recovery','stats'));
    await page.context().clearCookies();await panel(page).getByRole('button',{name:'Проверить сессию для ответа'}).click();await loginForm(page,'recovery');await choose(page,'recovery');
    // Rotate through real auth API behind the rendered CSRF token. The replay
    // must fail CSRF, recover current session, then still use the original body/key.
    const token=await csrf(page.request);const rotate=await http(()=>page.request.post('/api/v1/auth/rotate',{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}));expect(rotate.status()).toBe(200);
    const rejected=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===messages('recovery'));
    await panel(page).getByRole('button',{name:'Повторить исходный ответ'}).click();expect((await rejected).status()).toBe(403);
    await expect(panel(page).getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled();const replayed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===messages('recovery'));
    await panel(page).getByRole('button',{name:'Повторить исходный ответ'}).click();const replay=await replayed;expect(replay.status()).toBe(202);const value=parseReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>replay.json())));expect(value.outcome).toBe('REPLAY');expect(value.receipt_id===first?.receipt_id&&value.message_id===first?.message_id&&value.accepted_at===first?.accepted_at).toBe(true);
    expect(attempts).toBe(3);expect(identical).toBe(true);oneCommand(before,await helper('recovery','stats'));expect((await worker('recovery')).calls).toBe(1);await refresh(page);await expect(row(page,value.message_id).getByText('Канал принял',{exact:true})).toBeVisible();
  }finally{await page.unrouteAll({behavior:'wait'});body=null;key=undefined;first=undefined;}
});

test('canonical UNKNOWN survives replacement worker, same receipt and reload with one adapter CALL',async({page})=>{
  test.setTimeout(60000);await signIn(page,'unknown');const before=await helper('unknown','stats');let key='',text='';
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===messages('unknown')){key=r.headers()['idempotency-key'];text=JSON.parse(r.postData()!).text;}});
  const receipt=await send(page,`UNKNOWN ${randomUUID()}`);const ran=await worker('unknown','unknown');expect(ran.calls).toBe(1);expect(ran.effects).toBe(1);await refresh(page);await expect(row(page,receipt.message_id).getByText(/Результат неизвестен — повтора нет/)).toBeVisible();expect(await row(page,receipt.message_id).getByRole('button').count()).toBe(0);
  const replay=await post(page.request,'unknown',text,key,await csrf(page.request));expect(replay.status()).toBe(202);const observed=parseReceipt(await json(replay));expect(observed.outcome==='REPLAY'&&observed.message_id===receipt.message_id).toBe(true);
  const restarted=await worker('unknown','recover');expect(restarted.calls).toBe(1);expect(restarted.effects).toBe(1);expect(restarted.worked).toBe(0);await page.reload();await choose(page,'unknown');await expect(row(page,receipt.message_id).getByText(/Результат неизвестен — повтора нет/)).toBeVisible();oneCommand(before,await helper('unknown','stats'));expect((await worker('unknown','stats')).calls).toBe(1);key='';text='';
});

test('valid202 plus failed history GET permits only read recovery and no second POST',async({page})=>{
  test.setTimeout(60000);await signIn(page,'read_failure');let failRead=true,posts=0;
  await page.route(`**${messages('read_failure')}*`,async route=>{if(route.request().method()==='POST'){posts++;await safeContinue(route);}else if(failRead){failRead=false;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));}else await safeContinue(route);});
  await panel(page).getByLabel('Ручной текстовый ответ').fill('Accepted before read failure');await panel(page).getByRole('button',{name:'Проверить и отправить'}).click();await expect(panel(page).getByText('Намерение подтверждено. Повторяется только чтение.')).toBeVisible();expect(await panel(page).getByRole('button',{name:'Повторить исходный ответ'}).count()).toBe(0);
  await panel(page).getByRole('button',{name:'Повторить чтение сообщений'}).click();await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeEnabled();await refresh(page);expect(posts).toBe(1);await worker('read_failure');await page.unrouteAll({behavior:'wait'});
});

test('real limit25 pagination/cursor/null, read-only refresh and fresh history after pending202',async({page})=>{
  test.setTimeout(60000);
  await signIn(page,'pagination');const p=panel(page);let posts=0;page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'))posts++;});
  const connections=p.getByRole('region',{name:'Подключения',exact:true}),conversations=p.getByRole('region',{name:'Диалоги',exact:true}),historyRegion=p.getByRole('region',{name:'История сообщений',exact:true});
  await connections.getByRole('button',{name:'Ещё подключения'}).click();await expect(connections.locator('li')).toHaveCount(inventory.pagination.connection_ids.length);await expect(conversations.locator('li')).toHaveCount(inventory.pagination.conversation_ids.length);
  const first=await history(page.request,'pagination');expect(first.items.length).toBe(25);expect(first.next_cursor!==null).toBe(true);const second=await history(page.request,'pagination',first.next_cursor);expect(second.next_cursor).toBeNull();
  const response=page.waitForResponse(r=>r.url().includes(`${messages('pagination')}?limit=25&cursor=`));await historyRegion.getByRole('button',{name:'Ещё сообщения'}).click();const loaded=await response;expect(new URL(loaded.url()).searchParams.get('cursor')===first.next_cursor).toBe(true);
  await expect(historyRegion.locator('ol > li')).toHaveCount(first.items.length+second.items.length);const ids=await historyRegion.locator('ol > li').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-testid')));expect(new Set(ids).size).toBe(ids.length);expect(await historyRegion.getByRole('button',{name:'Ещё сообщения'}).count()).toBe(0);
  await refresh(page);await expect(historyRegion.locator('ol > li')).toHaveCount(25);await connections.getByRole('button',{name:'Обновить подключения'}).click();await expect(connections.locator('li')).toHaveCount(25);expect(posts).toBe(0);
  const before=await helper('pagination','stats');let release!:()=>void,complete!:(result:SafeResult<number>)=>void;
  const gate=new Promise<void>(r=>{release=r;}),committed=new Promise<SafeResult<number>>(r=>{complete=r;});
  await page.route(`**${messages('pagination')}`,async route=>{
    if(route.request().method()!=='POST'){await safeContinue(route);return;}
    const real=await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch());
    complete(real.ok?{ok:true,value:real.value.status()}:real);if(!real.ok)return;
    await gate;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_RELEASE_FAILED',()=>route.fulfill({response:real.value})));
  });
  try{
    await p.getByLabel('Ручной текстовый ответ').fill('Reply while older history is available');
    const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===messages('pagination'));
    await p.getByRole('button',{name:'Проверить и отправить'}).click();expect(requireSafeResult(await committed)).toBe(202);
    await expect(historyRegion.getByRole('button',{name:'Ещё сообщения'})).toBeDisabled();
    const fresh=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname===messages('pagination')&&!new URL(r.url()).searchParams.has('cursor'));
    release();const receipt=parseReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>(await accepted).json())));expect((await fresh).status()).toBe(200);
    await expect(row(page,receipt.message_id).getByText('В очереди',{exact:true})).toBeVisible();expect(posts).toBe(1);oneCommand(before,await helper('pagination','stats'));await worker('pagination');
  }finally{release();await page.unrouteAll({behavior:'wait'});}
});

test('authenticated isolation, mismatched private refs and real late history/grant across Workspace',async({page})=>{
  test.setTimeout(60000);await signIn(page,'isolation');const token=await csrf(page.request),before=await helper('foreign','stats');
  for(const suffix of ['channel-connections?limit=25','conversations?limit=25',`conversations/${inventory.foreign.conversation_id}/messages?limit=25`]){const r=await http(()=>page.request.get(path('foreign',suffix)));expect(r.status()).toBe(403);}
  expect((await post(page.request,'foreign','Forbidden',randomUUID(),token)).status()).toBe(403);
  for(const [preset,ref,status] of [['foreign',inventory.foreign.images.ready,403],['isolation',inventory.foreign.images.ready,404]] as const){const r=await http(()=>page.request.post(grantPath(preset,ref),{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}));expect(r.status()).toBe(status);}
  expect(await helper('foreign','stats')).toEqual(before);
  let release!:()=>void,started!:()=>void;const gate=new Promise<void>(r=>{release=r;}),seen=new Promise<void>(r=>{started=r;});
  await page.route(`**${messages('isolation')}?*`,async route=>{const real=requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch()));started();await gate;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_RELEASE_FAILED',()=>route.fulfill({response:real})));});
  await panel(page).getByRole('button',{name:'Обновить сообщения'}).click();await seen;await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.isolation_peer.workspace_id);await expect(panel(page).getByText('Загружаем сообщения…',{exact:true})).toHaveCount(0);release();await page.unrouteAll({behavior:'wait'});expect(await panel(page).getByText('Incoming isolation main — é 🎨',{exact:true}).count()).toBe(0);await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
  await choose(page,'isolation');let releaseGrant!:()=>void,grantStarted!:()=>void;const grantGate=new Promise<void>(r=>{releaseGrant=r;}),grantSeen=new Promise<void>(r=>{grantStarted=r;});
  await page.route(`**${grantPath('isolation')}`,async route=>{const real=requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch()));expect(real.status()).toBe(200);grantStarted();await grantGate;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_RELEASE_FAILED',()=>route.fulfill({response:real})));});
  await row(page,inventory.isolation.images.ready.message_id).getByRole('button',{name:'Открыть изображение'}).click();await grantSeen;await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.isolation_peer.workspace_id);releaseGrant();await page.unrouteAll({behavior:'wait'});expect(await panel(page).getByRole('img').count()).toBe(0);await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
});

test('OWNER downgrade denies new grants/send/history and hides private UI; issued grant keeps TTL boundary',async({page})=>{
  test.setTimeout(60000);await signIn(page,'revoked');const ready=row(page,inventory.revoked.images.ready.message_id);await ready.getByRole('button',{name:'Открыть изображение'}).click();const image=ready.getByRole('img');await loadedPrivateImage(image);const signed=(await privateImageValue(()=>image.getAttribute('src')))!;const token=await csrf(page.request),before=await helper('revoked','stats');await helper('revoked','downgrade');
  expect((await http(()=>page.request.get(signed))).status()).toBe(200);await page.getByRole('button',{name:'Обновить подписку'}).click();await expect(page.getByText('Нет доступа к данным владельца',{exact:true})).toBeVisible();expect(await page.getByRole('img').count()).toBe(0);expect(await page.getByLabel('Ручной текстовый ответ').count()).toBe(0);
  await expect(page.getByRole('region',{name:'Audit',exact:true})).toHaveCount(0);expect(await page.getByTestId('current-contact').count()).toBe(0);expect((await http(()=>page.request.post(grantPath('revoked'),{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}))).status()).toBe(403);
  expect((await http(()=>page.request.get(messages('revoked')+'?limit=25'))).status()).toBe(403);expect((await post(page.request,'revoked','Forbidden',randomUUID(),token)).status()).toBe(403);expect(await helper('revoked','stats')).toEqual(before);
  await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.isolation_peer.workspace_id);await expect(panel(page)).toBeVisible();await page.reload();await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.revoked.workspace_id);await expect(panel(page)).toHaveCount(0);await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
});

for(const [preset,action] of [['restricted','restrict'],['inactive','disable']] as const)test(`real ${preset} admission preserves history/private reads and editable draft`,async({page})=>{
  test.setTimeout(60000);await signIn(page,preset);await expect(panel(page).getByText(/Доступно по наблюдению/)).toBeVisible();const before=await helper(preset,'stats');await helper(preset,action);const draft='  Explicit new reply  ';await panel(page).getByLabel('Ручной текстовый ответ').fill(draft);const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===messages(preset));await panel(page).getByRole('button',{name:'Проверить и отправить'}).click();expect((await response).status()).toBe(409);await expect(panel(page).getByText('Сервер не разрешил новый ответ. Черновик сохранён.')).toBeVisible();expect((await panel(page).getByLabel('Ручной текстовый ответ').inputValue())===draft).toBe(true);await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeEnabled();await refresh(page);await row(page,inventory[preset].images.ready.message_id).getByRole('button',{name:'Открыть изображение'}).click();await loadedPrivateImage(panel(page).getByRole('img'));expect(await helper(preset,'stats')).toEqual(before);
});

test('permanent CONTROLLED refusal is current FAILED without resend',async({page})=>{
  test.setTimeout(60000);await signIn(page,'permanent');const receipt=await send(page,'Finite permanent failure');const ran=await worker('permanent','permanent');expect(ran.calls).toBe(1);expect(ran.effects).toBe(0);await refresh(page);await expect(row(page,receipt.message_id).getByText(/Отправка отклонена/)).toBeVisible();expect(await row(page,receipt.message_id).getByRole('button').count()).toBe(0);
});

test('real credentialed messaging CORS POST and rejected preflight do not duplicate command',async({page})=>{
  test.setTimeout(60000);await signIn(page,'foreign');const before=await helper('foreign','stats'),token=await csrf(page.request),url=`http://127.0.0.1:8000${messages('foreign')}`;
  const network=await page.context().newCDPSession(page),statuses:number[]=[],errors:string[]=[];await network.send('Network.enable');network.on('Network.responseReceived',e=>{if(e.type==='Preflight'&&e.response.url===url)statuses.push(e.response.status);});network.on('Network.loadingFailed',e=>{if(e.corsErrorStatus)errors.push(e.corsErrorStatus.corsError);});
  try{
    const positive=await page.evaluate(async({url,token,key})=>{try{return (await fetch(url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':key},body:JSON.stringify({text:'CORS accepted'})})).status;}catch{return 0;}},{url,token,key:randomUUID()});expect(positive).toBe(202);await expect.poll(()=>statuses.includes(200)).toBe(true);
    const negative=await page.evaluate(async({url,token,key})=>{try{await fetch(url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':key,'X-Disallowed':'1'},body:JSON.stringify({text:'Must not commit'})});return false;}catch{return true;}},{url,token,key:randomUUID()});expect(negative).toBe(true);await expect.poll(()=>statuses.includes(400)).toBe(true);await expect.poll(()=>errors.some(e=>e.includes('Preflight'))).toBe(true);oneCommand(before,await helper('foreign','stats'));await worker('foreign');
  }finally{await network.detach();}
});
