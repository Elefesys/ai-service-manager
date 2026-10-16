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
import { parseControlState, parseControlReceipt, type ControlBody, type ControlOperation } from '../src/conversation-control-api';
import { parseEscalation, parseEscalationPage, parseEscalationReceipt, type EscalationView, type EscalationBody, type EscalationReceipt, type EscalationOperation } from '../src/escalation-api';

const envPath=process.env.ASM_BROWSER_ENV_FILE, fixturePath=process.env.ASM_BROWSER_FIXTURE_FILE, inventoryPath=process.env.ASM_BROWSER_MESSAGING_FILE, passwordPath=process.env.ASM_BROWSER_PASSWORD_FILE, counterDir=process.env.ASM_BROWSER_COUNTER_DIR;
if(!envPath||!fixturePath||!inventoryPath||!passwordPath||!counterDir) throw new Error('E2E_SAFE_FAILURE:MESSAGING_PRIVATE_FILES_REQUIRED');
function privateJson(path:string) { try { return JSON.parse(readFileSync(path,'utf8')); } catch { throw new Error('E2E_SAFE_FAILURE:MESSAGING_FIXTURE_OUTPUT'); } }
const fixtures:Record<string,{workspace_id:string;user_account_id:string;login:string}>=privateJson(fixturePath).messaging_fixtures;
type Ref={conversation_id:string;message_id:string;file_id:string};
type Inventory={conversation_id:string;client_id:string;alternate_conversation_id:string;alternate_client_id:string;connection_ids:string[];conversation_ids:string[];message_ids:string[];images:{ready:Ref;failed?:Ref;pending?:Ref};material_photos?:Record<string,Ref>};
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
async function helper(preset:string,action:string,runtime=false):Promise<Record<string,number|boolean|string>> {
  const args=['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`];
  if(runtime)args.push('-v',`${counterDir}:/run/m2-browser-counters:rw`);
  args.push(runtime?'browser-runtime':'browser-provision','python',runtime?'scripts/m2_4_browser_worker.py':'scripts/m2_4_browser_fixture.py','--preset',preset,'--action',action);
  const r=requireSafeResult(await safeDiagnostic('MESSAGING_FIXTURE_FAILED',()=>promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:65536})));
  try{return JSON.parse(r.stdout);}catch{throw new Error('E2E_SAFE_FAILURE:MESSAGING_FIXTURE_OUTPUT');}
}
function oneCommand(before:Record<string,number|boolean|string>,after:Record<string,number|boolean|string>) {for(const key of ['messages','receipts','audit_events','outbox_events','jobs'])expect(Number(after[key])-Number(before[key])).toBe(1);}
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

const controlPanel=(page:Page)=>page.getByRole('region',{name:'Управление диалогом',exact:true});
const controlContext=(preset:string)=>({workspace:fixtures[preset].workspace_id,conversation:inventory[preset].conversation_id,client:inventory[preset].client_id});
const controlPath=(preset:string,route='control')=>path(preset,`conversations/${inventory[preset].conversation_id}/${route}`);
async function currentControl(page:Page,preset:string){const r=await http(()=>page.request.get(controlPath(preset)));expect(r.status()).toBe(200);return parseControlState(await json(r),controlContext(preset));}
async function changeControl(page:Page,preset:string,operation:ControlOperation,keyboard=false){
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===controlPath(preset,operation==='RESUME'?'resume':'takeover'));
  const button=controlPanel(page).getByRole('button',{name:operation==='RESUME'?'Разрешить автоматику':'Забрать управление',exact:true});
  if(keyboard){await controlPanel(page).getByRole('button',{name:'Забрать управление'}).focus();await page.keyboard.press('Tab');await expect(button).toBeFocused();await page.keyboard.press('Enter');}else await button.click();
  const r=await pending;expect(r.status()).toBe(200);const body=requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>JSON.parse(r.request().postData()!))) as ControlBody;
  const receipt=parseControlReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())),controlContext(preset),operation,body);expect(receipt.outcome).toBe('ACCEPTED');
  await expect(controlPanel(page).getByRole('button',{name:'Забрать управление'})).toBeEnabled();
}
function controlDelta(before:Record<string,number|boolean|string>,after:Record<string,number|boolean|string>,count:number){for(const key of ['control_receipts','control_audit_events'])expect(Number(after[key])-Number(before[key])).toBe(count);}

