import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { type Bundle, parseActive, parseCommand, parseDraft } from '../src/configuration-api';

const fixtureFile=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!fixtureFile||!passwordFile)throw new Error('E2E_CONFIGURATION_PRIVATE_FIXTURES_REQUIRED');
let fixture:{workspace_id:string;business_id:string;messaging_fixtures:Record<string,{workspace_id:string;business_id:string;login:string}>};
try{fixture=JSON.parse(readFileSync(fixtureFile,'utf8'));}catch{throw new Error('E2E_CONFIGURATION_FIXTURE_JSON');}
const password=readFileSync(passwordFile,'utf8'),login=process.env.ASM_BROWSER_LOGIN??'browser.owner';
const base=`/api/v1/workspaces/${fixture.workspace_id}/businesses/${fixture.business_id}/configuration`;
const origin=process.env.ASM_BROWSER_BASE_URL??'http://127.0.0.1:8080';
function finiteChildFailure(error:unknown):string {
  const value=(typeof error==='object'&&error!==null?error:{}) as Record<string,unknown>;
  const exit=typeof value.code==='number'&&Number.isInteger(value.code)&&value.code>=-255&&value.code<=255?String(value.code):'UNKNOWN';
  const signal=value.signal===undefined||value.signal===null?'NONE':typeof value.signal==='string'&&['SIGTERM','SIGKILL','SIGINT'].includes(value.signal)?value.signal:'OTHER';
  const timeout=value.killed===true&&value.signal==='SIGTERM';
  const pattern=/^M2_4_BROWSER_DIAGNOSTIC:stage=(ARGS|TARGET|GUARD|SEED|INGEST|CLAIM_AI|CLAIM_WORK|EXECUTE_INBOX|EXECUTE_TURN|EXECUTE_AI|EXECUTE_SEND|MODEL|REPLAY|JOURNAL|DRAIN|CLEANUP);class=(MESSAGING|DATABASE|TIMEOUT|INPUT|IO|OTHER);code=(NONE|NOT_ALLOWED|STALE_CLAIM|AI_STALE|ACCESS_DENIED|INVALID_INPUT|IDEMPOTENCY_KEY_CONFLICT|OTHER);cleanup=(NONE|MESSAGING|DATABASE|TIMEOUT|INPUT|IO|OTHER);calls=(UNKNOWN|[0-9]{1,4});effects=(UNKNOWN|[0-9]{1,4});model_calls=(UNKNOWN|[0-2]);mismatch=[01]$/;
  const diagnostic=typeof value.stderr==='string'?value.stderr.split(/\r?\n/).find(line=>pattern.test(line)):undefined;
  return 'exit='+exit+';timeout='+String(timeout)+';signal='+signal+';'+(diagnostic??'diagnostic=UNAVAILABLE');
}
async function safe<T>(operation:()=>Promise<T>):Promise<T>{try{return await operation();}catch{throw new Error('E2E_CONFIGURATION_HTTP_FAILED');}}
async function read(request:APIRequestContext,kind:'draft'|'active',route=base){
  const r=await safe(()=>request.get(`${route}/${kind}`));expect(r.status()).toBe(200);const value=await safe(()=>r.json());return kind==='draft'?parseDraft(value):parseActive(value);
}
async function signIn(page:Page){await page.goto('/');await page.getByLabel('Логин').fill(login);await page.getByLabel('Пароль').fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByText('ACTIVE SESSION')).toBeVisible();if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==fixture.workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(fixture.workspace_id);}
async function csrf(request:APIRequestContext){const r=await safe(()=>request.get('/api/v1/auth/session'));expect(r.status()).toBe(200);return (await safe(()=>r.json()) as {csrf_token:string}).csrf_token;}
const synthetic=():Bundle=>({schema_version:1,communication_style:'NEUTRAL',services:[{id:'consultation',name:'Synthetic knowledge consultation',description:'Only synthetic consultation facts.',active:true,intake_fields:[],price:{mode:'OWNER_QUOTE',amount_minor:null,formula_note:null},duration:{mode:'FIXED',minutes:45,rule_note:null},deposit:{mode:'NONE',amount_minor:null,percent:null}}],rules:[{id:'min_age',service_id:null,kind:'MIN_AGE',value:18}],faqs:[{id:'preparation',service_id:'consultation',question:'Как подготовиться к консультации?',answer:'Возьмите синтетический эскиз.',source:'Synthetic owner handbook',confirmed:true,rule_ids:['min_age']}]});
async function prepare(page:Page){
  await signIn(page);const state=await read(page.request,'draft');if(!('draft_version'in state))throw new Error('E2E_CONFIGURATION_DRAFT_SHAPE');
  const token=await csrf(page.request);
  const r=await safe(()=>page.request.put(`${base}/draft`,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:{expected_draft_version:state.draft_version,bundle:synthetic()}}));expect(r.status()).toBe(200);parseCommand(await safe(()=>r.json()));
  await page.getByRole('button',{name:/Synthetic browser business/}).click();await expect(page.getByLabel('Название услуги 1')).toBeEnabled();
}

