import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { type Bundle, parseActive, parseCommand, parseDraft, parseKnowledgeState } from '../src/configuration-api';

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

// Restore only the legacy publication captured by this synthetic journey.
// The real OWNER rollback capability enforces eligibility and a fresh CAS.
async function restoreLegacyPublication(page:Page,release:string|null){
  if(!release||page.isClosed())return;
  const active=await read(page.request,'active');if(active.release_id===release)return;
  const token=await csrf(page.request);
  const response=await safe(()=>page.request.post(`${base}/rollback`,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:{expected_activation_version:active.activation_version,release_id:release}}));
  expect(response.status()).toBe(200);parseCommand(await safe(()=>response.json()));
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
  expect(writes).toBe(2);
  await page.getByLabel('Владелец подтвердил FAQ 1').uncheck();
  await page.getByRole('button',{name:'Сохранить черновик'}).click();
  await expect(page.getByLabel('Владелец подтвердил FAQ 1')).toBeEnabled();
  await page.getByRole('button',{name:'Проверить и показать предпросмотр'}).click();
  await expect(page.getByText('Публикация заблокирована ошибками.',{exact:true})).toBeVisible();
  await expect(page.getByText(/ERROR — ошибка.*Укажите источник FAQ и подтвердите сведения/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
  expect(writes).toBe(3);
  expect(await read(page.request,'active')).toEqual(after);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
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


test('@narrow owner reviews sources, preserves exact uncertain intent, publishes a ready build and revokes',async({page})=>{
  test.setTimeout(60000);
  await prepare(page);
  const settings=page.getByRole('region',{name:'Настройки бизнеса',exact:true});
  // Establish a real prior publication through the existing owner button.
  await settings.getByRole('button',{name:'Опубликовать черновик',exact:true}).click();
  await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByText('Возьмите синтетический эскиз.',{exact:true})).toBeVisible();
  const previous=await read(page.request,'active');
  const knowledgeBase=base.replace(/\/configuration$/,'/knowledge');
  const state=async()=>{const r=await safe(()=>page.request.get(knowledgeBase));expect(r.status()).toBe(200);return parseKnowledgeState(await safe(()=>r.json()));};
  const before=await state();
  await settings.getByRole('button',{name:'Посмотреть источники',exact:true}).click();
  await expect(settings.getByRole('textbox',{name:'Текст источника',exact:true})).toBeEnabled();
  const title='Synthetic source '+randomUUID(),canonical='Синтетическая памятка: возьмите эскиз. <b>Это текст.</b>';
  let attempts=0,firstBody:string|null=null,firstKey:string|undefined,identical=false,finished=false;
  await page.route(`**${knowledgeBase}/sources`,async route=>{
    if(route.request().method()!=='POST'){await route.continue();return;}
    attempts++;const body=route.request().postData(),key=route.request().headers()['idempotency-key'];
    if(attempts===1){firstBody=body;firstKey=key;const r=await safe(()=>route.fetch());expect(r.status()).toBe(200);await safe(()=>route.abort('failed'));}
    else{identical=body===firstBody&&key===firstKey;await safe(()=>route.continue());}
  });
  try{
    await settings.getByLabel('Заголовок источника',{exact:true}).fill(title);
    await settings.getByRole('combobox',{name:'Формат источника',exact:true}).selectOption('MARKDOWN');
    await settings.getByRole('textbox',{name:'Текст источника',exact:true}).fill('  '+canonical+'  ');
    await settings.getByRole('button',{name:'Сохранить источник',exact:true}).click();
    await expect(settings.getByRole('button',{name:'Повторить исходную команду',exact:true})).toBeVisible();
    await expect(settings.getByRole('textbox',{name:'Текст источника',exact:true})).toBeDisabled();
    await settings.getByRole('button',{name:'Повторить исходную команду',exact:true}).click();
    const source=settings.getByRole('article',{name:`Источник: ${title}`,exact:true});
    await expect(source.getByText(canonical,{exact:true})).toBeVisible();
    expect(attempts===2&&identical).toBe(true);
    const saved=await state();expect(saved.sources.length===before.sources.length+1&&saved.sources.filter(s=>s.head.title===title).length===1).toBe(true);
    expect((await read(page.request,'active')).release_id===previous.release_id).toBe(true);
    await source.getByRole('button',{name:'Подтвердить источник',exact:true}).click();
    await expect(source.getByRole('heading',{name:`${title} · Подтверждён`,exact:true})).toBeVisible();
    const confirmed=await state();const own=confirmed.sources.find(s=>s.head.title===title)!;
    expect(own.head.confirmed&&own.head.canonical_text===canonical&&own.preview.chunks.length===1).toBe(true);
    await settings.getByRole('button',{name:'Подготовить поиск',exact:true}).click();
    if(confirmed.embedding_mode==='CONTROLLED'){
      await expect(settings.getByText(/Поиск готов к публикации/).first()).toBeVisible();
      await expect.poll(async()=>{const value=await state();return value.builds.find(b=>b.revision_ids.includes(own.head.revision_id))?.state;}).toBe('READY');
      await settings.getByRole('button',{name:'Опубликовать источники',exact:true}).click();
      await expect(settings.getByText('Опубликованный поиск подключён к текущим настройкам.',{exact:true})).toBeVisible();
      const published=await state();expect(published.active_build_id!==null&&published.release_id!==previous.release_id).toBe(true);
      expect(published.builds.some(b=>b.build_id===published.active_build_id&&b.revision_ids.includes(own.head.revision_id)&&b.state==='READY')).toBe(true);
    }else{
      await expect(settings.getByText(/Ошибка индексации.*Индексация отключена/).first()).toBeVisible();
      await expect.poll(async()=>{const value=await state();return value.builds.find(b=>b.revision_ids.includes(own.head.revision_id))?.state;}).toBe('ERROR');
      await expect(settings.getByRole('button',{name:'Опубликовать источники',exact:true})).toBeDisabled();
      const unchanged=await read(page.request,'active');expect(unchanged.release_id===previous.release_id&&unchanged.activation_version===previous.activation_version).toBe(true);
    }
    await source.getByRole('button',{name:'Отозвать источник',exact:true}).click();
    await expect(source.getByRole('heading',{name:`${title} · Отозван`,exact:true})).toBeVisible();
    const revoked=await state();expect(revoked.sources.find(s=>s.source_id===own.source_id)?.head.confirmed).toBe(false);
    await source.getByRole('button',{name:'Удалить источник',exact:true}).click();
    await source.getByRole('button',{name:'Удалить текст и индекс',exact:true}).click();
    await expect(source).toHaveCount(0);
    expect((await state()).sources.some(s=>s.source_id===own.source_id)).toBe(false);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);finished=true;
  }finally{firstBody=null;firstKey=undefined;try{if(!page.isClosed()){await page.unrouteAll({behavior:'wait'});await restoreLegacyPublication(page,previous.release_id);}}catch(error){if(finished)throw error;}}
});