test('@narrow CONTROLLED incoming text/private image -> exact keyboard reply -> Worker current delivery',async({page},info)=>{
  test.setTimeout(60000);await signIn(page,'happy');
  await expect(panel(page).getByText('Incoming happy main — é 🎨',{exact:true})).toBeVisible();
  if(info.project.name==='chromium-desktop'){await expect(panel(page).getByText('Изображение загружается.')).toBeVisible();await expect(panel(page).getByText(/Изображение недоступно · INVALID_INPUT/)).toBeVisible();}
  const ready=row(page,inventory.happy.images.ready.message_id);const imageRequests:Promise<boolean>[]=[];
  page.on('request',request=>{if(request.resourceType()==='image'){imageRequests.push(request.allHeaders().then(h=>!h['x-csrf-token']&&!h.authorization&&!h.referer&&!h.cookie));}});
  await ready.getByRole('button',{name:'Открыть изображение'}).click();const img=ready.getByRole('img');await loadedPrivateImage(img);
  const signed=await privateImageValue(()=>img.getAttribute('src'));expect(!!signed).toBe(true);expect((await panel(page).textContent())!.includes(signed!)).toBe(false);expect(imageRequests.length>0).toBe(true);expect((await Promise.all(imageRequests)).every(Boolean)).toBe(true);
  const unsigned=new URL(signed!);unsigned.search='';const anonymous=await http(()=>page.request.get(unsigned.href));expect(anonymous.status()).toBe(403);
  // The shared worker drains scheduled FETCH jobs too. Keep CONTROL's manual/
  // worker assertions here, after the original PENDING/FAILED image assertions.
  const beforeControl=await helper('happy','control-stats'),initialControl=await currentControl(page,'happy');let controlPosts=0;
  page.on('request',r=>{if(r.method()==='POST'&&/\/(resume|takeover)$/.test(new URL(r.url()).pathname))controlPosts++;});
  await controlPanel(page).getByRole('button',{name:'Обновить режим'}).click();await expect(controlPanel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();expect(controlPosts).toBe(0);
  await changeControl(page,'happy','RESUME',true);await expect(controlPanel(page).getByText('Автоматика разрешена',{exact:true})).toBeVisible();
  await changeControl(page,'happy','TAKEOVER');await expect(controlPanel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();
  const before=await helper('happy','stats'),calls=await worker('happy','stats');const text=`  Manual ${randomUUID()}\ne\u0301 🙂  `;let posts=0;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'))posts++;});
  const input=panel(page).getByLabel('Ручной текстовый ответ');await input.fill(text);await input.press('Enter');const exact=await input.inputValue();expect(exact===text+'\n').toBe(true);expect(posts).toBe(0);
  await input.press('Tab');await expect(panel(page).getByRole('button',{name:'Проверить и отправить'})).toBeFocused();
  const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/messages'));await page.keyboard.press('Enter');const r=await accepted;expect(r.status()).toBe(202);const receipt=parseReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>r.json())));
  await expect(row(page,receipt.message_id).getByText('В очереди',{exact:true})).toBeVisible();expect((await row(page,receipt.message_id).locator('.message-text').textContent())===exact).toBe(true);
  await expect(controlPanel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();const finalControl=await currentControl(page,'happy');expect(finalControl.control_mode).toBe('HUMAN');expect(BigInt(finalControl.control_generation)-BigInt(initialControl.control_generation)).toBe(3n);expect(BigInt(finalControl.context_version)-BigInt(initialControl.context_version)).toBe(1n);
  controlDelta(beforeControl,await helper('happy','control-stats'),2);expect(controlPosts).toBe(2);
  const ran=await worker('happy');expect(Number(ran.calls)-Number(calls.calls)).toBe(1);expect(Number(ran.effects)-Number(calls.effects)).toBe(1);await refresh(page);await expect(row(page,receipt.message_id).getByText('Канал принял',{exact:true})).toBeVisible();oneCommand(before,await helper('happy','stats'));
  await page.reload();await choose(page,'happy');expect(posts).toBe(1);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
  await expect(controlPanel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();expect(controlPosts).toBe(2);
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
  const beforeControl=await helper('unknown','control-stats');await controlPanel(page).getByRole('button',{name:'Обновить режим'}).click();await expect(controlPanel(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();
  await changeControl(page,'unknown','TAKEOVER');await expect(controlPanel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();await expect(controlPanel(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();expect(await controlPanel(page).getByRole('button',{name:/resend|повтор.*отправ/i}).count()).toBe(0);controlDelta(beforeControl,await helper('unknown','control-stats'),1);
  const replay=await post(page.request,'unknown',text,key,await csrf(page.request));expect(replay.status()).toBe(202);const observed=parseReceipt(await json(replay));expect(observed.outcome==='REPLAY'&&observed.message_id===receipt.message_id).toBe(true);
  const restarted=await worker('unknown','recover');expect(restarted.calls).toBe(1);expect(restarted.effects).toBe(1);expect(restarted.worked).toBe(0);await page.reload();await choose(page,'unknown');await expect(row(page,receipt.message_id).getByText(/Результат неизвестен — повтора нет/)).toBeVisible();oneCommand(before,await helper('unknown','stats'));expect((await worker('unknown','stats')).calls).toBe(1);key='';text='';
  await expect(controlPanel(page).getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();
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

// UI-E01–07. Keep these worker journeys AFTER the retained seeded PENDING image
// assertion above. Each request is produced by accepted Resume -> marker -> Jobs.
const escQueue=(page:Page)=>page.getByRole('region',{name:'Запросы владельцу',exact:true});
const escDetail=(page:Page)=>page.getByRole('region',{name:'Карточка запроса',exact:true});
const escPath=(preset:string,id?:string)=>path(preset,`escalations${id?`/${id}`:''}`);
const escContext=(v:EscalationView)=>({workspace:v.workspace_id,escalation:v.escalation_id,conversation:v.conversation_id,client:v.client_id});
async function escList(request:APIRequestContext,preset:string){const r=await http(()=>request.get(`${escPath(preset)}?limit=10&status=ALL`));expect(r.status()).toBe(200);return parseEscalationPage(await json(r),fixtures[preset].workspace_id,'ALL');}
async function escRead(request:APIRequestContext,preset:string,v:EscalationView){const r=await http(()=>request.get(escPath(preset,v.escalation_id)));expect(r.status()).toBe(200);return parseEscalation(await json(r),fixtures[preset].workspace_id,escContext(v));}
async function createEsc(page:Page,preset:string,alternate=false){
  const c={workspace:fixtures[preset].workspace_id,conversation:alternate?inventory[preset].alternate_conversation_id:inventory[preset].conversation_id,client:alternate?inventory[preset].alternate_client_id:inventory[preset].client_id};
  const url=path(preset,`conversations/${c.conversation}`),read=await http(()=>page.request.get(`${url}/control`));expect(read.status()).toBe(200);const state=parseControlState(await json(read),c);
  const body:ControlBody={expected_client_id:c.client,expected_control_generation:state.control_generation,expected_context_version:state.context_version};
  const token=await csrf(page.request),r=await http(()=>page.request.post(`${url}/resume`,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:body}));expect(r.status()).toBe(200);expect(parseControlReceipt(await json(r),c,'RESUME',body).outcome).toBe('ACCEPTED');
  const ran=await worker(preset,alternate?'escalate-alternate':'escalate-main');expect(ran.created).toBe(1);expect(ran.calls).toBe(0);expect(ran.effects).toBe(0);
  const item=(await escList(page.request,preset)).items.find(v=>v.conversation_id===c.conversation&&v.status==='PENDING');expect(!!item).toBe(true);expect(item!.client_id===c.client&&item!.assignee_user_account_id===fixtures[preset].user_account_id).toBe(true);return item!;
}
async function openEsc(page:Page,v:EscalationView){
  await escQueue(page).getByRole('button',{name:'Обновить очередь'}).click();await expect(escQueue(page).getByText('Загружаем очередь…',{exact:true})).toHaveCount(0);
  await page.getByTestId(`escalation-${v.escalation_id}`).click();await expect(escDetail(page).getByText('Ожидается решение владельца',{exact:true})).toBeVisible();
}
function escDelta(before:Record<string,number|boolean|string>,after:Record<string,number|boolean|string>,count:number){
  for(const key of ['escalation_receipts','escalation_audit'])expect(Number(after[key])-Number(before[key])).toBe(count);
  for(const key of ['messages','receipts','audit_events','outbox_events','jobs','control_receipts','control_audit_events','escalations','escalation_timers'])expect(after[key]).toBe(before[key]);
}
async function decide(page:Page,preset:string,v:EscalationView,operation:EscalationOperation,answer='',keyboard=false){
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`${escPath(preset,v.escalation_id)}/${operation==='RESOLVE'?'resolve':'cancel'}`);
  if(operation==='RESOLVE'){
    const input=escDetail(page).getByLabel('Внутренний ответ владельца');await input.fill(answer);
    if(keyboard){await input.press('Tab');await expect(escDetail(page).getByRole('button',{name:'Сохранить внутренний ответ'})).toBeFocused();await page.keyboard.press('Enter');}
    else await escDetail(page).getByRole('button',{name:'Сохранить внутренний ответ'}).click();
  }else await escDetail(page).getByRole('button',{name:'Отменить запрос'}).click();
  const response=await pending;expect(response.status()).toBe(200);const body=requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>JSON.parse(response.request().postData()!))) as EscalationBody;
  expect(operation==='RESOLVE'?body.answer_text===answer:!Object.hasOwn(body,'answer_text')).toBe(true);
  const saved=parseEscalationReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json())),escContext(v),operation,body);
  await expect(escDetail(page).getByText('Решение сохранено. Актуальная карточка получена.')).toBeVisible();return saved;
}

test('@narrow Escalation runtime queue -> exact internal resolve and cancel; inactive/restricted, keyboard, no send or Resume',async({page},info)=>{
  test.setTimeout(60000);const preset=info.project.name==='chromium-narrow'?'esc_narrow':'esc_happy';await signIn(page,preset);
  const main=await createEsc(page,preset),alternate=await createEsc(page,preset,true);const before=await helper(preset,'escalation-stats');
  expect(before.escalations).toBe(2);expect(before.escalation_timers).toBe(6);await helper(preset,'disable');await helper(preset,'restrict');
  await openEsc(page,main);await expect(escDetail(page).getByText(/Запись напоминания не означает/)).toBeVisible();const controlBefore=await currentControl(page,preset);let writes=0;
  page.on('request',r=>{if(r.method()==='POST'&&/\/(messages|resume|takeover)$/.test(new URL(r.url()).pathname))writes++;});
  const exact='  Внутреннее решение\ne\u0301 🎨  ';const saved=await decide(page,preset,main,'RESOLVE',exact,true);expect(saved.outcome).toBe('ACCEPTED');
  expect((await escDetail(page).locator('.exact-answer').textContent())===exact).toBe(true);const current=await escRead(page.request,preset,main);expect(current.status).toBe('RESOLVED');expect(current.waiting).toBeNull();expect(current.resolution?.answer_text===exact).toBe(true);
  const controlAfter=await currentControl(page,preset);expect(controlAfter.control_mode).toBe(controlBefore.control_mode);expect(controlAfter.control_generation).toBe(controlBefore.control_generation);expect(BigInt(controlAfter.context_version)-BigInt(controlBefore.context_version)).toBe(1n);
  await expect(panel(page).getByText(/По этому диалогу сохранено внутреннее решение/)).toBeVisible();expect((await panel(page).getByLabel('Ручной текстовый ответ').inputValue())==='').toBe(true);
  await openEsc(page,alternate);await decide(page,preset,alternate,'CANCEL');const closed=await escRead(page.request,preset,alternate);expect(closed.status).toBe('CANCELLED');expect(closed.closure?.reason).toBe('OWNER_CANCELLED');expect(closed.resolution).toBeNull();escDelta(before,await helper(preset,'escalation-stats'),2);expect(writes).toBe(0);
  await escQueue(page).getByLabel('Сохранённый статус').selectOption('ALL');await expect(escQueue(page).locator('.escalation-list > li')).toHaveCount(2);await expect(escQueue(page).getByRole('button',{name:'Ещё запросы'})).toHaveCount(0);
  const restart=await worker(preset,'recover');expect(restart.calls).toBe(0);expect(restart.effects).toBe(0);
  await page.reload();await expect(escQueue(page)).toBeVisible();expect(writes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
});

test('Escalation committed200 loss -> real login/CSRF recovery -> exact same key/body REPLAY and one decision',async({page})=>{
  test.setTimeout(60000);const preset='esc_recovery';await signIn(page,preset);const v=await createEsc(page,preset);await openEsc(page,v);const before=await helper(preset,'escalation-stats');
  let attempts=0,original:string|null=null,key:string|undefined,first:EscalationReceipt|undefined,identical=true;
  let complete!:(result:SafeResult<number>)=>void;const committed=new Promise<SafeResult<number>>(r=>{complete=r;});const url=`${escPath(preset,v.escalation_id)}/resolve`;
  await page.route(`**${url}`,async route=>{
    attempts++;if(attempts>1){identical=identical&&original===route.request().postData()&&key===route.request().headers()['idempotency-key'];await safeContinue(route);return;}
    original=route.request().postData();key=route.request().headers()['idempotency-key'];const real=await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch({timeout:10000}));
    if(real.ok){const parsed=await safeDiagnostic('MESSAGING_BODY_FAILED',async()=>parseEscalationReceipt(await real.value.json(),escContext(v),'RESOLVE',JSON.parse(original!) as EscalationBody));if(parsed.ok)first=parsed.value;else{complete(parsed);return;}}
    const aborted=await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed'));complete(!real.ok?real:!aborted.ok?aborted:{ok:true,value:real.value.status()});
  });
  try{
    await escDetail(page).getByLabel('Внутренний ответ владельца').fill('  Сохранить точно\ne\u0301 🎨  ');await escDetail(page).getByRole('button',{name:'Сохранить внутренний ответ'}).click();expect(requireSafeResult(await committed)).toBe(200);
    await expect(escDetail(page).getByText(/Результат решения неизвестен/)).toBeVisible();escDelta(before,await helper(preset,'escalation-stats'),1);
    await page.context().clearCookies();await escDetail(page).getByRole('button',{name:'Проверить сессию для решения'}).click();await loginForm(page,preset);
    await expect(escDetail(page).getByRole('button',{name:'Повторить исходное решение'})).toBeEnabled();const token=await csrf(page.request);const rotate=await http(()=>page.request.post('/api/v1/auth/rotate',{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}));expect(rotate.status()).toBe(200);
    const denied=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===url);await escDetail(page).getByRole('button',{name:'Повторить исходное решение'}).click();expect((await denied).status()).toBe(403);
    await expect(escDetail(page).getByRole('button',{name:'Повторить исходное решение'})).toBeEnabled();const replayed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===url);await escDetail(page).getByRole('button',{name:'Повторить исходное решение'}).click();const response=await replayed;expect(response.status()).toBe(200);
    const saved=parseEscalationReceipt(requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>response.json())),escContext(v),'RESOLVE',JSON.parse(original!) as EscalationBody);expect(saved.outcome).toBe('REPLAY');expect(JSON.stringify(saved.result)===JSON.stringify(first?.result)).toBe(true);
    await expect(escDetail(page).getByText('Сохранённый внутренний ответ')).toBeVisible();expect(attempts).toBe(3);expect(identical).toBe(true);escDelta(before,await helper(preset,'escalation-stats'),1);expect((await worker(preset,'stats')).calls).toBe(0);
    await page.reload();await expect(escQueue(page)).toBeVisible();expect(attempts).toBe(3);
  }finally{await page.unrouteAll({behavior:'wait'});original=null;key=undefined;first=undefined;}
});

test('Escalation valid200 plus failed GET offers only read recovery',async({page})=>{
  test.setTimeout(60000);const preset='esc_read';await signIn(page,preset);const v=await createEsc(page,preset);await openEsc(page,v);const before=await helper(preset,'escalation-stats');let posts=0,failed=false;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===`${escPath(preset,v.escalation_id)}/cancel`)posts++;});
  await page.route(`**${escPath(preset,v.escalation_id)}`,async route=>{if(!failed){failed=true;requireSafeResult(await safeDiagnostic('MESSAGING_ROUTE_ABORT_FAILED',()=>route.abort('failed')));}else await safeContinue(route);});
  await escDetail(page).getByRole('button',{name:'Отменить запрос'}).click();await expect(escDetail(page).getByText('Решение подтверждено. Повторяется только чтение.')).toBeVisible();await expect(escDetail(page).getByRole('button',{name:'Повторить исходное решение'})).toHaveCount(0);
  await escDetail(page).getByRole('button',{name:'Повторить чтение запроса'}).click();await expect(escDetail(page).getByText(/Отменён владельцем/)).toBeVisible();expect(posts).toBe(1);escDelta(before,await helper(preset,'escalation-stats'),1);await page.unrouteAll({behavior:'wait'});
});