test('@narrow owner edits FAQ/rule, previews and publishes current active knowledge',async({page})=>{
  await prepare(page);const before=await read(page.request,'active');const answer=`Синтетическая консультация: возьмите эскиз ${randomUUID()}.`;
  let writes=0;page.on('request',request=>{if(new URL(request.url()).pathname.startsWith(base)&&['PUT','POST'].includes(request.method()))writes++;});
  await page.getByLabel('Ответ FAQ 1').fill(answer);await page.getByLabel('Значение правила 1').fill('21');await page.getByRole('button',{name:'Сохранить черновик'}).click();await expect(page.getByText('Команда подтверждена. Текущее состояние получено.')).toBeVisible();
  const draft=await read(page.request,'draft');expect('draft_version'in draft).toBe(true);if(!('draft_version'in draft))throw new Error('E2E_CONFIGURATION_DRAFT_SHAPE');expect(draft.bundle?.faqs[0].answer===answer&&draft.bundle.rules[0].value===21).toBe(true);
  const stillActive=await read(page.request,'active');expect(stillActive.release_id===before.release_id&&stillActive.activation_version===before.activation_version).toBe(true);
  const writesBeforePreview=writes;await page.getByRole('button',{name:'Проверить и показать предпросмотр'}).click();await expect(page.getByRole('button',{name:'Опубликовать черновик'})).toBeEnabled();expect(writes).toBe(writesBeforePreview);
  await page.getByRole('button',{name:'Опубликовать черновик'}).click();await expect(page.getByRole('region',{name:'Опубликованные сведения'}).getByText(answer,{exact:true})).toBeVisible();
  const after=await read(page.request,'active');expect(after.release_id!==before.release_id&&BigInt(after.activation_version)===BigInt(before.activation_version)+1n&&after.bundle?.faqs[0].answer===answer&&after.bundle.rules[0].value===21).toBe(true);
  expect(writes).toBe(2);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.getByRole('region',{name:'Настройки бизнеса'})).toHaveCount(0);
});

test('lost owner edit acknowledgement replays exact body/key; CSRF denial leaves publication unchanged',async({page})=>{
  await prepare(page);const before=await read(page.request,'active');let attempts=0,firstBody:string|null=null,firstKey:string|undefined,identical=false;
  await page.route(`**${base}/draft`,async route=>{
    if(route.request().method()!=='PUT'){await route.continue();return;}
    attempts++;const body=route.request().postData(),key=route.request().headers()['idempotency-key'];
    if(attempts===1){firstBody=body;firstKey=key;const response=await safe(()=>route.fetch());expect(response.status()).toBe(200);await safe(()=>route.abort('failed'));}
    else{identical=body===firstBody&&key===firstKey;await safe(()=>route.continue());}
  });
  try{
    await page.getByLabel('Ответ FAQ 1').fill('Synthetic committed edit with lost acknowledgement.');await page.getByRole('button',{name:'Сохранить черновик'}).click();await expect(page.getByRole('button',{name:'Повторить исходную команду'})).toBeVisible();await expect(page.getByLabel('Ответ FAQ 1')).toBeDisabled();
    await page.getByRole('button',{name:'Повторить исходную команду'}).click();await expect(page.getByText('Команда подтверждена. Текущее состояние получено.')).toBeVisible();expect(attempts===2&&identical).toBe(true);
    const after=await read(page.request,'active');expect(after.release_id===before.release_id&&after.activation_version===before.activation_version).toBe(true);
    const current=await read(page.request,'draft');if(!('draft_version'in current))throw new Error('E2E_CONFIGURATION_DRAFT_SHAPE');const rejected=await safe(()=>page.request.post(`${base}/publish`,{headers:{Origin:origin,'X-CSRF-Token':'not-the-session-csrf','Idempotency-Key':randomUUID()},data:{expected_draft_version:current.draft_version,expected_activation_version:after.activation_version}}));expect(rejected.status()).toBe(403);const actual=await read(page.request,'active');expect(actual.release_id===after.release_id&&actual.activation_version===after.activation_version).toBe(true);
  }finally{await page.unrouteAll({behavior:'wait'});firstBody=null;firstKey=undefined;}
});