test('@narrow owner retains a linked build after reload and explicitly publishes without the last source',async({page})=>{
  test.setTimeout(60000);
  await prepare(page);
  const settings=page.getByRole('region',{name:'Настройки бизнеса',exact:true});
  await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeEnabled();
  await settings.getByRole('button',{name:'Опубликовать черновик',exact:true}).click();
  await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByText('Возьмите синтетический эскиз.',{exact:true})).toBeVisible();
  const baseline=await read(page.request,'active');
  const knowledgeBase=base.replace(/\/configuration$/,'/knowledge');
  const state=async()=>{const r=await safe(()=>page.request.get(knowledgeBase));expect(r.status()).toBe(200);return parseKnowledgeState(await safe(()=>r.json()));};
  const initial=await state();expect(initial.active_build_id).toBeNull();expect(initial.sources.filter(s=>s.state==='CONFIRMED')).toHaveLength(0);
  let finished=false;const createdSourceIds:string[]=[];
  async function open(){await settings.getByRole('button',{name:'Посмотреть источники',exact:true}).click();await expect(settings.getByRole('textbox',{name:'Текст источника',exact:true})).toBeEnabled();}
  async function makeEmpty(){
    await settings.getByRole('button',{name:'Подготовить пустой набор',exact:true}).click();
    await expect(settings.getByRole('button',{name:'Опубликовать настройки без источников',exact:true})).toBeEnabled();
    const value=await state(),id=await settings.getByRole('combobox',{name:'Готовый набор источников',exact:true}).inputValue();
    const empty=value.builds.find(b=>b.build_id===id)!;
    expect(empty).toMatchObject({state:'READY',revision_ids:[],chunk_count:0,calls_reserved:0,calls_completed:0});
    return empty;
  }
  try{
    await open();
    // Default CI remains DISABLED. A real empty build also exercises linked
    // publication there; the LOCAL CONTROLLED journey publishes nonempty text.
    if(initial.embedding_mode==='DISABLED'){
      await makeEmpty();await settings.getByRole('button',{name:'Опубликовать настройки без источников',exact:true}).click();
      await expect(settings.getByText('Настройки опубликованы без источников для поиска.',{exact:true})).toBeVisible();
    }
    for(const withdrawal of ['revoke','delete'] as const){
      const title=`Synthetic publication ${withdrawal} ${randomUUID()}`;
      await settings.getByRole('textbox',{name:'Заголовок источника',exact:true}).fill(title);
      await settings.getByRole('textbox',{name:'Текст источника',exact:true}).fill(`Synthetic ${withdrawal} source. Only owner-confirmed explanation.`);
      await settings.getByRole('button',{name:'Сохранить источник',exact:true}).click();
      const card=settings.getByRole('article',{name:`Источник: ${title}`,exact:true});
      await card.getByRole('button',{name:'Подтвердить источник',exact:true}).click();
      await expect(card.getByRole('heading',{name:`${title} · Подтверждён`,exact:true})).toBeVisible();
      const confirmed=await state(),own=confirmed.sources.find(s=>s.head.title===title)!;createdSourceIds.push(own.source_id);
      if(initial.embedding_mode==='CONTROLLED'){
        await settings.getByRole('button',{name:'Подготовить поиск',exact:true}).click();
        await expect(settings.getByRole('button',{name:'Опубликовать источники',exact:true})).toBeEnabled();
        await settings.getByRole('button',{name:'Опубликовать источники',exact:true}).click();
        await expect.poll(async()=>{const v=await state();return v.builds.find(b=>b.build_id===v.active_build_id)?.revision_ids.includes(own.head.revision_id);}).toBe(true);
      }
      if(withdrawal==='revoke'){
        const linked=await state();expect(linked.active_build_id).not.toBeNull();
        await page.reload();await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
        if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==fixture.workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(fixture.workspace_id);
        await page.getByRole('button',{name:/Synthetic browser business/}).click();await expect(settings.getByLabel('Название услуги 1')).toBeEnabled();
        await expect(settings.getByRole('textbox',{name:'Текст источника',exact:true})).toHaveCount(0);
        await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeDisabled();
        await settings.getByRole('combobox',{name:'Стиль общения',exact:true}).selectOption('WARM');
        await settings.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await expect(settings.getByRole('button',{name:'Сохранить черновик',exact:true})).toBeDisabled();
        await expect(settings.getByRole('textbox',{name:'Текст источника',exact:true})).toHaveCount(0);
        await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeDisabled();
        await settings.getByRole('button',{name:'Выбрать набор для публикации',exact:true}).click();
        await expect(settings.getByRole('combobox',{name:'Готовый набор источников',exact:true})).toHaveValue(linked.active_build_id!);
        await settings.getByRole('button',{name:initial.embedding_mode==='CONTROLLED'?'Опубликовать источники':'Опубликовать настройки без источников',exact:true}).click();
        await expect.poll(async()=>{const v=await state();return v.release_id!==linked.release_id&&v.active_build_id===linked.active_build_id;}).toBe(true);
        const config=await read(page.request,'active');expect(config.bundle?.communication_style).toBe('WARM');
      }
      await card.getByRole('button',{name:withdrawal==='revoke'?'Отозвать источник':'Удалить источник',exact:true}).click();
      if(withdrawal==='delete')await card.getByRole('button',{name:'Удалить текст и индекс',exact:true}).click();
      await expect(settings.getByRole('button',{name:'Подготовить пустой набор',exact:true})).toBeEnabled();
      const withdrawn=await state();expect(withdrawn.sources.some(s=>s.source_id===own.source_id&&s.head.confirmed)).toBe(false);
      await settings.getByRole('combobox',{name:'Стиль общения',exact:true}).selectOption(withdrawal==='revoke'?'CONCISE':'NEUTRAL');
      await settings.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await expect(settings.getByRole('button',{name:'Сохранить черновик',exact:true})).toBeDisabled();
      const empty=await makeEmpty();
      await settings.getByRole('button',{name:'Опубликовать настройки без источников',exact:true}).click();
      await expect(settings.getByText('Настройки опубликованы без источников для поиска.',{exact:true})).toBeVisible();
      const published=await state(),config=await read(page.request,'active');
      expect(published.active_build_id).toBe(empty.build_id);expect(published.release_id).not.toBe(withdrawn.release_id);
      expect(config.bundle?.communication_style).toBe(withdrawal==='revoke'?'CONCISE':'NEUTRAL');
      expect(published.builds.find(b=>b.build_id===published.active_build_id)).toMatchObject({revision_ids:[],chunk_count:0,calls_reserved:0,calls_completed:0});
      await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeDisabled();
      if(withdrawal==='revoke'){
        await card.getByRole('button',{name:'Удалить источник',exact:true}).click();await card.getByRole('button',{name:'Удалить текст и индекс',exact:true}).click();await expect(card).toHaveCount(0);
      }
    }
    expect((await state()).sources).toHaveLength(initial.sources.length);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);finished=true;
  }finally{try{
    for(const id of createdSourceIds){
      const value=await state(),own=value.sources.find(s=>s.source_id===id);if(!own)continue;
      const token=await csrf(page.request);
      const response=await safe(()=>page.request.post(`${knowledgeBase}/sources/${id}/delete`,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:{schema_version:1,expected_source_version:own.source_version,expected_activation_version:value.activation_version}}));
      expect(response.status()).toBe(200);
    }
    await restoreLegacyPublication(page,baseline.release_id);
  }catch(error){if(finished)throw error;}}
});