test('Escalation stale tab loses to actual Takeover material change; no automatic retry or answer',async({page,context:browser})=>{
  test.setTimeout(60000);const preset='esc_stale';await signIn(page,preset);const v=await createEsc(page,preset);await openEsc(page,v);const other=await browser.newPage();await other.goto('/');await choose(other,preset);const before=await helper(preset,'escalation-stats');
  try{
    await changeControl(other,preset,'TAKEOVER');let posts=0;page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname===`${escPath(preset,v.escalation_id)}/resolve`)posts++;});
    await escDetail(page).getByLabel('Внутренний ответ владельца').fill('Obsolete internal decision');const rejected=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`${escPath(preset,v.escalation_id)}/resolve`);await escDetail(page).getByRole('button',{name:'Сохранить внутренний ответ'}).click();expect((await rejected).status()).toBe(409);
    await expect(escDetail(page).getByText(/Повтор решения остановлен/)).toBeVisible();await expect(escDetail(page).getByText(/Изменилось управление/)).toBeVisible();await expect(escDetail(page).getByRole('button',{name:'Повторить исходное решение'})).toHaveCount(0);expect(posts).toBe(1);
    const current=await escRead(page.request,preset,v);expect(current.status).toBe('CANCELLED');expect(current.resolution).toBeNull();expect(current.current_context.control_mode).toBe('HUMAN');const after=await helper(preset,'escalation-stats');expect(after.escalation_receipts).toBe(before.escalation_receipts);expect(after.escalation_audit).toBe(before.escalation_audit);controlDelta(before,after,1);
  }finally{await other.close();}
});