test('published knowledge reaches one guarded fake runtime reply; draft and replay cannot add effects',async({page})=>{
  test.setTimeout(60000);
  const envPath=process.env.ASM_BROWSER_ENV_FILE,counterDir=process.env.ASM_BROWSER_COUNTER_DIR,inventoryFile=process.env.ASM_BROWSER_MESSAGING_FILE;
  if(!envPath||!counterDir||!inventoryFile||!fixture.messaging_fixtures.knowledge)throw new Error('E2E_CONFIGURATION_RUNTIME_FIXTURE_REQUIRED');
  let inventory:{knowledge:{conversation_id:string}};try{inventory=JSON.parse(readFileSync(inventoryFile,'utf8'));}catch{throw new Error('E2E_CONFIGURATION_RUNTIME_INVENTORY');}
  const knowledge=fixture.messaging_fixtures.knowledge;
  const knowledgeBase=`/api/v1/workspaces/${knowledge.workspace_id}/businesses/${knowledge.business_id}/configuration`;
  const answer='Synthetic published knowledge answer.',source='Synthetic owner handbook';
  await page.goto('/');await page.getByLabel('Логин').fill(knowledge.login);await page.getByLabel('Пароль').fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
  if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==knowledge.workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(knowledge.workspace_id);await page.getByRole('button',{name:/Synthetic business/}).click();
  const settings=page.getByRole('region',{name:'Настройки бизнеса',exact:true});await expect(settings.getByRole('button',{name:'Добавить услугу'})).toBeEnabled();
  // All business facts in this journey are entered through the actual owner UI.
  await settings.getByRole('button',{name:'Добавить услугу'}).click();await settings.getByLabel('Название услуги 1').fill('Synthetic knowledge consultation');await settings.getByLabel('Описание услуги 1').fill('Only synthetic consultation facts.');
  await settings.getByRole('button',{name:'Добавить правило'}).click();await settings.getByLabel('Значение правила 1').fill('21');
  await settings.getByRole('button',{name:'Добавить FAQ'}).click();await settings.getByLabel('Вопрос FAQ 1').fill('Как подготовиться к консультации?');await settings.getByLabel('Ответ FAQ 1').fill(answer);await settings.getByLabel('Источник FAQ 1').fill(source);await settings.getByLabel('Владелец подтвердил FAQ 1').check();
  await settings.getByRole('button',{name:'Сохранить черновик'}).click();await expect(settings.getByText('Команда подтверждена. Текущее состояние получено.')).toBeVisible();await settings.getByRole('button',{name:'Проверить и показать предпросмотр'}).click();await expect(settings.getByRole('button',{name:'Опубликовать черновик'})).toBeEnabled();
  await settings.getByRole('button',{name:'Опубликовать черновик'}).click();await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByText(answer,{exact:true})).toBeVisible();
  const publication=await read(page.request,'active',knowledgeBase);expect(publication.bundle?.faqs[0].answer===answer&&publication.bundle.rules[0].value===21).toBe(true);
  // A subsequent draft edit deliberately differs from the immutable active bundle.
  await settings.getByLabel('Ответ FAQ 1').fill('Synthetic DRAFT must stay private.');await settings.getByRole('button',{name:'Сохранить черновик'}).click();await expect(settings.getByLabel('Ответ FAQ 1')).toBeEnabled();
  const unchanged=await read(page.request,'active',knowledgeBase);expect(unchanged.release_id===publication.release_id&&unchanged.activation_version===publication.activation_version&&unchanged.bundle?.faqs[0].answer===answer).toBe(true);
  const inbox=page.getByRole('region',{name:'Переписка',exact:true});await expect(page.getByTestId(`conversation-${inventory.knowledge.conversation_id}`)).toBeVisible();await page.getByTestId(`conversation-${inventory.knowledge.conversation_id}`).click();
  const control=page.getByRole('region',{name:'Управление диалогом',exact:true});await expect(control.getByRole('button',{name:'Разрешить автоматику',exact:true})).toBeEnabled();
  const resumed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`/api/v1/workspaces/${knowledge.workspace_id}/conversations/${inventory.knowledge.conversation_id}/resume`);await control.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();expect((await resumed).status()).toBe(200);await expect(control.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
  async function runKnowledge():Promise<Record<string,unknown>>{
    const args=['compose','--env-file',envPath!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'-v',`${counterDir}:/run/m2-browser-counters:rw`,'browser-runtime','python','scripts/m2_4_browser_worker.py','--preset','knowledge','--action','knowledge-answer'];
    let stdout:string;try{stdout=(await promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:65536})).stdout;}catch(error){throw new Error('E2E_CONFIGURATION_RUNTIME_FAILED:'+finiteChildFailure(error));}
    try{return JSON.parse(stdout);}catch{throw new Error('E2E_CONFIGURATION_RUNTIME_OUTPUT');}
  }
  const delivered=await runKnowledge();expect([delivered.model_calls,delivered.calls,delivered.effects]).toEqual([1,1,1]);expect(delivered.release_id===publication.release_id&&delivered.activation_version===publication.activation_version&&delivered.answer===answer&&delivered.source===source).toBe(true);
  await inbox.getByRole('button',{name:'Обновить сообщения',exact:true}).click();await expect(inbox.getByText(answer,{exact:true})).toHaveCount(1);await expect(inbox.getByText('Synthetic DRAFT must stay private.',{exact:true})).toHaveCount(0);
  const replayed=await runKnowledge();expect(replayed.replayed).toBe(true);expect([replayed.model_calls,replayed.calls,replayed.effects]).toEqual([1,1,1]);expect(replayed.release_id===delivered.release_id&&replayed.activation_version===delivered.activation_version).toBe(true);
});