test('Escalation live OWNER revoke clears every protected view; peer cancel and Workspace isolation',async({page,context:browser})=>{
  test.setTimeout(60000);const preset='esc_revoked';await signIn(page,preset);const v=await createEsc(page,preset);await openEsc(page,v);const token=await csrf(page.request),before=await helper(preset,'escalation-stats');
  expect((await http(()=>page.request.get(`${escPath('foreign')}?limit=10&status=PENDING`))).status()).toBe(403);
  expect((await http(()=>page.request.get(escPath(preset,inventory.foreign.conversation_id)))).status()).toBe(404);
  await helper(preset,'downgrade');await escQueue(page).getByRole('button',{name:'Обновить очередь'}).click();await expect(page.getByText('Нет доступа к данным владельца',{exact:true})).toBeVisible();
  for(const name of ['Запросы владельцу','Audit','Переписка'])await expect(page.getByRole('region',{name,exact:true})).toHaveCount(0);expect(await page.getByRole('img').count()).toBe(0);
  expect((await http(()=>page.request.get(escPath(preset,v.escalation_id)))).status()).toBe(403);
  const rejected=await http(()=>page.request.post(`${escPath(preset,v.escalation_id)}/cancel`,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:{expected_conversation_id:v.conversation_id,expected_client_id:v.client_id,expected_escalation_version:v.version,expected_control_generation:v.current_context.control_generation,expected_context_version:v.current_context.context_version}}));expect(rejected.status()).toBe(403);escDelta(before,await helper(preset,'escalation-stats'),0);
  await page.getByLabel('Workspace',{exact:true}).selectOption(fixtures.isolation_peer.workspace_id);await expect(escQueue(page)).toBeVisible();await expect(page.getByTestId(`escalation-${v.escalation_id}`)).toHaveCount(0);
  // Separate authenticated actor, never a transplanted session/token.
  const peer=await browser.browser()!.newContext({baseURL:origin});const peerPage=await peer.newPage();
  try{
    await signIn(peerPage,'isolation_peer');await peerPage.getByLabel('Workspace',{exact:true}).selectOption(fixtures[preset].workspace_id);await peerPage.getByTestId(`escalation-${v.escalation_id}`).click();
    await expect(escDetail(peerPage).getByText('Ответственный потерял доступ владельца')).toBeVisible();await expect(escDetail(peerPage).getByRole('button',{name:'Сохранить внутренний ответ'})).toBeDisabled();await expect(escDetail(peerPage).getByRole('button',{name:'Отменить запрос'})).toBeEnabled();
    await decide(peerPage,preset,v,'CANCEL');escDelta(before,await helper(preset,'escalation-stats'),1);expect((await worker(preset,'stats')).calls).toBe(0);
  }finally{await peer.close();}
});

// P-A03-07: synthetic TELEGRAM input -> real V2 ingress/runtime worker -> owner
// API/current panel. No provider row substitution or external Telegram send.
test('material edit and delete refresh the paired current projection and preserve original history',async({page})=>{
  const preset='material';await page.goto('/');await loginForm(page,preset);await choose(page,preset);
  await expect(panel(page).getByText('Material original A',{exact:true})).toBeVisible();
  const original=(await history(page.request,preset)).items[0];expect(original.version).toBe('1');
  expect(await worker(preset,'material-edit')).toEqual({processed:1,replayed:0});await refresh(page);
  await expect(panel(page).getByText('Material edited B',{exact:true})).toBeVisible();
  await expect(panel(page).getByText('Material original A',{exact:true})).toHaveCount(0);
  const edited=(await history(page.request,preset)).items[0];expect(edited.message_id).toBe(original.message_id);expect(edited.text).toBe('Material original A');expect(edited.version).toBe('2');
  expect(edited.current).toEqual({schema_version:1,state:'VISIBLE',content_type:'TEXT',text:'Material edited B',image_availability:'NOT_APPLICABLE',changed:true});
  expect(await worker(preset,'material-edit')).toEqual({processed:0,replayed:1});
  expect((await history(page.request,preset)).items[0]).toEqual(edited);
  expect(await worker(preset,'material-delete')).toEqual({processed:1,replayed:0});await refresh(page);
  await expect(panel(page).getByText('Сообщение удалено.',{exact:true})).toBeVisible();await expect(panel(page).getByText('Material edited B',{exact:true})).toHaveCount(0);
  const deleted=(await history(page.request,preset)).items[0];expect(deleted.version).toBe('3');expect(deleted.text).toBe('Material original A');
  expect(deleted.current).toEqual({schema_version:1,state:'DELETED',content_type:null,text:null,image_availability:'HIDDEN',changed:true});
  await expect(row(page,original.message_id).getByRole('button',{name:'Открыть изображение'})).toHaveCount(0);
  const other=await http(()=>page.request.get(messages(preset,inventory[preset].alternate_conversation_id)));expect(other.status()).toBe(200);
  expect(parsePage(await json(other),parseMessage).items[0].current.text).toBe('Material original alternate');
});

async function materialPhoto(page:Page,label:string){
  const preset='material',ref=inventory[preset].material_photos![label];
  await page.goto('/');await loginForm(page,preset);await choose(page,preset,ref.conversation_id);
  const r=await http(()=>page.request.get(messages(preset,ref.conversation_id)));expect(r.status()).toBe(200);
  const original=parsePage(await json(r),parseMessage).items.find(m=>m.message_id===ref.message_id)!;
  expect(original.version).toBe('1');expect(original.current.image_availability).toBe('ORIGINAL_READY');expect(original.file?.status).toBe('READY');
  const before=await helper(preset,'material-stats');expect(before.files).toBe(4);expect(before.fetches).toBe(4);expect(before.ready).toBe(4);expect(before.winners).toBe(4);expect(before.invalid_terminal).toBe(0);
  return {preset,ref,original,before};
}
async function materialRead(page:Page,ref:Ref){
  const r=await http(()=>page.request.get(messages('material',ref.conversation_id)));expect(r.status()).toBe(200);
  return parsePage(await json(r),parseMessage).items.find(m=>m.message_id===ref.message_id)!;
}
async function openMaterialImage(page:Page,ref:Ref){
  const received=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===grantPath('material',ref));
  await row(page,ref.message_id).getByRole('button',{name:'Открыть изображение'}).click();expect((await received).status()).toBe(200);
  await loadedPrivateImage(row(page,ref.message_id).getByRole('img'));
}
function retainedMaterialHistory(before:Record<string,number|boolean|string>,after:Record<string,number|boolean|string>,terminals:number){
  for(const key of ['files','fetches','ready','winners','history_digest','files_digest','uploads_digest'])expect(after[key]).toBe(before[key]);
  expect(after.invalid_terminal).toBe(0);expect(Number(after.terminals)-Number(before.terminals)).toBe(terminals);
}
for(const label of ['replacement','text','delete']){
  test(`material PHOTO ${label}: loaded private image, same-ref caption, normal Worker mutation and grant refusal`,async({page})=>{
    test.setTimeout(90000);
    const {preset,ref,original,before}=await materialPhoto(page,label);await openMaterialImage(page,ref);
    expect(await worker(preset,`material-${label}-caption`)).toEqual({processed:1,replayed:0});await refresh(page);
    const caption=await materialRead(page,ref);expect(caption.version).toBe('2');expect(caption.text).toBe(original.text);expect(caption.file).toEqual(original.file);
    expect(caption.current).toEqual({schema_version:1,state:'VISIBLE',content_type:'PHOTO',text:`Material ${label} caption`,image_availability:'ORIGINAL_READY',changed:true});
    // Positive eligibility after a semantic version change and a second real GET.
    await openMaterialImage(page,ref);
    expect(await worker(preset,`material-${label}-change`)).toEqual({processed:1,replayed:0});await refresh(page);
    expect(await row(page,ref.message_id).getByRole('img').count()).toBe(0);
    await expect(row(page,ref.message_id).getByRole('button',{name:'Открыть изображение'})).toHaveCount(0);
    const changed=await materialRead(page,ref);expect(changed.version).toBe('3');expect(changed.text).toBe(original.text);expect(changed.content_type).toBe(original.content_type);expect(changed.file).toEqual(original.file);
    expect(changed.current).toEqual(label==='delete'
      ? {schema_version:1,state:'DELETED',content_type:null,text:null,image_availability:'HIDDEN',changed:true}
      : {schema_version:1,state:'VISIBLE',content_type:label==='text'?'TEXT':'PHOTO',text:label==='text'?'Material current text':'Material replacement change',image_availability:label==='text'?'NOT_APPLICABLE':'MEDIA_REPLACED_UNAVAILABLE',changed:true});
    if(label==='replacement')await expect(row(page,ref.message_id).getByText('Фото заменено, новое изображение недоступно.',{exact:true})).toBeVisible();
    const token=await csrf(page.request);const denied=await http(()=>page.request.post(grantPath(preset,ref),{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}));expect(denied.status()).toBe(404);
    retainedMaterialHistory(before,await helper(preset,'material-stats'),2);
    expect(await worker(preset,`material-${label}-change`)).toEqual({processed:0,replayed:1});expect(await materialRead(page,ref)).toEqual(changed);
    // Already issued signed URLs are TTL-limited capabilities. No assertion of
    // atomic URL revocation or realtime invalidation is made by this journey.
  });
}

test('material PHOTO delayed real old grant cannot restore image after semantic refresh',async({page})=>{
  test.setTimeout(90000);
  const {preset,ref,original,before}=await materialPhoto(page,'late');await openMaterialImage(page,ref);
  await refresh(page);expect(await row(page,ref.message_id).getByRole('img').count()).toBe(0);
  let release!:()=>void,observed!:(r:SafeResult<number>)=>void,finished!:(r:SafeResult<void>)=>void;
  const held=new Promise<void>(resolve=>{release=resolve;}),arrived=new Promise<SafeResult<number>>(resolve=>{observed=resolve;}),delivered=new Promise<SafeResult<void>>(resolve=>{finished=resolve;});
  let handled=false;
  await page.route(`**${grantPath(preset,ref)}`,async route=>{
    if(handled){await safeContinue(route);return;}handled=true;
    const actual=await safeDiagnostic('MESSAGING_ROUTE_FETCH_FAILED',()=>route.fetch());
    observed(actual.ok?{ok:true,value:actual.value.status()}:actual);
    await held;
    // Pass the unmodified real backend HTTP response. Only delivery order is
    // controlled; DTO, signed URL and backend decision are never fabricated.
    if(actual.ok)finished(await safeDiagnostic('MESSAGING_ROUTE_RELEASE_FAILED',()=>route.fulfill({response:actual.value})));
    else finished(actual);
  });
  try{
    const browserResponse=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===grantPath(preset,ref));
    await row(page,ref.message_id).getByRole('button',{name:'Открыть изображение'}).click();expect(requireSafeResult(await arrived)).toBe(200);
    expect(await worker(preset,'material-late-change')).toEqual({processed:1,replayed:0});await refresh(page);
    const current=await materialRead(page,ref);expect(current.version).toBe('2');expect(current.current.image_availability).toBe('MEDIA_REPLACED_UNAVAILABLE');expect(current.text).toBe(original.text);expect(current.file).toEqual(original.file);
    let oldImageRequests=0;const imageRequested=(request:{resourceType():string})=>{if(request.resourceType()==='image')oldImageRequests++;};page.on('request',imageRequested);
    release();requireSafeResult(await delivered);
    const received=await browserResponse;expect(received.status()).toBe(200);requireSafeResult(await safeDiagnostic('MESSAGING_BODY_FAILED',()=>received.finished()));
    // A browser task after the response lets fetch/React callbacks settle;
    // the condition is the real old response, not an arbitrary sleep.
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    expect(await row(page,ref.message_id).getByRole('img').count()).toBe(0);expect(oldImageRequests).toBe(0);page.off('request',imageRequested);
    await expect(row(page,ref.message_id).getByRole('button',{name:'Открыть изображение'})).toHaveCount(0);
    const token=await csrf(page.request);const denied=await http(()=>page.request.post(grantPath(preset,ref),{headers:{Origin:origin,'X-CSRF-Token':token},data:{}}));expect(denied.status()).toBe(404);
    retainedMaterialHistory(before,await helper(preset,'material-stats'),1);
  }finally{release();await page.unrouteAll({behavior:'wait'});}
});
