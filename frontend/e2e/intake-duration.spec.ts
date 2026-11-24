import {expect,test,type Locator,type Page,type Request,type Route} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createInterface} from 'node:readline';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import type {ApprovalBody,ApprovalCard} from '../src/escalation-api';
import type {Availability} from '../src/scheduling-api';
import {parseReceipt} from '../src/messaging-api';
import type {DraftCommand,DraftListItem,DraftRevisionCommand,Intake,PriceCalculation,PriceHistory,QuoteDelivery,RequestQuote,ServiceAssessment,ServiceRequestDraft} from '../src/intake-api';

const fixtureFile=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!fixtureFile||!passwordFile)throw new Error('E2E_INTAKE_PRIVATE_FIXTURES_REQUIRED');
const fixture=JSON.parse(readFileSync(fixtureFile,'utf8')) as {messaging_fixtures:{knowledge:{login:string;workspace_id:string;business_id:string;user_account_id:string}}};
const password=readFileSync(passwordFile,'utf8'),owner=fixture.messaging_fixtures.knowledge;

type Viewport='desktop'|'narrow';
type IntakeOperation='seed'|'collect'|'collect-sized'|'complex'|'ambiguous'|'second'|'late-size'|'late-cover-up'|'complex-message'|'assess-first'|'assess-second'|'price-first'|'price-second'|'price-size'|'price-oversize'|'quote-second'|'agent-first'|'agent-start-second'|'agent-second'|'agent-exclude-first'|'agent-correct-first'|'agent-same-title';
type QuoteOperation='deliver-quote'|'lose-quote-ack';
type QuoteReply='agree-quote'|'repeat-agreement'|'ambiguous-agreement'|'decline-quote';
type FixtureOperation=IntakeOperation|QuoteOperation|QuoteReply|'page-reply-history'|'pilot-cover-up'|'deliver-pilot-question';
type QuoteReplyResult={outcome:string|null;message_id:string;source_message_id:string|null;quote_id:string|null;acceptance_id:string|null;order_id:string|null;session_id:string|null};
type DispatchCheckpoint={phase:'before_call'|'before_finalize';calls:number;effects:number};
type QuoteIntakeJourney='quote-delivery'|'quote-guard'|'quote-acceptance'|'quote-clarification'|'quote-agent'|'quote-pilot';
type IntakeJourney='intake'|'request'|'request-deferred'|'assessment'|'assessment-complex'|'assessment-complex-source'|'pricing'|'owner-decision'|'owner-decision-partial'|'owner-source-other'|'pilot-complex'|QuoteIntakeJourney;

function intakeChildFailure(error:unknown,operation:FixtureOperation,journey:IntakeJourney,variant:Viewport):Error {
 const result=error as {code?:unknown;stderr?:unknown;killed?:boolean;signal?:string};
 const exit=typeof result.code==='number'?String(result.code):'UNKNOWN';
 const request=`operation=${operation};journey=${journey};variant=${variant}`;
 const prefix=`M5_INTAKE_BROWSER_REFUSED:${request};`;
 const pattern=/^stage=(TARGET|GUARD|CONFIGURATION|MODEL_SETUP|INGEST|CLAIM|EXECUTE|OWNER_READ|REPLAY|EFFECTS);reason=[A-Z][A-Z0-9_]{0,63}(;job_kind=(NONE|PROCESS_INBOX|PROCESS_TURN|SEND_AI_TEXT|SEND_QUOTE_TEXT|ESCALATION_TIMER|SEND_MANUAL_TEXT|SEND_GUARDED_TEXT|SEND_AI_PHOTO|FETCH_IMAGE);matches_expected=(true|false))?$/;
 const diagnostic=typeof result.stderr==='string'?result.stderr.split(/\r?\n/)
  .find(line=>line.startsWith(prefix)&&pattern.test(line.slice(prefix.length))):undefined;
 const timeout=result.killed===true&&result.signal==='SIGTERM';
 return new Error(`E2E_INTAKE_RUNTIME_REFUSED:exit=${exit};${request};${diagnostic?.slice(prefix.length)??`diagnostic=UNAVAILABLE;timeout=${timeout}`}`);
}

async function openWorkspace(page:Page){
 await expect(page.getByText('ACTIVE SESSION',{exact:true})).toBeVisible();
 const workspace=page.getByLabel('Workspace',{exact:true});
 if(await workspace.inputValue()!==owner.workspace_id)await workspace.selectOption(owner.workspace_id);
}

async function openConversation(page:Page,conversation:string){
 const inbox=page.getByRole('region',{name:'Переписка',exact:true});
 await inbox.getByRole('button',{name:'Обновить диалоги',exact:true}).click();
 await page.getByTestId(`conversation-${conversation}`).click();
 return inbox;
}

async function refreshIntake(inbox:Locator,intake:Locator){
 await inbox.getByRole('button',{name:'Обновить сообщения',exact:true}).click();
 await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();
}

async function configureIntakeService(page:Page,variant:Viewport){
 const serviceName='Synthetic intake consultation '+variant+' '+randomUUID();
 await page.goto('/');await page.getByLabel('Логин',{exact:true}).fill(owner.login);await page.getByLabel('Пароль',{exact:true}).fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await openWorkspace(page);
 await page.getByRole('button',{name:/Synthetic business/}).click();
 const settings=page.getByRole('region',{name:'Настройки бизнеса',exact:true});
 await expect(settings.getByRole('button',{name:'Добавить услугу',exact:true})).toBeEnabled();
 if(await settings.getByLabel('Название услуги 1',{exact:true}).count()===0)await settings.getByRole('button',{name:'Добавить услугу',exact:true}).click();
 await settings.getByLabel('Название услуги 1',{exact:true}).fill(serviceName);const description=settings.getByLabel('Описание услуги 1');await expect(description).toHaveCount(1);await description.fill('Synthetic browser template '+variant+', owner review required.');
 await settings.getByRole('button',{name:'Применить шаблон новой татуировки v1',exact:true}).first().click();
 return {settings,serviceName};
}

async function publishIntakeService(settings:Locator,serviceName:string){
 await settings.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await expect(settings.getByText('Команда подтверждена. Текущее состояние получено.',{exact:true})).toBeVisible();
 await settings.getByRole('button',{name:'Проверить и показать предпросмотр',exact:true}).click();await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeEnabled();await settings.getByRole('button',{name:'Опубликовать черновик',exact:true}).click();await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByRole('heading',{name:serviceName+' · Активна',exact:true})).toBeVisible();
}

async function beginIntake(page:Page,variant:Viewport,journey:IntakeJourney){
 const {settings,serviceName}=await configureIntakeService(page,variant);
 await publishIntakeService(settings,serviceName);
 return {...await collectIntake(page,variant,journey),serviceName};
}

async function intakeFixture<T>(operation:FixtureOperation,journey:IntakeJourney,variant:Viewport,conversation?:string,targetId?:string,observe?: (checkpoint:DispatchCheckpoint)=>Promise<void>):Promise<T>{
 const envFile=process.env.ASM_BROWSER_ENV_FILE;
 if(!envFile||!owner?.user_account_id)throw new Error('E2E_INTAKE_TEST_RUNTIME_REQUIRED');
 const args=['compose','--env-file',envFile,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-runtime','python','scripts/m5_intake_fixture.py','--variant',variant,'--journey',journey,'--operation',operation,'--actor',owner.user_account_id,'--workspace',owner.workspace_id,'--business',owner.business_id,
  ...(conversation?['--conversation',conversation]:[]),...(targetId?[operation==='deliver-pilot-question'?'--receipt-key':'--request',targetId]:[]),...(observe?['--observe-dispatch']:[])];
 const child=promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:16384});
 const completed=child.then(result=>({stdout:result.stdout}),error=>({error:intakeChildFailure(error,operation,journey,variant)}));
 let checkpoints=0;
 if(observe){
  const stream=createInterface({input:child.child.stdout!,crlfDelay:Infinity});
  try{
   for await(const line of stream){
    const message=JSON.parse(line);
    if(!Object.hasOwn(message,'phase'))continue;
    const phase=(['before_call','before_finalize'] as const)[checkpoints++];
    expect(message.phase).toBe(phase);
    await observe(message as DispatchCheckpoint);
    child.child.stdin!.write('continue\n');
   }
  }finally{
   stream.close();
   child.child.stdin?.end();
   await completed;
  }
 }
 const result=await completed;
 if('error' in result)throw result.error;
 if(observe)expect(checkpoints).toBe(2);
 return JSON.parse(observe?result.stdout.trim().split('\n').at(-1)!:result.stdout) as T;
}

async function removeHistoricalDuration(quoteId:string){
 const envFile=process.env.ASM_BROWSER_ENV_FILE;
 if(!envFile||!owner?.workspace_id)throw new Error('E2E_INTAKE_TEST_RUNTIME_REQUIRED');
 const fixture=`
import asyncio
import sys
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine

sys.path[:0] = ["scripts", "tests"]
from m1_3_browser_fixture import guard, target
from m7_scheduling_fixtures import remove_historical_duration

async def run():
    engine = create_async_engine(target(), hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with engine.begin() as connection:
            await guard(connection)
            await remove_historical_duration(connection, UUID(sys.argv[1]), UUID(sys.argv[2]))
    finally:
        await engine.dispose()

asyncio.run(run())
`;
 const args=['compose','--env-file',envFile,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser',
  'run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-provision',
  'python','-c',fixture,owner.workspace_id,quoteId];
 try{
  await promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:16384});
 }catch{
  throw new Error('E2E_M7_HISTORICAL_DURATION_FIXTURE_FAILED');
 }
}

async function collectIntake(page:Page,variant:Viewport,journey:IntakeJourney){
 const input=(operation:IntakeOperation,conversation?:string,fixtureJourney=journey)=>
  intakeFixture<{conversation_id:string;message_id:string;model_calls:number;calls:number;effects:number;status:string;
   service_intents?:{request_id:string;approval_id:string|null;quote_id:string|null}}>(operation,fixtureJourney,variant,conversation);
 const seed=await input('seed');expect([seed.model_calls,seed.calls,seed.effects]).toEqual([0,0,0]);
 const inbox=await openConversation(page,seed.conversation_id);
 const control=page.getByRole('region',{name:'Управление диалогом',exact:true});await expect(control.getByRole('button',{name:'Разрешить автоматику',exact:true})).toBeEnabled();await control.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();await expect(control.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
 const assessment=journey.startsWith('assessment');
 const pricing=journey==='pricing'||journey.startsWith('owner-decision')||journey.startsWith('quote-');
 const agent=journey==='quote-agent'||journey==='quote-pilot';
 const operation=agent?'agent-first':journey==='intake'?'collect':pricing?'price-first':assessment?'assess-first':'collect-sized';
 const collected=await input(operation,seed.conversation_id);
 expect([collected.model_calls,collected.calls,collected.effects,collected.status]).toEqual([1,agent?0:1,agent?0:1,assessment||pricing?'PRELIMINARILY_COMPLETE':'CLARIFY']);
 const intake=page.getByRole('region',{name:'Предварительный запрос',exact:true});
 await refreshIntake(inbox,intake);
 await expect(intake.getByLabel('Идея',{exact:true})).toHaveValue(agent?'роза':'flower');
 if(journey!=='intake')await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue(agent?'20 мм':pricing?'20 mm':'8 cm');
 else await expect(intake.getByText('Какой примерный размер вы представляете, в сантиметрах?',{exact:true})).toBeVisible();
 return {input,conversation:seed.conversation_id,collected,intake,inbox};
}

test('@narrow source-backed intake, owner field confirmation, Action Center and measured owner case',async({page},info)=>{
 test.setTimeout(90000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {input,conversation,intake}=await beginIntake(page,variant,'intake');
 const source=intake.getByRole('link',{name:'сообщение клиента',exact:true}).first();const anchor=await source.getAttribute('href');expect(anchor).toMatch(/^#message-[0-9a-f-]+$/);await source.click();await expect(page.locator(anchor!)).toContainText('Synthetic intake flower forearm');
 const readCases=page.waitForResponse(response=>response.request().method()==='GET'&&new URL(response.url()).pathname.endsWith('/intake/duration-cases'));
 await page.getByRole('button',{name:'Открыть примеры длительности',exact:true}).click();const cases=page.getByRole('region',{name:'Примеры длительности',exact:true});
 expect((await readCases).status()).toBe(200);
 await expect(cases.getByLabel('Описание работы',{exact:true})).toBeEnabled();
 await cases.getByLabel('Описание работы',{exact:true}).fill('Synthetic owner flower '+variant);await cases.getByLabel('Место',{exact:true}).fill('forearm');await cases.getByLabel('Рабочее время, мин',{exact:true}).fill('35');await cases.getByRole('button',{name:'Создать пример',exact:true}).click();
 const example=cases.locator('article').filter({has:page.getByRole('heading',{name:'Synthetic owner flower '+variant,exact:true})}).first();await expect(example.getByText('Работа: 35 · занято: неизвестно мин',{exact:true})).toBeVisible();await example.getByRole('button',{name:'Подтвердить пример',exact:true}).click();await expect(example.getByText(/Подтверждено · версия 2/)).toBeVisible();
 await intake.getByRole('button',{name:'Сравнить с примерами мастера',exact:true}).click();await expect(intake.getByRole('heading',{name:'Synthetic owner flower '+variant,exact:true})).toBeVisible();await expect(intake.getByText(/Рабочее время: 35, занятое: неизвестно/).first()).toBeVisible();
 const complex=await input('complex',conversation);expect([complex.model_calls,complex.calls,complex.effects,complex.status]).toEqual([1,0,0,'OWNER_HANDOFF']);
 const center=page.getByRole('region',{name:'Запросы владельцу',exact:true});
 await center.getByRole('button',{name:'Обновить очередь',exact:true}).click();
 const pending=center.getByRole('button',{name:/Требуется решение владельца/}).first();
 const cardTestId=await pending.getAttribute('data-testid');expect(cardTestId).toMatch(/^escalation-[0-9a-f-]+$/);
 await pending.click();await expect(center.getByText('Мастер, уточните, можно ли продолжить консультацию по этому запросу.',{exact:true})).toBeVisible();await expect(center.getByLabel('Сводка запроса для решения')).toContainText('flower');
 await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();
 await expect(center.getByLabel('Сводка запроса для решения')).toContainText('idea: flower · client-stated');
 await intake.getByRole('button',{name:'Подтвердить поле Идея',exact:true}).click();await expect(intake.getByText('Подтверждено мастером',{exact:true})).toBeVisible();expect(await intake.getByText('Со слов клиента',{exact:true}).count()).toBe(1);
 await center.getByRole('button',{name:'Обновить запрос',exact:true}).click();
 await expect(center.getByTestId(cardTestId!)).toHaveAttribute('aria-pressed','true');
 await expect(center.getByLabel('Сводка запроса для решения')).toContainText('idea: flower · owner-confirmed');
 await expect(center.getByRole('button',{name:'Сохранить внутренний ответ',exact:true})).toBeEnabled();
 await center.getByLabel('Внутренний ответ владельца',{exact:true}).fill('Synthetic internal decision; no agreement to duration.');await center.getByRole('button',{name:'Сохранить внутренний ответ',exact:true}).click();await expect(center.getByText('Решение сохранено. Актуальная карточка получена.',{exact:true})).toBeVisible();
 await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();await expect(intake.getByText('Подтверждено мастером',{exact:true})).toHaveCount(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.getByRole('region',{name:'Предварительный запрос',exact:true})).toHaveCount(0);await expect(page.getByText('Synthetic owner flower '+variant,{exact:true})).toHaveCount(0);
});

async function chooseWork(page:Page,message:string,idea:string,placement:string,size?:string,style?:string){
 const fields=page.getByRole('group',{name:'Выбор сведений для заявки'});
 const beginning=fields.getByLabel('Начало работы',{exact:true});
 await beginning.selectOption(message);
 await fields.getByRole('checkbox',{name:`Идея: ${idea}`,exact:true}).check();
 await fields.getByRole('checkbox',{name:`Место: ${placement}`,exact:true}).check();
 if(size)await fields.getByRole('checkbox',{name:`Примерный размер: ${size}`,exact:true}).check();
 if(style)await fields.getByRole('checkbox',{name:`Стиль: ${style}`,exact:true}).check();
 const create=fields.getByRole('button',{name:'Создать заявку',exact:true});
 await expect(create).toBeDisabled();
 await fields.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе',exact:true}).check();
 return create;
}

type DraftWrite={key:string|undefined;body:unknown;requestId?:string;error?:string;status:number};

async function recordDraftWrite(route:Route,writes:DraftWrite[],method:'POST'|'PATCH',dropFirst=false){
 const request=route.request();
 if(request.method()!==method)return route.continue();
 const response=await route.fetch();
 const result=await response.json() as {request_id?:string;error?:{code:string}};
 writes.push({key:request.headers()['idempotency-key'],body:request.postDataJSON(),requestId:result.request_id,error:result.error?.code,status:response.status()});
 if(dropFirst&&writes.length===1)return route.abort('failed');
 await route.fulfill({response});
}

async function chooseRevision(page:Page,message:string){
 const group=page.getByRole('group',{name:'Уточнение заявки',exact:true});
 await group.getByLabel('Уточняемое сведение',{exact:true}).selectOption('approximate_size');
 await expect(group.getByRole('link',{name:'Сообщение для уточнения',exact:true})).toHaveAttribute('href',`#message-${message}`);
 const save=group.getByRole('button',{name:'Сохранить уточнение заявки',exact:true});
 await expect(save).toBeDisabled();
 await group.getByRole('checkbox',{name:'Сведение из этого сообщения относится к выбранной заявке',exact:true}).check();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 return save;
}

async function createSecondAfterRevision(page:Page,variant:Viewport){
 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,'request-deferred');
 const intakeUrl=`/api/v1/workspaces/${owner.workspace_id}/businesses/${owner.business_id}/intake/conversations/${conversation}`;
 const endpoint=`${intakeUrl}/service-requests`;
 const posts:DraftWrite[]=[],revisions:DraftWrite[]=[];
 await page.route(`**${endpoint}`,route=>recordDraftWrite(route,posts,'POST'));
 await page.route(`**${endpoint}/*`,route=>recordDraftWrite(route,revisions,'PATCH'));
 const card=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const id=card.getByTestId('service-request-id'),revision=card.getByTestId('service-request-revision');
 await (await chooseWork(page,collected.message_id,'flower','forearm','8 cm')).click();
 await expect(card.getByText(/8 cm · Со слов клиента/)).toBeVisible();
 await expect(revision).toHaveText('1');
 const firstId=(await id.textContent())!;

 const second=await input('second',conversation);
 const late=await input('late-size',conversation);
 for(const turn of [second,late])expect([turn.model_calls,turn.calls,turn.effects,turn.status]).toEqual([1,1,1,'CLARIFY']);
 await refreshIntake(inbox,intake);
 await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue('12 cm');
 await (await chooseRevision(page,late.message_id)).click();
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('2');
 expect(revisions).toHaveLength(1);
 expect(revisions[0]).toMatchObject({status:200,requestId:firstId});
 const change=revisions[0].body as DraftRevisionCommand;
 expect(change).toMatchObject({field:'approximate_size',source:{message_id:late.message_id}});
 expect(change.source.source_version).toMatch(/^[0-9a-f]{64}$/);
 await expect(card.getByRole('link',{name:'Сообщение для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
 await expect(card.getByText(change.source.source_version,{exact:true})).toBeVisible();

 const snapshot=await page.request.get(intakeUrl);
 expect(snapshot.status()).toBe(200);
 const summary=await snapshot.json() as Intake;
 expect(summary.facts.find(fact=>fact.field==='approximate_size')).toMatchObject({value:'12 cm',source:change.source});
 const send=await chooseWork(page,second.message_id,'swallow','shoulder','12 cm');
 await send.click();
 await expect(intake.getByRole('alert')).toContainText('Снимите отметку со спорного поля');
 expect(posts).toHaveLength(2);
 const rejected=posts[1],command=rejected.body as DraftCommand;
 expect(rejected).toMatchObject({status:409,error:'NEEDS_CLARIFICATION'});
 expect(rejected.requestId).toBeUndefined();
 expect(command).toMatchObject({expected_version:summary.version,expected_fingerprint:summary.fingerprint,intent_source:{message_id:second.message_id}});
 expect([...command.fields].sort()).toEqual(['approximate_size','idea','placement']);
 const index=await page.request.get(`${endpoint}/cards`);
 expect(index.status()).toBe(200);
 const {items}=await index.json() as {items:DraftListItem[]};
 expect(items).toEqual([expect.objectContaining({request_id:firstId,revision:'2'})]);
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('2');

 const fields=intake.getByRole('group',{name:'Выбор сведений для заявки'});
 const size=fields.getByRole('checkbox',{name:'Примерный размер: 12 cm',exact:true});
 const confirmed=fields.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе',exact:true});
 await expect(fields.getByLabel('Начало работы',{exact:true})).toHaveValue(second.message_id);
 for(const checkbox of ['Идея: swallow','Место: shoulder','Примерный размер: 12 cm'])
  await expect(fields.getByRole('checkbox',{name:checkbox,exact:true})).toBeChecked();
 await expect(confirmed).not.toBeChecked();
 await expect(send).toBeDisabled();
 await size.uncheck();
 await confirmed.check();
 await send.click();

 await expect(card.getByText(/swallow · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/shoulder · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/12 cm/)).toHaveCount(0);
 await expect(card.getByText(/Не хватает/)).toContainText('Примерный размер');
 await expect(revision).toHaveText('1');
 expect(posts).toHaveLength(3);
 const accepted=posts[2];
 expect(accepted).toMatchObject({status:200,body:{...command,fields:command.fields.filter(field=>field!=='approximate_size')}});
 expect(accepted.key).toBeTruthy();
 expect(accepted.key).not.toBe(rejected.key);
 expect(accepted.requestId).toMatch(/^[0-9a-f-]{36}$/);
 expect(accepted.requestId).not.toBe(firstId);
 await expect(id).toHaveText(accepted.requestId!);

 const picker=intake.getByLabel('Сохранённая заявка',{exact:true});
 await expect(picker.locator('option')).toHaveCount(3);
 await picker.selectOption(firstId);
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('2');
 for(const value of ['flower','forearm','12 cm'])await expect(card.getByText(`${value} · Со слов клиента`,{exact:false})).toBeVisible();
 await expect(card.getByRole('link',{name:'Сообщение для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
 await expect(card.getByText(change.source.source_version,{exact:true})).toBeVisible();
 expect(posts).toHaveLength(3);
 expect(revisions).toHaveLength(1);
}

test('@narrow service request preserves sources across tabs and rejects an assigned size on create',async({page,context},info)=>{
 test.setTimeout(120000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {input,conversation,collected,intake,inbox,serviceName}=await beginIntake(page,variant,'request');
 const secondTab=await context.newPage();
 await secondTab.goto('/');
 await openWorkspace(secondTab);
 await openConversation(secondTab,conversation);

 const firstPosts:DraftWrite[]=[],secondPosts:DraftWrite[]=[],revisions:DraftWrite[]=[],staleWrites:DraftWrite[]=[];
 const endpoint=`/intake/conversations/${conversation}/service-requests`;
 const reads:(string|null)[]=[];
 page.on('request',request=>{
  const url=new URL(request.url());
  if(request.method()==='GET'&&url.pathname.endsWith(endpoint))reads.push(url.searchParams.get('request_id'));
 });
 await page.route(`**${endpoint}`,route=>recordDraftWrite(route,firstPosts,'POST',true));
 await secondTab.route(`**${endpoint}`,route=>recordDraftWrite(route,secondPosts,'POST'));
 await page.route(`**${endpoint}/*`,route=>recordDraftWrite(route,revisions,'PATCH',true));
 const [firstCreate,secondCreate]=await Promise.all([
  chooseWork(page,collected.message_id,'flower','forearm','8 cm'),
  chooseWork(secondTab,collected.message_id,'flower','forearm','8 cm'),
 ]);
 await Promise.all([firstCreate.click(),secondCreate.click()]);
 const retryCreate=intake.getByRole('button',{name:'Повторить создание заявки',exact:true});
 await expect(retryCreate).toBeVisible();
 const competingId=secondTab.getByTestId('service-request-id');
 await expect(competingId).toHaveText(/^[0-9a-f-]{36}$/);
 const firstId=(await competingId.textContent())!;
 expect(firstPosts).toHaveLength(1);
 expect(secondPosts).toHaveLength(1);
 expect(firstPosts[0]).toMatchObject({requestId:firstId,status:200});
 expect(secondPosts[0]).toMatchObject({requestId:firstId,status:200});
 expect(firstPosts[0].key).toBeTruthy();
 expect(secondPosts[0].key).toBeTruthy();
 expect(firstPosts[0].key).not.toBe(secondPosts[0].key);
 expect(firstPosts[0].body).toEqual(secondPosts[0].body);

 await retryCreate.click();
 const card=page.getByRole('region',{name:'Черновик заявки',exact:true});
 const id=card.getByTestId('service-request-id'),revision=card.getByTestId('service-request-revision');
 const picker=page.getByLabel('Сохранённая заявка',{exact:true});
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('1');
 expect(firstPosts).toHaveLength(2);
 expect(firstPosts[1]).toEqual(firstPosts[0]);
 await expect(card.getByText(serviceName,{exact:true})).toBeVisible();
 await expect(card.getByText(/flower · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/forearm · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/8 cm · Со слов клиента/)).toBeVisible();
 await expect(card.getByRole('link',{name:'Сообщение для поля Идея',exact:true})).toHaveAttribute('href',`#message-${collected.message_id}`);
 const selection=firstPosts[0].body as {intent_source:{source_version:string};fields:string[]};
 expect([...selection.fields].sort()).toEqual(['approximate_size','idea','placement']);
 expect(selection.intent_source.source_version).toMatch(/^[0-9a-f]{64}$/);
 await expect(card.getByText(selection.intent_source.source_version,{exact:true}).first()).toBeVisible();
 await expect(card.getByText(/Не хватает/)).toContainText('Стиль');
 await expect(card.getByText('Какой стиль вам нравится?',{exact:true})).toBeVisible();

 const second=await input('second',conversation);
 expect([second.model_calls,second.calls,second.effects,second.status]).toEqual([1,1,1,'CLARIFY']);
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,second.message_id,'swallow','shoulder')).click();
 await expect(card.getByText(/swallow · Со слов клиента/)).toBeVisible();
 const secondId=(await id.textContent())!;
 expect(firstId).not.toBe(secondId);
 await expect(revision).toHaveText('1');
 await expect(card.getByText(serviceName,{exact:true})).toBeVisible();
 expect(firstPosts).toHaveLength(3);
 expect(firstPosts[2]).toMatchObject({requestId:secondId,status:200});
 await expect(picker.locator('option')).toHaveCount(3);

 await picker.selectOption(firstId);
 await expect(id).toHaveText(firstId);
 await expect(card.getByText(/8 cm · Со слов клиента/)).toBeVisible();
 await expect(revision).toHaveText('1');
 await expect(intake.getByRole('group',{name:'Уточнение заявки',exact:true})).toHaveCount(0);
 expect(firstPosts).toHaveLength(3);
 expect(revisions).toHaveLength(0);

 const staleTab=secondTab;
 const staleInbox=staleTab.getByRole('region',{name:'Переписка',exact:true});
 const staleIntake=staleTab.getByRole('region',{name:'Предварительный запрос',exact:true});
 const staleCard=staleTab.getByRole('region',{name:'Черновик заявки',exact:true});
 const stalePicker=staleTab.getByLabel('Сохранённая заявка',{exact:true});
 await staleTab.route(`**${endpoint}/*`,route=>recordDraftWrite(route,staleWrites,'PATCH'));
 await expect(staleCard.getByTestId('service-request-id')).toHaveText(firstId);
 await expect(staleCard.getByTestId('service-request-revision')).toHaveText('1');

 const late=await input('late-size',conversation);
 expect([late.model_calls,late.calls,late.effects,late.status]).toEqual([1,1,1,'CLARIFY']);
 await Promise.all([refreshIntake(inbox,intake),refreshIntake(staleInbox,staleIntake)]);
 await Promise.all([intake,staleIntake].map(panel=>expect(panel.getByLabel('Примерный размер',{exact:true})).toHaveValue('12 cm')));
 const [save,staleSave]=await Promise.all([chooseRevision(page,late.message_id),chooseRevision(staleTab,late.message_id)]);
 await save.click();
 const retry=intake.getByRole('button',{name:'Повторить изменение заявки',exact:true});
 await expect(retry).toBeVisible();
 expect(revisions).toHaveLength(1);
 expect(revisions[0]).toMatchObject({status:200,requestId:firstId});
 await staleSave.click();
 await expect(staleIntake.getByRole('alert')).toContainText('Заявка или сводка изменились');
 await expect(staleCard.getByTestId('service-request-revision')).toHaveText('1');
 await expect(staleSave).toBeDisabled();
 expect(staleWrites).toHaveLength(1);
 expect(staleWrites[0]).toMatchObject({status:409,error:'STALE_STATE',body:revisions[0].body});
 expect(staleWrites[0].key).not.toBe(revisions[0].key);
 await retry.click();
 await expect(revision).toHaveText('2');
 expect(revisions).toHaveLength(2);
 expect(revisions[1]).toEqual(revisions[0]);
 const update=revisions[0].body as {expected_revision:string;field:string;source:{message_id:string;source_version:string}};
 expect(update).toMatchObject({expected_revision:'1',field:'approximate_size',source:{message_id:late.message_id}});
 expect(update.source.source_version).toMatch(/^[0-9a-f]{64}$/);

 reads.length=0;
 await page.reload();
 await openWorkspace(page);
 await openConversation(page,conversation);
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('2');
 expect(reads).toContain(firstId);
 expect(reads.every(requestId=>requestId===firstId)).toBe(true);
 await expect(card.getByText(/12 cm · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/flower · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/forearm · Со слов клиента/)).toBeVisible();
 await expect(card.getByRole('link',{name:'Сообщение для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
 await expect(card.getByText(update.source.source_version,{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);

 await staleIntake.getByRole('button',{name:'Обновить карточку заявки',exact:true}).click();
 await expect(staleCard.getByTestId('service-request-revision')).toHaveText('2');
 await stalePicker.selectOption(secondId);
 await expect(staleCard.getByTestId('service-request-id')).toHaveText(secondId);
 await expect(staleCard.getByTestId('service-request-revision')).toHaveText('1');
 await expect(staleCard.getByText(/swallow · Со слов клиента/)).toBeVisible();
 await expect(staleCard.getByText(/shoulder · Со слов клиента/)).toBeVisible();
 await expect(staleCard.getByText(/8 cm|12 cm/)).toHaveCount(0);
 await expect(staleCard.getByRole('link',{name:'Сообщение для поля Место',exact:true})).toHaveAttribute('href',`#message-${second.message_id}`);

 const ambiguous=await input('ambiguous',conversation);
 expect([ambiguous.model_calls,ambiguous.calls,ambiguous.effects,ambiguous.status]).toEqual([1,1,1,'CLARIFY']);
 await refreshIntake(inbox,intake);
 await expect(intake.getByText('Уточните, к какой услуге или отдельной идее относится сообщение.',{exact:true})).toBeVisible();
 await expect(intake.getByRole('button',{name:'Сохранить уточнение заявки',exact:true})).toHaveCount(0);
 await expect(intake.getByRole('button',{name:'Создать заявку',exact:true})).toHaveCount(0);
 await expect(id).toHaveText(firstId);
 await expect(revision).toHaveText('2');
 expect(firstPosts).toHaveLength(3);
 expect(secondPosts).toHaveLength(1);
 expect(revisions).toHaveLength(2);
 expect(staleWrites).toHaveLength(1);

 await secondTab.close();
 await test.step('Reject a previously assigned size and create B with its own facts',()=>createSecondAfterRevision(page,variant));
});

test('@narrow assesses the selected request against published duration and size limits',async({page},info)=>{
 test.setTimeout(120000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const published=settings.getByRole('region',{name:'Опубликованные сведения',exact:true});
 const mode=settings.getByLabel('Режим длительности 1',{exact:true});
 const price=settings.getByLabel('Режим цены 1',{exact:false});
 // The shared CONTROLLED fixture can carry synthetic FAQ/rules from earlier journeys.
 for(const name of [/^Удалить FAQ \d+$/,/^Удалить правило \d+$/]){
  const buttons=settings.getByRole('button',{name});
  for(let index=await buttons.count()-1;index>=0;index--)await buttons.nth(index).click();
 }
 await price.selectOption('OWNER_QUOTE');
 await settings.getByLabel('Цена, копейки 1',{exact:true}).fill('');
 await settings.getByLabel('Пояснение формулы 1',{exact:true}).fill('');
 await mode.selectOption('FIXED');
 await settings.getByLabel('Длительность, минуты 1',{exact:true}).fill('65');
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(/Цена: Решение владельца/)).toBeVisible();

 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,'assessment');
 const card=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const panel=card.getByRole('region',{name:'Оценка заявки',exact:true});
 const picker=intake.getByLabel('Сохранённая заявка',{exact:true});
 const evaluate=panel.getByRole('button',{name:/^(Оценить заявку|Пересчитать оценку)$/});
 const clock=panel.getByText(/Занято на следующий сеанс/);
 const refresh=panel.getByRole('button',{name:'Обновить оценку заявки',exact:true});
 const pricing=card.getByRole('region',{name:'Расчёт цены',exact:true});
 const calculatePrice=pricing.getByRole('button',{name:/^(Рассчитать|Пересчитать) цену$/});
 const endpoint=`/api/v1/workspaces/${owner.workspace_id}/businesses/${owner.business_id}/intake/conversations/${conversation}/service-requests`;
 async function readAssessment(id:string):Promise<ServiceAssessment>{
  const response=await page.request.get(`${endpoint}/${id}/assessment`);
  expect(response.status()).toBe(200);
  return await response.json() as ServiceAssessment;
 }
 await intake.getByRole('button',{name:'Подтвердить поле Примерный размер',exact:true}).click();
 await expect(intake.getByText('Подтверждено мастером',{exact:true})).toBeVisible();
 await (await chooseWork(page,collected.message_id,'flower','forearm','8 cm','linework')).click();
 await expect(card.getByTestId('service-request-id')).toHaveText(/^[0-9a-f-]{36}$/);
 const firstId=(await card.getByTestId('service-request-id').textContent())!;
 await evaluate.click();
 await expect(clock).toContainText('65 мин');
 await expect(panel.getByText('Выполнимо',{exact:true})).toBeVisible();
 await expect(panel.getByText('Фиксированная длительность из опубликованных настроек.',{exact:true})).toBeVisible();
 const fixed=await readAssessment(firstId);
 expect(fixed).toMatchObject({current:true,outcome:'FEASIBLE',reason:'FIXED_DURATION',occupied_minutes:65});
 const repeated=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname===`${endpoint}/${firstId}/assessment`);
 await evaluate.click();
 expect(await (await repeated).json()).toEqual(fixed);
 await expect(clock).toContainText('65 мин');
 await calculatePrice.click();
 await expect(pricing.getByText('Цену определяет мастер',{exact:true})).toBeVisible();
 await expect(clock).toContainText('65 мин');

 await mode.selectOption('CONFIGURED_RULE');
 await settings.getByLabel('Порог размера, мм 1',{exact:true}).fill('80');
 await settings.getByLabel('Минуты до порога включительно 1',{exact:true}).fill('55');
 await settings.getByLabel('Минуты свыше порога 1',{exact:true}).fill('95');
 const ruleText='До 80 мм включительно — 55 мин. Свыше 80 мм — 95 мин.';
 await expect(settings.locator('form').first().getByText(ruleText,{exact:true})).toBeVisible();
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(ruleText)).toBeVisible();
 await refresh.click();
 const staleAssessment=panel.getByText('Архивная оценка. Для актуального результата выполните пересчёт.',{exact:true});
 await expect(staleAssessment).toBeVisible();
 await expect(clock).toHaveCount(0);
 await expect(panel.getByText(fixed.release_id!,{exact:true})).toBeVisible();
 expect(await readAssessment(firstId)).toMatchObject({assessment_id:fixed.assessment_id,release_id:fixed.release_id,current:false});
 await evaluate.click();
 await expect(clock).toContainText('55 мин');
 await expect(panel.getByText('Порог опубликованного правила 80 мм.',{exact:true})).toBeVisible();
 await expect(panel.getByRole('link',{name:'Источник оценки для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${collected.message_id}`);
 const configured=await readAssessment(firstId);
 expect(configured).toMatchObject({
  request_revision:fixed.request_revision,current:true,outcome:'FEASIBLE',reason:'SIZE_DURATION_RULE',size_mm:80,occupied_minutes:55,
  archived_duration:{
   assessment_id:fixed.assessment_id,request_revision:fixed.request_revision,
   release_id:fixed.release_id,activation_version:fixed.activation_version,occupied_minutes:65,
  },
 });
 expect(configured.assessment_id).not.toBe(fixed.assessment_id);
 const archive=panel.getByText('Архивная оценка',{exact:true});
 const oldDuration=panel.getByText('Ревизия 1 · ранее было утверждено 65 мин.',{exact:true});
 await expect(archive).toBeVisible();
 await expect(oldDuration).toBeHidden();
 await archive.click();
 await expect(oldDuration).toBeVisible();
 await expect(clock).toContainText('55 мин');
 await refresh.click();
 await expect(refresh).toBeEnabled();
 await expect(oldDuration).toBeVisible();
 await expect(clock).toContainText('55 мин');
 expect(await readAssessment(firstId)).toEqual(configured);

 const second=await input('assess-second',conversation);
 expect([second.model_calls,second.calls,second.effects,second.status]).toEqual([1,1,1,'CLARIFY']);
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,second.message_id,'swallow','shoulder',undefined,'linework')).click();
 await expect(card.getByText(/swallow · Со слов клиента/)).toBeVisible();
 const secondId=(await card.getByTestId('service-request-id').textContent())!;
 expect(secondId).not.toBe(firstId);
 await evaluate.click();
 await expect(panel.getByText('Нужны данные',{exact:true})).toBeVisible();
 await expect(panel.getByText('Какой примерный размер вы представляете, в сантиметрах?',{exact:true})).toBeVisible();
 await expect(clock).toHaveCount(0);
 const missing=await readAssessment(secondId);
 expect(missing).toMatchObject({outcome:'NEEDS_DATA',field:'approximate_size',occupied_minutes:null});
 expect(missing.evidence.every(fact=>fact.source.message_id===second.message_id)).toBe(true);

 const late=await input('late-size',conversation);
 expect([late.model_calls,late.calls,late.effects,late.status]).toEqual([1,1,1,'PRELIMINARILY_COMPLETE']);
 await refreshIntake(inbox,intake);
 await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue('12 cm');
 await picker.selectOption(firstId);
 await expect(card.getByTestId('service-request-id')).toHaveText(firstId);
 await (await chooseRevision(page,late.message_id)).click();
 await expect(card.getByTestId('service-request-revision')).toHaveText('2');
 await expect(staleAssessment).toBeVisible();
 await expect(clock).toHaveCount(0);
 await evaluate.click();
 await expect(clock).toContainText('95 мин');
 await expect(panel.getByRole('link',{name:'Источник оценки для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
 expect(await readAssessment(firstId)).toMatchObject({request_revision:'2',outcome:'FEASIBLE',size_mm:120,occupied_minutes:95});

 await settings.getByRole('button',{name:'Добавить правило',exact:true}).click();
 await settings.getByLabel('Тип правила 1',{exact:false}).selectOption('MAX_SIZE_MM');
 await settings.getByLabel('Максимальный размер, мм 1',{exact:true}).fill('100');
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(/Максимальный размер: 100 мм/)).toBeVisible();
 await evaluate.click();
 await expect(panel.getByText('Отказ',{exact:true})).toBeVisible();
 await expect(panel.getByText('Размер 120 мм превышает опубликованный предел 100 мм.',{exact:true})).toBeVisible();
 await expect(clock).toHaveCount(0);
 expect(await readAssessment(firstId)).toMatchObject({outcome:'DECLINED',reason:'SIZE_LIMIT_EXCEEDED',limit:100,size_mm:120});

 const removeRule=settings.getByRole('button',{name:'Удалить правило 1',exact:true});
 await removeRule.click();
 await settings.getByRole('button',{name:'Добавить правило',exact:true}).click();
 await settings.getByLabel('Значение правила 1',{exact:true}).fill('18');
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(/Минимальный возраст: 18/)).toBeVisible();
 await evaluate.click();
 await expect(panel.getByText('Нужны данные',{exact:true})).toBeVisible();
 await expect(panel.getByText('Уточните возраст для проверки опубликованного ограничения.',{exact:true})).toBeVisible();
 await expect(clock).toHaveCount(0);
 expect(await readAssessment(firstId)).toMatchObject({outcome:'NEEDS_DATA',reason:'MIN_AGE_UNCONFIRMED',limit:18,occupied_minutes:null});

 await removeRule.click();
 await mode.selectOption('OWNER_DEFINED');
 await price.selectOption('FIXED');
 await settings.getByLabel('Цена, копейки 1',{exact:true}).fill('15000');
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(/Цена: Задано владельцем · 150 ₽/)).toBeVisible();
 await evaluate.click();
 await expect(panel.getByText('Решает мастер',{exact:true})).toBeVisible();
 await expect(panel.getByText('Мастер задаёт длительность следующего сеанса.',{exact:true})).toBeVisible();
 await expect(clock).toHaveCount(0);
 expect(await readAssessment(firstId)).toMatchObject({outcome:'NEEDS_OWNER',reason:'OWNER_DURATION',occupied_minutes:null});
 await calculatePrice.click();
 await expect(pricing.getByText('150 ₽',{exact:true})).toBeVisible();
 await expect(panel.getByText('Решает мастер',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('@narrow prices each selected work from a published rule and preserves the previous price',async({page},info)=>{
 test.setTimeout(90000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const rules=settings.getByRole('button',{name:/^Удалить правило \d+$/});
 for(let index=await rules.count()-1;index>=0;index--)await rules.nth(index).click();
 await settings.getByLabel('Режим цены 1',{exact:true}).selectOption('CONFIGURED_FORMULA');
 for(const [label,value] of [
  ['База, копейки 1','250000'],['За начатый шаг, копейки 1','50000'],
  ['Шаг размера, мм 1','10'],['Предел размера для цены, мм 1','1000'],
  ['Прибавка к верхней границе, копейки 1',''],
 ])await settings.getByLabel(label,{exact:true}).fill(value);
 const example=settings.getByLabel('Размер примера, мм 1',{exact:true});
 const sample=settings.getByRole('status',{name:'Пример цены 1',exact:true});
 await example.fill('20');
 await expect(sample).toHaveText('3 500 ₽');
 await example.fill('21');
 await expect(sample).toHaveText('4 000 ₽');
 await publishIntakeService(settings,serviceName);

 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,'pricing');
 const card=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const panel=card.getByRole('region',{name:'Расчёт цены',exact:true});
 const current=panel.getByRole('article',{name:'Текущий расчёт цены',exact:true});
 const calculateButton=panel.getByRole('button',{name:/^(Рассчитать|Пересчитать) цену$/});
 const refresh=intake.getByRole('button',{name:'Обновить сводку',exact:true});
 const sourceLink=current.getByRole('link',{name:'Источник размера для цены',exact:true});
 const cardId=card.getByTestId('service-request-id');
 const endpoint=`/api/v1/workspaces/${owner.workspace_id}/businesses/${owner.business_id}/intake/conversations/${conversation}/service-requests`;
 async function calculate(id:string):Promise<PriceCalculation>{
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`${endpoint}/${id}/pricing`);
  await calculateButton.click();
  const saved=await response;
  expect(saved.status()).toBe(200);
  await expect(calculateButton).toBeEnabled();
  return await saved.json() as PriceCalculation;
 }
 await (await chooseWork(page,collected.message_id,'flower','forearm','20 mm','linework')).click();
 await expect(cardId).toHaveText(/^[0-9a-f-]{36}$/);
 const firstId=(await cardId.textContent())!;
 const first=await calculate(firstId);
 expect(first).toMatchObject({outcome:'EXACT',authority:'CONFIRMED',amount_minor:350000,size_mm:20,steps:2});
 await expect(current.getByText('3 500 ₽',{exact:true})).toBeVisible();
 await expect(sourceLink).toHaveAttribute('href',`#message-${collected.message_id}`);
 expect(await calculate(firstId)).toEqual(first);

 const separate=await input('price-second',conversation);
 expect(separate.status).toBe('CLARIFY');
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,separate.message_id,'swallow','shoulder',undefined,'linework')).click();
 await expect(cardId).not.toHaveText(firstId);
 const secondId=(await cardId.textContent())!;
 const missing=await calculate(secondId);
 expect(missing).toMatchObject({outcome:'NEEDS_INPUT',reason:'SIZE_REQUIRED',amount_minor:null});
 await expect(current.getByText('Уточните подтверждённый размер в миллиметрах.',{exact:true})).toBeVisible();

 const measurement=await input('price-size',conversation);
 expect(measurement.status).toBe('PRELIMINARILY_COMPLETE');
 await refreshIntake(inbox,intake);
 await (await chooseRevision(page,measurement.message_id)).click();
 await expect(card.getByTestId('service-request-revision')).toHaveText('2');
 const second=await calculate(secondId);
 expect(second).toMatchObject({outcome:'EXACT',authority:'CONFIRMED',amount_minor:400000,size_mm:21,steps:3,release_id:first.release_id});
 await expect(current.getByText('4 000 ₽',{exact:true})).toBeVisible();
 await expect(sourceLink).toHaveAttribute('href',`#message-${measurement.message_id}`);
 await expect(current.getByText(first.release_id!,{exact:true})).toBeVisible();
 expect(await calculate(secondId)).toEqual(second);

 await settings.getByLabel('Прибавка к верхней границе, копейки 1',{exact:true}).fill('50000');
 await publishIntakeService(settings,serviceName);
 await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByText(/Верхняя граница выше на 500\s₽/)).toBeVisible();
 const pricePath=`${endpoint}/${secondId}/pricing`;
 const priceCalls:string[]=[];
 const observePrice=(r:{url():string;method():string})=>{
  if(new URL(r.url()).pathname===pricePath)priceCalls.push(r.method());
 };
 page.on('request',observePrice);
 const revalidated=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname===pricePath);
 await refresh.click();
 expect((await (await revalidated).json() as PriceHistory).items[0]).toEqual({...second,current:false});
 await expect(current).toHaveCount(0);
 expect(priceCalls).toEqual(['GET']);
 page.off('request',observePrice);
 const provisional=await calculate(secondId);
 expect(provisional).toMatchObject({outcome:'RANGE',authority:'PROVISIONAL',amount_minor:null,lower_minor:400000,upper_minor:450000});
 expect(provisional.release_id).not.toBe(second.release_id);
 await expect(current.getByText('Предварительный диапазон',{exact:false})).toContainText('4 000 ₽ – 4 500 ₽');
 await panel.getByText('История расчётов цены',{exact:true}).click();
 const old=panel.getByRole('article',{name:'Архивный расчёт цены',exact:true}).filter({has:page.getByText('4 000 ₽',{exact:true})});
 await expect(old).toBeVisible();
 await expect(old.getByText(second.release_id!,{exact:true})).toBeVisible();
 await refresh.click();
 await expect(refresh).toBeEnabled();
 await expect(old).toBeVisible();
 const read=await page.request.get(`${endpoint}/${secondId}/pricing`);
 expect(read.status()).toBe(200);
 const history=await read.json() as PriceHistory;
 expect(history.items).toEqual([provisional,{...second,current:false},{...missing,current:false}]);
 const oversize=await input('price-oversize',conversation);
 await refreshIntake(inbox,intake);
 await (await chooseRevision(page,oversize.message_id)).click();
 await expect(card.getByTestId('service-request-revision')).toHaveText('3');
 expect(await calculate(secondId)).toMatchObject({
  outcome:'NEEDS_HUMAN',reason:'SIZE_OUTSIDE_RULE',amount_minor:null,size_mm:1001,
  size_fact:{value:'100,1 cm',source:{message_id:oversize.message_id}},
 });
 await expect(current.getByText('Цену определяет мастер',{exact:true})).toBeVisible();
 await expect(current.getByText('Размер превышает опубликованный предел 1000 мм.',{exact:true})).toBeVisible();
 await expect(sourceLink).toHaveAttribute('href',`#message-${oversize.message_id}`);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

for(const [journey,operation,description] of [
 ['assessment-complex','late-cover-up','with an updated field'],
 ['assessment-complex-source','complex-message','without changing fields'],
] as const){
test(`@narrow late cover-up moves approved minutes to the archive in the owner card ${description}`,async({page},info)=>{
 test.setTimeout(90000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const rules=settings.getByRole('button',{name:/^Удалить правило \d+$/});
 for(let index=await rules.count()-1;index>=0;index--)await rules.nth(index).click();
 await settings.getByLabel('Режим длительности 1',{exact:true}).selectOption('FIXED');
 await settings.getByLabel('Длительность, минуты 1',{exact:true}).fill('65');
 await publishIntakeService(settings,serviceName);

 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,journey);
 const card=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const panel=card.getByRole('region',{name:'Оценка заявки',exact:true});
 const clock=panel.getByText(/Занято на следующий сеанс/);
 const evaluate=panel.getByRole('button',{name:/^(Оценить заявку|Пересчитать оценку)$/});
 await (await chooseWork(page,collected.message_id,'flower','forearm','8 cm','linework')).click();
 await expect(card.getByTestId('service-request-id')).toHaveText(/^[0-9a-f-]{36}$/);
 const requestId=(await card.getByTestId('service-request-id').textContent())!;
 await evaluate.click();
 await expect(clock).toContainText('65 мин');

 const late=await input(operation,conversation);
 expect([late.model_calls,late.calls,late.effects,late.status]).toEqual([1,0,0,'OWNER_HANDOFF']);
 await refreshIntake(inbox,intake);
 if(operation==='complex-message'){
  await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue('8 cm');
  const group=page.getByRole('group',{name:'Уточнение заявки',exact:true});
  await group.getByLabel('Уточняемое сведение',{exact:true}).selectOption('complex_work');
  await group.getByLabel('Сообщение о сложности',{exact:true}).selectOption(late.message_id);
  await expect(group.getByRole('link',{name:'Сообщение для уточнения',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
  const save=group.getByRole('button',{name:'Сохранить уточнение заявки',exact:true});
  await expect(save).toBeDisabled();
  await group.getByRole('checkbox',{name:'Сообщение о сложности относится к выбранной заявке',exact:true}).check();
  const patch=page.waitForRequest(request=>request.method()==='PATCH'&&new URL(request.url()).pathname.endsWith(`/service-requests/${requestId}`));
  await save.click();
  const body=(await patch).postDataJSON() as DraftRevisionCommand;
  expect(body).not.toHaveProperty('field');
  expect(body.source).toMatchObject({message_id:late.message_id,source_version:expect.stringMatching(/^[0-9a-f]{64}$/)});
 }else{
  await (await chooseRevision(page,late.message_id)).click();
 }
 await expect(card.getByTestId('service-request-id')).toHaveText(requestId);
 await expect(card.getByTestId('service-request-revision')).toHaveText('2');
 if(operation==='complex-message')await expect(card.getByText('Примерный размер · 8 cm · Со слов клиента',{exact:true})).toBeVisible();
 await expect(panel.getByText(/Архивная оценка\. Для актуального результата/)).toBeVisible();
 await expect(panel.getByText('Ранее было утверждено 65 мин.',{exact:true})).toBeVisible();
 await expect(clock).toHaveCount(0);

 await evaluate.click();
 await expect(panel.getByText('Решает мастер',{exact:true})).toBeVisible();
 await expect(panel.getByText(/Перекрытие старой татуировки\./)).toBeVisible();
 await expect(panel.getByRole('link',{name:'Сообщение с уточнением',exact:true})).toHaveAttribute('href',`#message-${late.message_id}`);
 await expect(clock).toHaveCount(0);
 const oldDuration=panel.getByText('Ревизия 1 · ранее было утверждено 65 мин.',{exact:true});
 await expect(oldDuration).toBeHidden();
 await panel.getByText('Архивная оценка',{exact:true}).click();
 await expect(oldDuration).toBeVisible();
 await expect(clock).toHaveCount(0);
});
}

test('@narrow confirms one selected owner decision while the other work stays open',async({page},info)=>{
 test.setTimeout(90_000);
 page.setDefaultTimeout(12_000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const rules=settings.getByRole('button',{name:/^Удалить правило \d+$/});
 for(let index=await rules.count()-1;index>=0;index--)await rules.nth(index).click();
 await settings.getByLabel('Режим цены 1',{exact:true}).selectOption('OWNER_QUOTE');
 await settings.getByLabel('Режим длительности 1',{exact:true}).selectOption('OWNER_DEFINED');
 await publishIntakeService(settings,serviceName);
 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,'owner-decision');
 const work=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const center=page.getByRole('region',{name:'Решения по заявкам',exact:true});
 const detail=center.getByRole('article',{name:'Карточка решения по заявке',exact:true});
 const cardId=work.getByTestId('service-request-id');
 const approvalButton=work.getByRole('button',{name:'Открыть решение мастера',exact:true});
 const collection='/api/v1/workspaces/'+owner.workspace_id+'/businesses/'+owner.business_id+'/intake/conversations/'+conversation+'/service-requests';
 const approvalPath=(request:string)=>collection+'/'+request+'/approvals';
 async function open(request:string){
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===approvalPath(request));
  await approvalButton.click();
  const saved=await response;
  expect(saved.status()).toBe(200);
  return await saved.json() as ApprovalCard;
 }

 await (await chooseWork(page,collected.message_id,'flower','forearm','20 mm','linework')).click();
 await expect(cardId).toHaveText(/^[0-9a-f-]{36}$/);
 const aId=(await cardId.textContent())!;
 const first=await open(aId);
 expect(first).toMatchObject({status:'PENDING',decision:null,basis:{service_name:serviceName,amount_minor:null,occupied_minutes:null,can_approve:true}});
 await expect(detail.getByRole('heading',{name:serviceName+' · заявка #'+aId.slice(-6)})).toBeVisible();
 expect(first.basis.intent_source.message_id).toBe(collected.message_id);

 const separate=await input('price-second',conversation);
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,separate.message_id,'swallow','shoulder',undefined,'linework')).click();
 await expect(cardId).not.toHaveText(aId);
 const bId=(await cardId.textContent())!;
 const second=await open(bId);
 expect(second).toMatchObject({status:'PENDING',decision:null,basis:{intent_source:{message_id:separate.message_id}}});
 expect(second.approval_id).not.toBe(first.approval_id);
 const a=center.getByTestId('approval-'+first.approval_id),b=center.getByTestId('approval-'+second.approval_id);
 await expect(a).toContainText('Ожидает решения мастера');
 await expect(b).toContainText('Ожидает решения мастера');
 await expect(a).toBeVisible();
 await expect(b).toBeVisible();

 const control=page.getByRole('region',{name:'Управление диалогом',exact:true});
 await control.getByRole('button',{name:'Обновить режим',exact:true}).click();
 await control.getByRole('button',{name:'Забрать управление',exact:true}).click();
 await expect(control.getByText('Управление у мастера',{exact:true})).toBeVisible();
 await a.click();
 await expect(detail.getByRole('link',{name:'Исходная реплика заявки'})).toBeVisible();
 const aDecisionUrl=approvalPath(aId)+'/'+first.approval_id;
 const decisions:{body:ApprovalBody;card:ApprovalCard}[]=[];
 await page.route('**'+aDecisionUrl,async route=>{
  if(route.request().method()!=='POST')return route.continue();
  const result=await route.fetch();
  expect(result.status()).toBe(200);
  decisions.push({body:route.request().postDataJSON(),card:await result.json() as ApprovalCard});
  if(decisions.length===1)await route.abort('failed');
  else await route.fulfill({response:result});
 });
 await detail.getByLabel('Цена, ₽',{exact:true}).fill('3950,01');
 await detail.getByLabel('Длительность следующего сеанса, мин',{exact:true}).fill('75');
 await detail.getByLabel('Пояснение или вопрос',{exact:true}).fill('Synthetic approved terms');
 await detail.getByRole('button',{name:'Подтвердить условия',exact:true}).click();
 await center.getByRole('button',{name:'Повторить то же решение',exact:true}).click();
 const approved=detail.getByRole('region',{name:'Подтверждённые условия',exact:true});
 await expect(approved).toContainText(/3\s950,01\s₽/);
 await expect(approved).toContainText('75 мин');
 expect(decisions).toHaveLength(2);
 expect(decisions[0]).toEqual(decisions[1]);
 expect(decisions[0].body).toMatchObject({operation:'APPROVE',amount_minor:395001,occupied_minutes:75});
 expect(decisions[0].card.decision?.decision_id).toBeTruthy();
 await expect(b).toContainText('Ожидает решения мастера');
 await expect(control.getByText('Управление у мастера',{exact:true})).toBeVisible();

 await page.reload();
 await openWorkspace(page);
 await expect(b).toContainText('Ожидает решения мастера');
 await a.click();
 await expect(detail).toContainText(decisions[0].card.decision!.decision_id);
 await expect(approved).toContainText('75 мин');

 // Use another real conversation and the server's real history cursor, without
 // loading the older message into Inbox before opening the pinned source.
 const other=await input('seed',undefined,'owner-source-other');
 expect(other.conversation_id).not.toBe(conversation);
 const otherInbox=await openConversation(page,other.conversation_id);
 const pinned=first.basis.intent_source;
 const pinnedText='Synthetic price flower forearm 20 mm linework';
 const selectedDecision=decisions[0].card.decision!.decision_id;
 const sourcePath=aDecisionUrl+'/sources/'+pinned.message_id;
 async function showPinnedSource(inboxConversation:string){
  await expect(otherInbox.getByTestId('conversation-'+inboxConversation)).toHaveAttribute('aria-pressed','true');
  await expect(page.getByTestId('message-'+pinned.message_id)).toHaveCount(0);
  const response=page.waitForResponse(reply=>reply.request().method()==='GET'
    &&new URL(reply.url()).pathname===sourcePath);
  await detail.getByRole('link',{name:'Исходная реплика заявки',exact:true}).click();
  const reply=await response;
  expect(reply.status()).toBe(200);
  expect(await reply.json()).toMatchObject({
    workspace_id:owner.workspace_id,conversation_id:conversation,client_id:first.client_id,
    request_id:aId,approval_id:first.approval_id,...pinned,text:pinnedText,
  });
  await expect(detail.getByTestId('approval-source-'+pinned.message_id)).toHaveText(pinnedText);
  await expect(a).toHaveAttribute('aria-pressed','true');
  await expect(detail.getByText(selectedDecision,{exact:true})).toBeVisible();
  await expect(otherInbox.getByTestId('conversation-'+inboxConversation)).toHaveAttribute('aria-pressed','true');
 }
 await showPinnedSource(other.conversation_id);

 const history='/api/v1/workspaces/'+owner.workspace_id+'/conversations/'+conversation+'/messages';
 await page.route(url=>url.pathname===history&&!url.searchParams.has('cursor'),route=>{
  const url=new URL(route.request().url());
  url.searchParams.set('limit','1');
  return route.continue({url:url.toString()});
 });
 const newHistory=page.waitForResponse(reply=>reply.request().method()==='GET'&&new URL(reply.url()).pathname===history);
 await openConversation(page,conversation);
 const firstPage=await newHistory;
 expect(firstPage.status()).toBe(200);
 const firstHistory=await firstPage.json();
 expect(firstHistory.items).toHaveLength(1);
 expect(firstHistory.items[0].message_id).not.toBe(pinned.message_id);
 expect(firstHistory.next_cursor).toBeTruthy();
 const older=await page.request.get(history+'?'+new URLSearchParams({limit:'25',cursor:firstHistory.next_cursor}));
 expect(older.status()).toBe(200);
 expect((await older.json()).items).toEqual(expect.arrayContaining([
  expect.objectContaining({message_id:pinned.message_id,conversation_id:conversation,text:pinnedText}),
 ]));
 await showPinnedSource(conversation);
 console.log('R1 Chromium '+info.project.name+' pinned source '+pinned.message_id+' read from '+other.conversation_id+
  ' and beyond first Inbox page in '+conversation+'; exact text and decision '+selectedDecision);

 await b.click();
 await detail.getByLabel('Пояснение или вопрос',{exact:true}).fill('Synthetic уточнение размера');
 const clarification=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===approvalPath(bId)+'/'+second.approval_id);
 await detail.getByRole('button',{name:'Запросить уточнение',exact:true}).click();
 const bResponse=await clarification;
 expect(bResponse.status()).toBe(200);
 const clarified=await bResponse.json() as ApprovalCard;
 expect(clarified).toMatchObject({status:'CLARIFICATION',decision:{authorized_action:null,terms:null}});
 await expect(detail.getByText('Запрошено уточнение',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 console.log('Q3 Chromium '+info.project.name+' A '+aId+' approval '+first.approval_id+
  ' decision '+decisions[0].card.decision!.decision_id+'; B '+bId+' approval '+second.approval_id+' clarification '+clarified.decision!.decision_id);
});

test('@narrow asks only for the missing term and retains its independent basis',async({page},info)=>{
 test.setTimeout(90_000);
 page.setDefaultTimeout(12_000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const rules=settings.getByRole('button',{name:/^Удалить правило \d+$/});
 for(let index=await rules.count()-1;index>=0;index--)await rules.nth(index).click();
 const priceMode=settings.getByLabel('Режим цены 1',{exact:true});
 const durationMode=settings.getByLabel('Режим длительности 1',{exact:true});
 const depositMode=settings.getByRole('combobox',{name:'Режим предоплаты 1',exact:true});
 await priceMode.selectOption('CONFIGURED_FORMULA');
 for(const [label,value] of [
  ['База, копейки 1','300000'],['За начатый шаг, копейки 1','50000'],
  ['Шаг размера, мм 1','10'],['Предел размера для цены, мм 1','1000'],
  ['Прибавка к верхней границе, копейки 1','50000'],
 ])await settings.getByLabel(label,{exact:true}).fill(value);
 await durationMode.selectOption('OWNER_DEFINED');
 await depositMode.selectOption('NONE');
 await settings.getByLabel('Предоплата, копейки 1',{exact:true}).fill('');
 await settings.getByLabel('Предоплата, процент 1',{exact:true}).fill('');
 await publishIntakeService(settings,serviceName);
 const {conversation,collected,intake}=await collectIntake(page,variant,'owner-decision-partial');
 await (await chooseWork(page,collected.message_id,'flower','forearm','20 mm','linework')).click();
 const work=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const cardId=work.getByTestId('service-request-id');
 await expect(cardId).toHaveText(/^[0-9a-f-]{36}$/);
 const id=(await cardId.textContent())!;
 const detail=page.getByRole('article',{name:'Карточка решения по заявке',exact:true});
 const endpoint='/api/v1/workspaces/'+owner.workspace_id+'/businesses/'+owner.business_id+'/intake/conversations/'+conversation+'/service-requests/'+id+'/approvals';
 async function clickAndRead(label:string,path=endpoint,container=detail){
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path);
  await container.getByRole('button',{name:label,exact:true}).click();
  const saved=await response;
  expect(saved.status()).toBe(200);
  return await saved.json() as ApprovalCard;
 }

 const rangeBasis=await clickAndRead('Открыть решение мастера',endpoint,work);
 const range={lower_minor:400000,upper_minor:450000,authority:'PROVISIONAL'};
 expect(rangeBasis.basis).toMatchObject({amount_minor:null,price_range:range,occupied_minutes:null,deposit:{mode:'NONE'}});
 const rangeText=/4\s000\s₽\s–\s4\s500\s₽\s·\sпредварительный диапазон/;
 await expect(detail).toContainText(rangeText);
 await expect(detail.getByLabel('Цена, ₽',{exact:true})).toHaveCount(0);
 await detail.getByLabel('Длительность следующего сеанса, мин',{exact:true}).fill('75');
 const rangeDecisionPath=endpoint+'/'+rangeBasis.approval_id;
 const firstWrite=page.waitForResponse(reply=>reply.request().method()==='POST'&&new URL(reply.url()).pathname===rangeDecisionPath);
 const rangeSaved=await clickAndRead('Подтвердить условия',rangeDecisionPath);
 const command=(await firstWrite).request();
 expect(command.postDataJSON()).toEqual({expected_version:'1',action:'PREPARE_QUOTE',operation:'APPROVE',occupied_minutes:75});
 expect(rangeSaved.decision).toMatchObject({submitted:{amount_minor:null,occupied_minutes:75},
  terms:{amount_minor:null,price_range:range,occupied_minutes:75,price_reference_id:rangeBasis.basis.price_calculation_id}});
 const replay=await page.request.post(rangeDecisionPath,{
  data:command.postDataJSON(),headers:{'X-CSRF-Token':command.headers()['x-csrf-token'],Origin:new URL(page.url()).origin},
 });
 expect(replay.status()).toBe(200);
 expect(await replay.json()).toEqual(rangeSaved);
 const reread=page.waitForResponse(reply=>reply.request().method()==='GET'&&new URL(reply.url()).pathname===rangeDecisionPath);
 await page.getByRole('button',{name:'Обновить решения по заявкам',exact:true}).click();
 const renewed=await reread;
 expect(renewed.status()).toBe(200);
 expect(await renewed.json()).toEqual(rangeSaved);
 const terms=detail.getByRole('region',{name:'Подтверждённые условия',exact:true});
 await expect(terms).toContainText(rangeText);
 await expect(terms).toContainText('75 мин');

 await priceMode.selectOption('FIXED');
 await settings.getByLabel('Цена, копейки 1',{exact:true}).fill('120001');
 await depositMode.selectOption('FULL_PREPAYMENT');
 await publishIntakeService(settings,serviceName);
 const priceBasis=await clickAndRead('Открыть решение мастера',endpoint,work);
 expect(priceBasis.basis).toMatchObject({amount_minor:120001,price_range:null,occupied_minutes:null,deposit:{mode:'FULL_PREPAYMENT'}});
 await expect(detail.getByLabel('Цена, ₽',{exact:true})).toHaveCount(0);
 await expect(detail).toContainText(/1\s200,01\s₽/);
 await detail.getByLabel('Длительность следующего сеанса, мин',{exact:true}).fill('80');
 const priceSaved=await clickAndRead('Подтвердить условия',endpoint+'/'+priceBasis.approval_id);
 expect(priceSaved.decision).toMatchObject({submitted:{amount_minor:null,occupied_minutes:80},
  terms:{amount_minor:120001,occupied_minutes:80,price_reference_id:priceBasis.basis.price_calculation_id}});
 await expect(detail.getByRole('region',{name:'Подтверждённые условия'})).toContainText('Полная предоплата');

 await settings.getByLabel('Цена, копейки 1',{exact:true}).fill('');
 await priceMode.selectOption('OWNER_QUOTE');
 await durationMode.selectOption('FIXED');
 await settings.getByLabel('Длительность, минуты 1',{exact:true}).fill('65');
 await publishIntakeService(settings,serviceName);
 const durationBasis=await clickAndRead('Открыть решение мастера',endpoint,work);
 expect(durationBasis.approval_id).not.toBe(priceBasis.approval_id);
 await expect(detail.getByLabel('Длительность следующего сеанса, мин',{exact:true})).toHaveCount(0);
 await expect(detail).toContainText('65 мин');
 await detail.getByLabel('Цена, ₽',{exact:true}).fill('4600');
 const durationSaved=await clickAndRead('Подтвердить условия',endpoint+'/'+durationBasis.approval_id);
 expect(durationSaved.decision).toMatchObject({submitted:{amount_minor:460000,occupied_minutes:null},
  terms:{amount_minor:460000,occupied_minutes:65,duration_reference_id:durationBasis.basis.assessment_id}});
 await expect(detail.getByRole('region',{name:'Подтверждённые условия'})).toContainText('Полная предоплата');
 await clickAndRead('Отозвать подтверждение',endpoint+'/'+durationBasis.approval_id);
 const next=await clickAndRead('Открыть новый запрос');
 await detail.getByLabel('Пояснение или вопрос',{exact:true}).fill('Synthetic отказ по сложности');
 const declined=await clickAndRead('Отказать по заявке',endpoint+'/'+next.approval_id);
 expect(declined).toMatchObject({status:'DECLINED',decision:{authorized_action:null,terms:null}});
 await expect(detail.getByText('Мастер отказал',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 console.log('R1 Chromium '+info.project.name+' RANGE 400000–450000 PROVISIONAL / 75; approval '+rangeSaved.approval_id+
  ' decision '+rangeSaved.decision!.decision_id+' calculation '+rangeBasis.basis.price_calculation_id+
  '; Q3-D 120001 / 80 FULL_PREPAYMENT decision '+priceSaved.decision!.decision_id);
});

type QuoteAttempt={quote_id:string;job_claimed:boolean;status:QuoteDelivery['status'];reason:string|null;calls:number;effects:number;text:string|null};

async function configureQuoteService(page:Page,variant:Viewport,journey:QuoteIntakeJourney){
 page.setDefaultTimeout(12000);
 const {settings,serviceName}=await configureIntakeService(page,variant);
 const rules=settings.getByRole('button',{name:/^Удалить правило \d+$/});
 for(let i=await rules.count()-1;i>=0;i--)await rules.nth(i).click();
 await settings.getByLabel('Режим цены 1',{exact:true}).selectOption('CONFIGURED_FORMULA');
 await settings.getByLabel('Режим длительности 1',{exact:true}).selectOption('FIXED');
 const fixedDeposit=journey==='quote-pilot';
 await settings.getByRole('combobox',{name:'Режим предоплаты 1',exact:true}).selectOption(fixedDeposit?'FIXED_DEPOSIT':'NONE');
 const range=journey==='quote-acceptance'||journey==='quote-clarification';
 for(const [label,value] of [
  ['База, копейки 1','250000'],['За начатый шаг, копейки 1','50000'],
  ['Шаг размера, мм 1','10'],['Предел размера для цены, мм 1',range?'1000':'100'],
  ['Прибавка к верхней границе, копейки 1',range?'50000':''],['Длительность, минуты 1','65'],
  ['Предоплата, копейки 1',fixedDeposit?'50000':''],['Предоплата, процент 1',''],
 ])await settings.getByLabel(label,{exact:true}).fill(value);
 await publishIntakeService(settings,serviceName);
 return {settings,serviceName};
}

async function beginQuoteJourney(page:Page,variant:Viewport,journey:QuoteIntakeJourney){
 const {settings,serviceName}=await configureQuoteService(page,variant,journey);
 const {input,conversation,collected,intake,inbox}=await collectIntake(page,variant,journey);
 const work=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const cardId=work.getByTestId('service-request-id');
 const panel=work.getByRole('region',{name:'Предложение клиенту',exact:true});
 const endpoint=`/api/v1/workspaces/${owner.workspace_id}/businesses/${owner.business_id}/intake/conversations/${conversation}/service-requests`;
 const history=`/api/v1/workspaces/${owner.workspace_id}/conversations/${conversation}/messages`;
 const execute=(operation:QuoteOperation,requestId:string,observe?: (checkpoint:DispatchCheckpoint)=>Promise<void>)=>
  intakeFixture<QuoteAttempt>(operation,journey,variant,conversation,requestId,observe);
 async function read(requestId:string, status?:QuoteDelivery['status']){
  const response=await page.request.get(`${endpoint}/${requestId}/quote`);
  expect(response.status()).toBe(200);
  const value=await response.json() as QuoteDelivery;
  if(status!==undefined)expect(value.status).toBe(status);
  return value;
 }
 async function readHistory(){
  const response=await page.request.get(history);
  expect(response.status()).toBe(200);
  return (await response.json() as {items:{message_id:string;direction:'INBOUND'|'OUTBOUND';text:string|null}[]}).items;
 }
 const price=work.getByRole('button',{name:/^(Рассчитать|Пересчитать) цену$/});
 const evaluate=work.getByRole('button',{name:/^(Оценить заявку|Пересчитать оценку)$/});
 async function evaluateAndPrice(requestId:string){
  await evaluate.click();
  await expect(work.getByRole('region',{name:'Оценка заявки',exact:true}).getByText('Выполнимо',{exact:true})).toBeVisible();
  await price.click();
  await expect(panel.getByRole('status')).toHaveText('Предложение в очереди на отправку');
  return (await read(requestId,'QUEUED')).quote!;
 }
 await (await chooseWork(page,collected.message_id,'flower','forearm','20 mm','linework')).click();
 await expect(cardId).toHaveText(/^[0-9a-f-]{36}$/);
 const firstId=(await cardId.textContent())!;
 return {input,conversation,collected,intake,inbox,settings,serviceName,work,cardId,panel,firstId,endpoint,execute,read,readHistory,evaluateAndPrice,price};
}

test('@narrow M6.4A-R2 binds a follow-up to the second work and preserves the excluded request',async({page},info)=>{
 test.setTimeout(120_000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const journey='quote-agent';
 const writes:string[]=[];
 page.on('request',request=>{
  const path=new URL(request.url()).pathname;
  if(path.split('/').includes('service-requests')&&request.method()!=='GET')writes.push(path);
 });
 await configureQuoteService(page,variant,journey);
 const {input,conversation,collected,intake}=await collectIntake(page,variant,journey);
 const endpoint=`/api/v1/workspaces/${owner.workspace_id}/businesses/${owner.business_id}/intake/conversations/${conversation}/service-requests`;
 const history=`/api/v1/workspaces/${owner.workspace_id}/conversations/${conversation}/messages`;
 const work=intake.getByRole('region',{name:'Черновик заявки',exact:true});
 const quotePanel=work.getByRole('region',{name:'Предложение клиенту',exact:true});
 async function readDraft(requestId:string){
  const response=await page.request.get(`${endpoint}?request_id=${requestId}`);
  expect(response.status()).toBe(200);
  return await response.json() as ServiceRequestDraft;
 }
 async function readQuote(requestId:string,status:QuoteDelivery['status']){
  const response=await page.request.get(`${endpoint}/${requestId}/quote`);
  expect(response.status()).toBe(200);
  const view=await response.json() as QuoteDelivery;
  expect(view.status).toBe(status);
  return view;
 }
 async function readHistory(){
  const response=await page.request.get(history);
  expect(response.status()).toBe(200);
  return (await response.json() as {items:{message_id:string;direction:string;text:string}[]}).items;
 }
 const deliver=(requestId:string)=>intakeFixture<QuoteAttempt>('deliver-quote',journey,variant,conversation,requestId);

 const a=collected.service_intents!;
 expect(a).toMatchObject({request_id:expect.any(String),approval_id:null,quote_id:expect.any(String)});
 await page.reload();
 await openWorkspace(page);
 const inbox=await openConversation(page,conversation);
 const requests=intake.getByLabel('Сохранённая заявка',{exact:true});
 async function showDraft(requestId:string,revision:string,source:string){
  await intake.getByRole('button',{name:'Обновить карточку заявки',exact:true}).click();
  await expect(requests.locator(`option[value="${requestId}"]`)).toHaveCount(1);
  await requests.selectOption(requestId);
  await expect(work.getByTestId('service-request-id')).toHaveText(requestId);
  await expect(work.getByTestId('service-request-revision')).toHaveText(revision);
  await expect(work.getByRole('link',{name:'Исходное сообщение',exact:true})).toHaveAttribute('href','#message-'+source);
 }
 await showDraft(a.request_id,'1',collected.message_id);
 const aDraft=await readDraft(a.request_id);
 const first=(await readQuote(a.request_id,'QUEUED')).quote!;
 expect(first).toMatchObject({quote_id:a.quote_id,material:{amount_minor:350000,occupied_minutes:65}});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение в очереди на отправку');
 const sentA=await deliver(a.request_id);
 expect(sentA).toMatchObject({quote_id:a.quote_id,calls:1,effects:1,status:'SENT',text:first.text});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение отправлено клиенту');

 const started=await input('agent-start-second',conversation);
 expect([started.model_calls,started.calls,started.effects,started.status]).toEqual([1,1,1,'CLARIFY']);
 const question='На каком месте тела вы хотите татуировку?';
 expect((await readHistory()).filter(message=>message.direction==='OUTBOUND'&&message.text===question)).toHaveLength(1);
 const completed=await input('agent-second',conversation);
 const b=completed.service_intents!;
 expect([completed.model_calls,completed.calls,completed.effects]).toEqual([1,0,0]);
 expect(b).toMatchObject({request_id:expect.any(String),approval_id:expect.any(String),quote_id:null});
 expect(b.request_id).not.toBe(a.request_id);
 expect(await readDraft(a.request_id)).toEqual(aDraft);
 const bDraft=await readDraft(b.request_id);
 expect(bDraft.revision).toBe('1');
 expect(bDraft.intent_source.message_id).toBe(started.message_id);
 expect(Object.fromEntries(bDraft.facts.map(fact=>[fact.field,fact.source.message_id]))).toEqual({
  idea:started.message_id,placement:completed.message_id,approximate_size:completed.message_id,style:completed.message_id,
 });

 const excluded=await input('agent-exclude-first',conversation);
 const clarification='Уточните, к какой услуге или отдельной идее относится сообщение.';
 expect([excluded.model_calls,excluded.calls,excluded.effects,excluded.status]).toEqual([1,1,1,'CLARIFY']);
 expect(excluded.service_intents).toBeUndefined();
 expect(await readDraft(a.request_id)).toEqual(aDraft);
 expect(await readDraft(b.request_id)).toEqual(bDraft);
 expect((await readQuote(a.request_id,'SENT')).quote).toEqual(first);
 expect((await readHistory()).filter(message=>message.direction==='OUTBOUND'&&message.text===clarification)).toHaveLength(1);

 const correction=await input('agent-correct-first',conversation);
 const revised=correction.service_intents!;
 expect(revised).toMatchObject({request_id:a.request_id,approval_id:null,quote_id:expect.any(String)});
 expect(await readDraft(b.request_id)).toEqual(bDraft);
 await refreshIntake(inbox,intake);
 await showDraft(a.request_id,'2',collected.message_id);
 const revisedDraft=await readDraft(a.request_id);
 expect(revisedDraft.facts.find(fact=>fact.field==='approximate_size')).toMatchObject({value:'21 мм',source:{message_id:correction.message_id}});
 expect(revisedDraft.facts.filter(fact=>fact.field!=='approximate_size')).toEqual(aDraft.facts.filter(fact=>fact.field!=='approximate_size'));
 await expect(work.getByRole('link',{name:'Сообщение для поля Примерный размер',exact:true})).toHaveAttribute('href','#message-'+correction.message_id);
 const updated=(await readQuote(a.request_id,'QUEUED')).quote!;
 expect(updated).toMatchObject({quote_id:revised.quote_id,version:'2',material:{amount_minor:400000,occupied_minutes:65}});
 const sentRevision=await deliver(a.request_id);
 expect(sentRevision).toMatchObject({quote_id:updated.quote_id,calls:1,effects:1,status:'SENT',text:updated.text});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение отправлено клиенту');

 await showDraft(b.request_id,'1',started.message_id);
 await expect(work.getByRole('link',{name:'Сообщение для поля Место',exact:true})).toHaveAttribute('href','#message-'+completed.message_id);
 const center=page.getByRole('region',{name:'Решения по заявкам',exact:true});
 await center.getByRole('button',{name:'Обновить решения по заявкам',exact:true}).click();
 const card=center.getByTestId('approval-'+b.approval_id);
 await expect(card).toContainText('Ожидает решения мастера');
 await card.click();
 const detail=center.getByTestId('approval-detail-'+b.approval_id);
 await expect(detail.getByRole('list',{name:'Проверенные сведения'})).toContainText('ласточка');
 await detail.getByRole('link',{name:'Исходная реплика заявки',exact:true}).click();
 await expect(detail.getByTestId('approval-source-'+started.message_id)).toHaveText('Отдельная татуировка: ласточка');
 const pending=await page.request.get(`/api/v1/workspaces/${owner.workspace_id}/service-approvals`);
 expect(pending.status()).toBe(200);
 expect((await pending.json() as {items:ApprovalCard[]}).items
  .filter(card=>card.conversation_id===conversation&&card.status==='PENDING')
  .map(card=>card.approval_id)).toEqual([b.approval_id]);
 const before=(await readHistory()).filter(message=>message.direction==='INBOUND');
 const decisionPath=`${endpoint}/${b.request_id}/approvals/${b.approval_id}`;
 const saved=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname===decisionPath);
 await detail.getByLabel('Цена, ₽',{exact:true}).fill('4600');
 await detail.getByRole('button',{name:'Подтвердить условия',exact:true}).click();
 const response=await saved;
 expect(response.status()).toBe(200);
 const approved=await response.json() as ApprovalCard;
 expect(approved.decision?.terms).toMatchObject({amount_minor:460000,occupied_minutes:65});
 const second=(await readQuote(b.request_id,'QUEUED')).quote!;
 expect(second.material).toMatchObject({request_id:b.request_id,price_reference_id:approved.decision!.decision_id});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение в очереди на отправку');
 const sentB=await deliver(b.request_id);
 expect(sentB).toMatchObject({quote_id:second.quote_id,calls:1,effects:1,status:'SENT',text:second.text});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение отправлено клиенту');
 await expect(quotePanel.getByTestId('quote-text')).toHaveText(second.text);
 await expect(work.getByRole('region',{name:'Согласованный заказ',exact:true})).toHaveCount(0);
 const messages=await readHistory();
 expect(messages.filter(message=>message.direction==='INBOUND')).toEqual(before);

 const separate=await input('agent-same-title',conversation);
 const c=separate.service_intents!;
 expect(new Set([a.request_id,b.request_id,c.request_id]).size).toBe(3);
 expect(c.approval_id).toBeNull();
 expect(await readDraft(a.request_id)).toEqual(revisedDraft);
 const cDraft=await readDraft(c.request_id);
 expect(cDraft.facts.find(fact=>fact.field==='placement')).toMatchObject({value:'плечо',source:{message_id:separate.message_id}});
 await refreshIntake(inbox,intake);
 await showDraft(c.request_id,'1',separate.message_id);
 const cQuote=(await readQuote(c.request_id,'QUEUED')).quote!;
 expect(cQuote).toMatchObject({quote_id:c.quote_id,material:{amount_minor:400000,occupied_minutes:65}});
 const sentC=await deliver(c.request_id);
 expect(sentC).toMatchObject({quote_id:cQuote.quote_id,calls:1,effects:1,status:'SENT',text:cQuote.text});
 await expect(quotePanel.getByRole('status')).toHaveText('Предложение отправлено клиенту');
 expect((await readHistory()).filter(message=>message.direction==='OUTBOUND').map(message=>message.text).sort()).toEqual([first.text,question,clarification,updated.text,second.text,cQuote.text].sort());
 expect(writes).toEqual([decisionPath]);
 console.log('M6.4A-R2 Chromium '+info.project.name+' '+JSON.stringify({
  conversation,
  excluded:{source:excluded.message_id,calls:excluded.calls,effects:excluded.effects},
  a:{request:a.request_id,source:collected.message_id,revision:revisedDraft.revision,correction:correction.message_id,quotes:[sentA.quote_id,sentRevision.quote_id],calls:sentA.calls+sentRevision.calls,effects:sentA.effects+sentRevision.effects},
  b:{request:b.request_id,source:started.message_id,completion:completed.message_id,revision:bDraft.revision,approval:b.approval_id,decision:approved.decision?.decision_id,quote:sentB.quote_id,calls:sentB.calls,effects:sentB.effects},
  c:{request:c.request_id,source:separate.message_id,revision:cDraft.revision,quote:sentC.quote_id,calls:sentC.calls,effects:sentC.effects},
  inboundAfterDecision:0,orders:0,
 }));
});

type QuoteJourney=Awaited<ReturnType<typeof beginQuoteJourney>>;
const dispatchingLabel='Отправка началась, ожидаем подтверждения';

async function takeoverQuote(page:Page,app:QuoteJourney,quote:RequestQuote,operation:QuoteOperation){
 const {panel,firstId,execute,read}=app;
 const controls=page.getByRole('region',{name:'Управление диалогом',exact:true});
 const checkpoints:DispatchCheckpoint[]=[];
 const result=await execute(operation,firstId,async checkpoint=>{
  expect([checkpoint.calls,checkpoint.effects]).toEqual(checkpoint.phase==='before_call'?[0,0]:[1,1]);
  if(checkpoint.phase==='before_finalize'){
   await controls.getByRole('button',{name:'Обновить режим',exact:true}).click();
   await controls.getByRole('button',{name:'Забрать управление',exact:true}).click();
   await expect(controls.getByText('Управление у мастера',{exact:true})).toBeVisible();
  }
  expect((await read(firstId,'DISPATCHING')).quote).toEqual(quote);
  await expect(panel.getByRole('status')).toHaveText(dispatchingLabel);
  expect(await panel.getByTestId('quote-text').textContent()).toBe(quote.text);
  checkpoints.push(checkpoint);
 });
 await expect(controls.getByText('Управление у мастера',{exact:true})).toBeVisible();
 return {result,checkpoints};
}

async function resumeQuote(page:Page){
 const controls=page.getByRole('region',{name:'Управление диалогом',exact:true});
 await controls.getByRole('button',{name:'Обновить режим',exact:true}).click();
 await controls.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();
 await expect(controls.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
}

async function confirmExactQuote(page:Page,app:QuoteJourney,previous:RequestQuote,status:'SENT'|'UNKNOWN',mode:'PERCENT_DEPOSIT'|'FULL_PREPAYMENT'){
 const {settings,serviceName,inbox,intake,work,panel,firstId,endpoint,price,read,execute}=app;
 if(!await settings.isVisible())await page.getByRole('button',{name:/Synthetic business/}).click();
 await settings.getByLabel('Прибавка к верхней границе, копейки 1',{exact:true}).fill('50000');
 await settings.getByRole('combobox',{name:'Режим предоплаты 1',exact:true}).selectOption(mode);
 if(mode==='PERCENT_DEPOSIT')await settings.getByLabel('Предоплата, процент 1',{exact:true}).fill('25');
 await publishIntakeService(settings,serviceName);
 await refreshIntake(inbox,intake);
 await work.getByRole('button',{name:/^(Оценить заявку|Пересчитать оценку)$/}).click();
 await expect(work.getByRole('region',{name:'Оценка заявки',exact:true}).getByText('Выполнимо',{exact:true})).toBeVisible();
 const calculated=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`${endpoint}/${firstId}/pricing`);
 await price.click();
 const calculation=await calculated;
 expect(calculation.status()).toBe(200);
 expect(await calculation.json()).toMatchObject({outcome:'RANGE',lower_minor:350000,upper_minor:400000});

 const priorStatus=status==='SENT'?'Предложение отправлено клиенту':'UNKNOWN · Доставка не подтверждена';
 const prior=panel.getByRole('region',{name:'Предыдущая версия',exact:true});
 await expect(panel.getByText('Нужно уточнение',{exact:true})).toBeVisible();
 await expect(panel.getByText(/^Уточните точную цену\./)).toBeVisible();
 await expect(prior.getByText(previous.code,{exact:true})).toBeVisible();
 await expect(prior.getByRole('status')).toHaveText(priorStatus);
 expect(await prior.getByTestId('quote-text').textContent()).toBe(previous.text);
 const blocked=await read(firstId,'NEEDS_CLARIFICATION');
 expect(blocked).toEqual({quote:null,status:'NEEDS_CLARIFICATION',reason:'EXACT_PRICE_REQUIRED',
  previous:{quote:previous,status,reason:status==='UNKNOWN'?'UNKNOWN_EXTERNAL_RESULT':null}});
 expect(await read(firstId,'NEEDS_CLARIFICATION')).toEqual(blocked);
 const checked=await execute('deliver-quote',firstId);
 expect(checked).toMatchObject({quote_id:previous.quote_id,status,job_claimed:false,calls:0,effects:0,text:null});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);

 if(status==='UNKNOWN')await resumeQuote(page);
 const approvalPath=`${endpoint}/${firstId}/approvals`;
 const opened=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===approvalPath);
 await work.getByRole('button',{name:'Открыть решение мастера',exact:true}).click();
 const approvalResponse=await opened;
 expect(approvalResponse.status()).toBe(200);
 const approval=await approvalResponse.json() as ApprovalCard;
 expect(approval.basis).toMatchObject({amount_minor:null,occupied_minutes:65,deposit:{mode},can_approve:true});
 const detail=page.getByRole('article',{name:'Карточка решения по заявке',exact:true});
 const decisionPath=`${approvalPath}/${approval.approval_id}`;
 const approved=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===decisionPath);
 await detail.getByLabel('Цена, ₽',{exact:true}).fill('3750');
 await detail.getByRole('button',{name:'Подтвердить условия',exact:true}).click();
 const decision=await approved;
 expect(decision.status()).toBe(200);
 const next=(await read(firstId,'QUEUED')).quote!;
 expect(next.version).toBe(String(Number(previous.version)+1));
 expect(next.quote_id).not.toBe(previous.quote_id);
 expect(next.code).not.toBe(previous.code);
 expect(next.material).toMatchObject({amount_minor:375000,occupied_minutes:65,deposit:{mode}});
 await expect(panel.getByTestId('quote-text')).toContainText(`Принимаю ${next.code}`);
 const delivered=await execute('deliver-quote',firstId);
 expect(delivered).toMatchObject({quote_id:next.quote_id,job_claimed:true,status:'SENT',calls:1,effects:1,text:next.text});
 await expect(panel.getByRole('status')).toHaveText('Предложение отправлено клиенту');
 expect((await read(firstId,'SENT')).quote).toEqual(next);
 const replay=await execute('deliver-quote',firstId);
 expect(replay).toMatchObject({quote_id:next.quote_id,status:'SENT',job_claimed:false,calls:0,effects:0,text:null});
 return {mode,previous:{id:previous.quote_id,code:previous.code,version:previous.version,status},checked,
  next:{id:next.quote_id,code:next.code,version:next.version},delivered,replay};
}

test('@narrow M6.3B sends each selected work once, including the later owner decision',async({page},info)=>{
 test.setTimeout(120000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const app=await beginQuoteJourney(page,variant,'quote-delivery');
 const {input,conversation,collected,intake,inbox,work,cardId,panel,firstId,endpoint,execute,read,readHistory,evaluateAndPrice,price}=app;
 const a=await evaluateAndPrice(firstId);
 expect(a.material).toMatchObject({request_id:firstId,conversation_id:conversation,amount_minor:350000,occupied_minutes:65,
  intent_source:{message_id:collected.message_id},decision_id:null});
 expect(a.material.price_reference_id).toBe(a.material.price_calculation_id);
 expect(a.material.duration_reference_id).toBe(a.material.assessment_id);
 const {result:deliveredA,checkpoints}=await takeoverQuote(page,app,a,'deliver-quote');
 expect(deliveredA).toMatchObject({quote_id:a.quote_id,job_claimed:true,status:'SENT',calls:1,effects:1,text:a.text});
 await expect(panel.getByRole('status')).toHaveText('Предложение отправлено клиенту');
 expect(await panel.getByTestId('quote-text').textContent()).toBe(a.text);
 const repeatA=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`${endpoint}/${firstId}/pricing`);
 await price.click();
 expect((await repeatA).status()).toBe(200);
 expect((await read(firstId,'SENT')).quote).toEqual(a);
 const replayA=await execute('deliver-quote',firstId);
 expect(replayA).toMatchObject({quote_id:a.quote_id,job_claimed:false,status:'SENT',calls:0,effects:0,text:null});
 await resumeQuote(page);

 const second=await input('quote-second',conversation);
 expect(second.status).toBe('PRELIMINARILY_COMPLETE');
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,second.message_id,'swallow','shoulder','101 mm','linework')).click();
 await expect(cardId).not.toHaveText(firstId);
 const secondId=(await cardId.textContent())!;
 expect((await read(secondId)).quote).toBeNull();
 const beforeB=(await readHistory()).filter(m=>m.direction==='INBOUND').map(m=>m.message_id);
 const approvalPath=`${endpoint}/${secondId}/approvals`;
 const opened=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===approvalPath);
 await work.getByRole('button',{name:'Открыть решение мастера',exact:true}).click();
 const openResponse=await opened;
 expect(openResponse.status()).toBe(200);
 const approval=await openResponse.json() as ApprovalCard;
 expect(approval.basis).toMatchObject({intent_source:{message_id:second.message_id},amount_minor:null,price_reason:'SIZE_OUTSIDE_RULE',occupied_minutes:65,can_approve:true});
 const detail=page.getByRole('article',{name:'Карточка решения по заявке',exact:true});
 const savedPath=approvalPath+'/'+approval.approval_id;
 const decision=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===savedPath);
 await detail.getByLabel('Цена, ₽',{exact:true}).fill('4600');
 await detail.getByRole('button',{name:'Подтвердить условия',exact:true}).click();
 const saved=await decision;
 expect(saved.status()).toBe(200);
 const approved=await saved.json() as ApprovalCard;
 expect(approved.decision?.terms).toMatchObject({amount_minor:460000,occupied_minutes:65});
 await expect(panel.getByRole('status')).toHaveText('Предложение в очереди на отправку');
 await expect(work.getByRole('button',{name:/^Отправить/})).toHaveCount(0);
 const b=(await read(secondId,'QUEUED')).quote!;
 expect(b.material).toMatchObject({request_id:secondId,conversation_id:conversation,amount_minor:460000,occupied_minutes:65,
  intent_source:{message_id:second.message_id},price_reference_id:approved.decision?.decision_id,
  duration_reference_id:approval.basis.assessment_id});
 expect(b.quote_id).not.toBe(a.quote_id);
 expect(b.code).not.toBe(a.code);
 expect(a.text).toContain('Идея — flower');
 expect(b.text).toContain('Идея — swallow');
 expect(a.text.endsWith(`\nПринимаю ${a.code}`)).toBe(true);
 expect(b.text.endsWith(`\nПринимаю ${b.code}`)).toBe(true);
 const deliveredB=await execute('deliver-quote',secondId);
 expect(deliveredB).toMatchObject({quote_id:b.quote_id,job_claimed:true,status:'SENT',calls:1,effects:1,text:b.text});
 await expect(panel.getByRole('status')).toHaveText('Предложение отправлено клиенту');
 expect(await panel.getByTestId('quote-text').textContent()).toBe(b.text);
 await panel.getByText('Источники условий',{exact:true}).click();
 await expect(panel.getByText(approved.decision!.decision_id,{exact:true})).toBeVisible();
 const command=saved.request();
 const repeated=await page.request.post(savedPath,{
  data:command.postDataJSON(),headers:{'X-CSRF-Token':command.headers()['x-csrf-token'],Origin:new URL(page.url()).origin},
 });
 expect(repeated.status()).toBe(200);
 expect(await repeated.json()).toEqual(approved);
 expect((await read(secondId,'SENT')).quote).toEqual(b);
 const replayB=await execute('deliver-quote',secondId);
 expect(replayB).toMatchObject({quote_id:b.quote_id,job_claimed:false,status:'SENT',calls:0,effects:0,text:null});

 const messages=await readHistory();
 expect(messages.filter(m=>m.direction==='INBOUND').map(m=>m.message_id)).toEqual(beforeB);
 for(const quote of [a,b])expect(messages.filter(m=>m.direction==='OUTBOUND'&&m.text===quote.text)).toHaveLength(1);
 await intake.getByLabel('Сохранённая заявка',{exact:true}).selectOption(firstId);
 await expect(panel.getByTestId('quote-text')).toContainText(`Принимаю ${a.code}`);
 expect(await panel.getByTestId('quote-text').textContent()).toBe(a.text);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 const clarification=variant==='desktop'?await confirmExactQuote(page,app,a,'SENT','PERCENT_DEPOSIT'):null;
 console.log('M6.3B R1 Chromium '+info.project.name+' '+JSON.stringify({conversation,checkpoints,clarification,
  a:{request:firstId,code:a.code,delivered:deliveredA,replay:replayA},b:{request:secondId,code:b.code,delivered:deliveredB,replay:replayB},
  inboundAfterApproval:0}));
});

test('@narrow M6.3B shows a takeover hold and an unconfirmed delivery after restart',async({page},info)=>{
 test.setTimeout(120000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const app=await beginQuoteJourney(page,variant,'quote-guard');
 const {conversation,intake,inbox,settings,serviceName,panel,firstId,execute,read,evaluateAndPrice}=app;
 const initial=await evaluateAndPrice(firstId);
 const controls=page.getByRole('region',{name:'Управление диалогом',exact:true});
 await controls.getByRole('button',{name:'Обновить режим',exact:true}).click();
 await controls.getByRole('button',{name:'Забрать управление',exact:true}).click();
 await expect(controls.getByText('Управление у мастера',{exact:true})).toBeVisible();
 const held=await execute('deliver-quote',firstId);
 expect(held).toMatchObject({quote_id:initial.quote_id,status:'HELD',reason:'HUMAN_CONTROL',calls:0,effects:0,text:null});
 await intake.getByRole('button',{name:'Обновить карточку заявки',exact:true}).click();
 await expect(panel.getByRole('status')).toHaveText('Отправка удержана');
 await expect(panel.getByText('Управление диалогом у мастера.',{exact:true})).toBeVisible();

 await resumeQuote(page);
 await settings.getByLabel('Прибавка к верхней границе, копейки 1',{exact:true}).fill('50000');
 await publishIntakeService(settings,serviceName);
 await refreshIntake(inbox,intake);
 const range=await evaluateAndPrice(firstId);
 expect(range.quote_id).not.toBe(initial.quote_id);
 expect(range.material.price_range).toEqual({authority:'PROVISIONAL',lower_minor:350000,upper_minor:400000});
 expect(range.text).toContain('Предварительный диапазон цены — 3\u202f500–4\u202f000 ₽.');
 const {result:unknown,checkpoints}=await takeoverQuote(page,app,range,'lose-quote-ack');
 expect(unknown).toMatchObject({quote_id:range.quote_id,job_claimed:true,status:'UNKNOWN',reason:'UNKNOWN_EXTERNAL_RESULT',calls:1,effects:1,text:range.text});
 const restarted=await execute('deliver-quote',firstId);
 expect(restarted).toMatchObject({quote_id:range.quote_id,job_claimed:false,status:'UNKNOWN',calls:0,effects:0,text:null});
 await page.reload();
 await openWorkspace(page);
 await openConversation(page,conversation);
 expect((await read(firstId,'UNKNOWN')).quote).toEqual(range);
 await expect(panel.getByRole('status')).toHaveText('UNKNOWN · Доставка не подтверждена');
 await expect(panel.getByText('Сообщение могло быть доставлено. Автоматический повтор отключён.',{exact:true})).toBeVisible();
 expect(await panel.getByTestId('quote-text').textContent()).toBe(range.text);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 const clarification=variant==='narrow'?await confirmExactQuote(page,app,range,'UNKNOWN','FULL_PREPAYMENT'):null;
 console.log('M6.3B R1 Chromium '+info.project.name+' '+JSON.stringify({conversation,request:firstId,held,checkpoints,unknown,restarted,clarification}));
});

test('@narrow M6.3C agrees B before A and preserves the first reply and planned session',async({page,context},info)=>{
 test.setTimeout(120_000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const journey='quote-acceptance';
 const {input,conversation,intake,inbox,cardId,panel,firstId,endpoint,execute,read,readHistory,evaluateAndPrice}=await beginQuoteJourney(page,variant,journey);
 const reply=(operation:QuoteReply,id:string)=>intakeFixture<QuoteReplyResult>(operation,journey,variant,conversation,id);
 const a=await evaluateAndPrice(firstId);
 expect(await execute('deliver-quote',firstId)).toMatchObject({status:'SENT',calls:1,effects:1});
 const second=await input('quote-second',conversation);
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,second.message_id,'swallow','shoulder','101 mm','linework')).click();
 await expect(cardId).not.toHaveText(firstId);
 const secondId=(await cardId.textContent())!;
 const b=await evaluateAndPrice(secondId);
 expect(await execute('deliver-quote',secondId)).toMatchObject({status:'SENT',calls:1,effects:1});
 expect(a.code).not.toBe(b.code);

 const ambiguous=await reply('ambiguous-agreement',secondId);
 expect(ambiguous).toMatchObject({outcome:'NEEDS_CLARIFICATION',acceptance_id:null,order_id:null,session_id:null});
 await refreshIntake(inbox,intake);
 await expect(panel.getByText(/Уточните, какое предложение он принимает/)).toBeVisible();
 expect((await read(firstId)).agreement).toBeUndefined();
 expect((await read(secondId)).agreement).toBeUndefined();

 const agreedB=await reply('agree-quote',secondId);
 expect(agreedB).toMatchObject({outcome:'ACCEPTED',quote_id:b.quote_id,source_message_id:agreedB.message_id});
 const savedB=(await read(secondId)).agreement!;
 expect(savedB).toMatchObject({acceptance_id:agreedB.acceptance_id,order_id:agreedB.order_id,session_id:agreedB.session_id,
  status:'PLANNED',scheduled_at:null,quote:b,source:{message_id:agreedB.message_id,status:'AVAILABLE',text:'Принимаю '+b.code}});
 expect(savedB.quote.material.price_range).toEqual({authority:'PROVISIONAL',lower_minor:800000,upper_minor:850000});
 await refreshIntake(inbox,intake);
 const order=panel.getByRole('region',{name:'Согласованный заказ',exact:true});
 await expect(order.getByTestId('service-order-id')).toHaveText(savedB.order_id);
 await expect(order.getByText(/Запланирован без даты · 65 мин/)).toBeVisible();
 await order.getByRole('link',{name:'Первая подтверждающая реплика'}).click();
 await expect(order.getByText('Принимаю '+b.code,{exact:true})).toBeVisible();
 await order.getByText('Принятые условия · '+b.code,{exact:true}).click();
 await expect(order.getByTestId('quote-text')).toHaveText(b.text);
 const retry=await reply('repeat-agreement',secondId);
 expect(retry).toMatchObject({acceptance_id:savedB.acceptance_id,order_id:savedB.order_id,session_id:savedB.session_id,
  source_message_id:agreedB.message_id});
 expect(retry.message_id).not.toBe(agreedB.message_id);
 expect((await read(secondId)).agreement).toEqual(savedB);

 await intake.getByLabel('Сохранённая заявка',{exact:true}).selectOption(firstId);
 await expect(panel.getByTestId('quote-text')).toContainText(a.code);
 await expect(order).toHaveCount(0);
 expect((await read(firstId)).agreement).toBeUndefined();
 const agreedA=await reply('agree-quote',firstId);
 const savedA=(await read(firstId)).agreement!;
 expect(savedA).toMatchObject({acceptance_id:agreedA.acceptance_id,order_id:agreedA.order_id,session_id:agreedA.session_id,
  status:'PLANNED',scheduled_at:null,quote:a,source:{message_id:agreedA.message_id}});
 expect(new Set([savedA.acceptance_id,savedA.order_id,savedA.session_id,savedB.acceptance_id,savedB.order_id,savedB.session_id]).size).toBe(6);
 await refreshIntake(inbox,intake);
 await expect(order.getByTestId('service-order-id')).toHaveText(savedA.order_id);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 console.log('M6.3C Chromium '+info.project.name+' '+JSON.stringify({conversation,a:agreedA,b:agreedB,retry,ambiguous:ambiguous.outcome,scheduledAt:null}));

 if(variant==='narrow')await test.step('M7.1A-R1 keeps the saved calendar across two work cards',async()=>{
  const beforeOutbound=(await readHistory()).filter(item=>item.direction==='OUTBOUND').map(item=>item.message_id);
  const requests=intake.getByLabel('Сохранённая заявка',{exact:true});

  function calendar(tab:Page,agreement:NonNullable<QuoteDelivery['agreement']>){
   const card=tab.getByRole('region',{name:'Согласованный заказ',exact:true});
   const availability=card.getByRole('region',{name:'Варианты времени выбранного сеанса',exact:true});
   const dateInput=availability.getByLabel('Дата вариантов',{exact:true});
   const slots=availability.getByRole('list',{name:'Подходящие окна'}).getByRole('listitem');
   const material=agreement.quote.material;
   const path=`${endpoint}/${material.request_id}/sessions/${agreement.session_id}/availability`;
   const matches=(request:Request)=>new URL(request.url()).pathname===path;
   const working=availability.getByRole('group',{name:'Рабочая неделя',exact:true});
   const policy=availability.getByRole('group',{name:'Настройки подбора времени',exact:true});
   const hours=availability.getByRole('group',{name:'Часы на выбранную дату',exact:true});

   async function action(method:'GET'|'POST',click:()=>Promise<unknown>){
    const [response]=await Promise.all([tab.waitForResponse(response=>matches(response.request())&&response.request().method()===method),click()]);
    expect(response.status()).toBe(200);
    const query=new URL(response.url()).searchParams;
    expect(Object.fromEntries(query)).toMatchObject({client_id:material.client_id,quote_id:agreement.quote.quote_id,order_id:agreement.order_id});
    const view=await response.json() as Availability;
    expect(view).toMatchObject({request_id:material.request_id,quote_id:agreement.quote.quote_id,order_id:agreement.order_id,
     session_id:agreement.session_id,occupied_minutes:65,duration_reference_id:material.duration_reference_id});
    await expect(dateInput).toHaveValue(view.date);
    return view;
   }

   async function open(){
    await expect(card.getByTestId('service-order-id')).toHaveText(agreement.order_id);
    await expect(card.getByTestId('service-session-id')).toHaveText(agreement.session_id);
    return action('GET',()=>card.getByRole('button',{name:'Варианты времени',exact:true}).click());
   }

   async function selectDate(date:string){
    return action('GET',async()=>{
     if(await dateInput.inputValue()===date)await availability.getByRole('button',{name:'Обновить варианты',exact:true}).click();
     else await dateInput.fill(date);
    });
   }

   async function setHours(start:string,end:string){
    if(!await hours.isVisible())await availability.getByText('Задать часы на эту дату',{exact:true}).click();
    if(!await hours.getByLabel('Начало',{exact:true}).count())await hours.getByRole('button',{name:'Добавить интервал',exact:true}).click();
    await hours.getByLabel('Начало',{exact:true}).fill(start);
    await hours.getByLabel('Окончание',{exact:true}).fill(end);
   }

   async function rejectStale(old:Availability,click:()=>Promise<unknown>){
    const sequence:string[]=[];
    const record=(request:Request)=>{if(matches(request))sequence.push(request.method());};
    tab.on('request',record);
    try{
     const [write,fresh]=await Promise.all([
      tab.waitForResponse(response=>matches(response.request())&&response.request().method()==='POST'),
      tab.waitForResponse(response=>matches(response.request())&&response.request().method()==='GET'),
      click(),
     ]);
     expect(write.status()).toBe(409);
     expect(await write.json()).toEqual({error:{code:'STALE_STATE'}});
     expect(write.request().postDataJSON().expected_version).toBe(old.schedule_version);
     expect(fresh.status()).toBe(200);
     expect(new URL(fresh.url()).searchParams.get('date')).toBe(old.date);
     const view=await fresh.json() as Availability;
     expect(view.schedule_version).toBeGreaterThan(old.schedule_version);
     await expect(availability.getByRole('alert')).toHaveText('Расписание уже изменилось. Проверьте сохранённые значения перед новой правкой.');
     expect(sequence).toEqual(['POST','GET']);
     return {view,proof:{status:write.status(),expectedVersion:old.schedule_version,savedVersion:view.schedule_version,sequence}};
    }finally{tab.off('request',record);}
   }

   return {availability,slots,working,policy,hours,open,selectDate,setHours,action,rejectStale};
  }

  const aCalendar=calendar(page,savedA);
  const initial=await aCalendar.open();
  expect(initial).toMatchObject({reason:'NO_WORKING_HOURS',windows:[],schedule_version:0});
  await expect(aCalendar.availability.getByText('Рабочие часы на эту дату не заданы.',{exact:true})).toBeVisible();
  function nextDate(days:number){
   const day=new Date(`${initial.date}T00:00:00Z`);
   day.setUTCDate(day.getUTCDate()+days);
   return {date:day.toISOString().slice(0,10),weekday:(day.getUTCDay()+6)%7};
  }
  const first=nextDate(1),second=nextDate(2),unscheduled=nextDate(3);
  const {date}=first,otherDate=second.date;
  await aCalendar.selectDate(date);

  await aCalendar.working.getByLabel('Часовой пояс',{exact:true}).fill('Asia/Novosibirsk');
  for(const [index,day] of [first,second].entries()){
   await aCalendar.working.getByRole('button',{name:'Добавить интервал',exact:true}).click();
   const row=aCalendar.working.getByRole('group',{name:`Интервал ${index+1}`,exact:true});
   await row.getByRole('combobox',{name:'День недели',exact:true}).selectOption(String(day.weekday));
   await row.getByLabel('Начало',{exact:true}).fill('10:00');
   await row.getByLabel('Окончание',{exact:true}).fill('12:00');
  }
  const activate=(ui:typeof aCalendar)=>ui.policy.getByRole('button',{name:'Активировать правила',exact:true}).click();
  const saveWeek=(ui:typeof aCalendar)=>ui.working.getByRole('button',{name:'Сохранить рабочие часы',exact:true}).click();
  const saveDate=(ui:typeof aCalendar)=>ui.hours.getByRole('button',{name:'Сохранить часы на дату',exact:true}).click();
  const schedule=await aCalendar.action('POST',()=>saveWeek(aCalendar));
  expect(schedule).toMatchObject({reason:'NO_ACTIVE_POLICY',windows:[],timezone:'Asia/Novosibirsk',date});
  await expect(aCalendar.availability.getByText('Активируйте правила подбора времени для этой услуги.',{exact:true})).toBeVisible();

  await aCalendar.availability.getByText('Правила подбора времени',{exact:true}).click();
  for(const [label,value] of [
   ['Шаг начала, мин','15'],['Буфер до сеанса, мин','10'],['Буфер после сеанса, мин','5'],
   ['Минимальное предупреждение, мин','60'],['Горизонт, дни','7'],['Срок варианта, мин','30'],['Срок удержания, мин','20'],
  ])await aCalendar.policy.getByLabel(label,{exact:true}).fill(value);
  const opened=await aCalendar.action('POST',()=>activate(aCalendar));
  expect(opened.windows.map(window=>window.visit_start)).toEqual(['10:15','10:30','10:45'].map(start=>`${date}T${start}:00+07:00`));
  expect(opened.windows[0]).toEqual({visit_start:`${date}T10:15:00+07:00`,visit_end:`${date}T11:20:00+07:00`,
   busy_start:`${date}T10:05:00+07:00`,busy_end:`${date}T11:25:00+07:00`});
  await expect(aCalendar.slots).toHaveCount(3);
  await expect(aCalendar.slots.first()).toContainText('Визит 10:15–11:20');
  await expect(aCalendar.slots.first()).toContainText('Занятость 10:05–11:25');
  await expect(aCalendar.availability.getByText('Asia/Novosibirsk',{exact:true})).toBeVisible();

  const bTab=await context.newPage();
  await bTab.goto('/');
  await openWorkspace(bTab);
  await openConversation(bTab,conversation);
  await bTab.getByLabel('Сохранённая заявка',{exact:true}).selectOption(secondId);
  const bCalendar=calendar(bTab,savedB);
  await bCalendar.open();
  const secondWork=await bCalendar.selectDate(date);
  expect(secondWork.schedule_version).toBe(opened.schedule_version);
  expect(secondWork.windows).toEqual(opened.windows);
  expect(secondWork.duration_reference_id).not.toBe(opened.duration_reference_id);
  await expect(bCalendar.availability.getByText('swallow',{exact:true})).toBeVisible();

  await bCalendar.setHours('10:00','12:30');
  const closed=await aCalendar.action('POST',()=>aCalendar.availability.getByRole('button',{name:'Отметить выходной',exact:true}).click());
  expect(closed).toMatchObject({date,reason:'DATE_CLOSED',windows:[],exception:{date,windows:[]}});
  await expect(aCalendar.availability.getByText('На эту дату отмечен выходной.',{exact:true})).toBeVisible();
  const staleDate=await bCalendar.rejectStale(secondWork,()=>saveDate(bCalendar));
  expect(staleDate.view).toMatchObject({date,schedule_version:closed.schedule_version,reason:'DATE_CLOSED',windows:[],exception:{date,windows:[]}});
  await expect(bCalendar.availability.getByText('На эту дату отмечен выходной.',{exact:true})).toBeVisible();
  await expect(bCalendar.slots).toHaveCount(0);

  await page.reload();
  await openWorkspace(page);
  await openConversation(page,conversation);
  await requests.selectOption(firstId);
  await aCalendar.open();
  expect(await aCalendar.selectDate(date)).toMatchObject({date,reason:'DATE_CLOSED',windows:[]});
  await expect(aCalendar.availability.getByText('На эту дату отмечен выходной.',{exact:true})).toBeVisible();
  await expect(aCalendar.slots).toHaveCount(0);
  const other=await aCalendar.selectDate(otherDate);
  expect(other.windows.map(window=>window.visit_start.slice(11,16))).toEqual(['10:15','10:30','10:45']);
  await expect(aCalendar.slots).toHaveCount(3);

  const noHours=await aCalendar.selectDate(unscheduled.date);
  expect(noHours).toMatchObject({reason:'NO_WORKING_HOURS',policy:{policy_id:opened.policy!.policy_id},exception:null,windows:[]});
  await expect(aCalendar.availability.getByText('Рабочие часы на эту дату не заданы.',{exact:true})).toBeVisible();
  await aCalendar.setHours('10:00','12:00');
  const replaced=await aCalendar.action('POST',()=>saveDate(aCalendar));
  expect(replaced.windows.map(window=>window.visit_start.slice(11,16))).toEqual(['10:15','10:30','10:45']);
  await aCalendar.setHours('10:00','10:30');
  const short=await aCalendar.action('POST',()=>saveDate(aCalendar));
  expect(short).toMatchObject({reason:'NO_WINDOWS',windows:[]});
  await expect(aCalendar.availability.getByText('Подходящих окон на эту дату нет.',{exact:true})).toBeVisible();
  await aCalendar.selectDate(date);
  const oldWeek=await bCalendar.selectDate(date);

  const weekRow=(ui:typeof aCalendar,day:number)=>ui.working.getByRole('group',{
   name:`Интервал ${oldWeek.week.findIndex(interval=>interval.weekday===day)+1}`,exact:true,
  });
  for(const ui of [aCalendar,bCalendar]){
   if(!await ui.working.isVisible())await ui.availability.getByText('Рабочие часы',{exact:true}).click();
  }
  await weekRow(bCalendar,second.weekday).getByLabel('Окончание',{exact:true}).fill('12:30');
  await bCalendar.working.getByLabel('Часовой пояс',{exact:true}).fill('UTC');
  await weekRow(aCalendar,first.weekday).getByLabel('Окончание',{exact:true}).fill('11:00');
  const savedWeek=await aCalendar.action('POST',()=>saveWeek(aCalendar));
  const staleWeek=await bCalendar.rejectStale(oldWeek,()=>saveWeek(bCalendar));
  expect(staleWeek.view).toMatchObject({timezone:savedWeek.timezone,week:savedWeek.week,schedule_version:savedWeek.schedule_version,reason:'DATE_CLOSED'});
  if(!await bCalendar.working.isVisible())await bCalendar.availability.getByText('Рабочие часы',{exact:true}).click();
  await expect(bCalendar.working.getByLabel('Часовой пояс',{exact:true})).toHaveValue('Asia/Novosibirsk');
  await expect(weekRow(bCalendar,first.weekday).getByLabel('Окончание',{exact:true})).toHaveValue('11:00');
  await expect(weekRow(bCalendar,second.weekday).getByLabel('Окончание',{exact:true})).toHaveValue('12:00');

  for(const ui of [aCalendar,bCalendar])await ui.availability.getByText('Правила подбора времени',{exact:true}).click();
  await bCalendar.policy.getByLabel('Буфер после сеанса, мин',{exact:true}).fill('12');
  await aCalendar.policy.getByLabel('Буфер до сеанса, мин',{exact:true}).fill('25');
  const savedPolicy=await aCalendar.action('POST',()=>activate(aCalendar));
  const stalePolicy=await bCalendar.rejectStale(staleWeek.view,()=>activate(bCalendar));
  expect(stalePolicy.view).toMatchObject({policy:savedPolicy.policy,schedule_version:savedPolicy.schedule_version,reason:'DATE_CLOSED'});
  if(!await bCalendar.policy.isVisible())await bCalendar.availability.getByText('Правила подбора времени',{exact:true}).click();
  await expect(bCalendar.policy.getByLabel('Буфер до сеанса, мин',{exact:true})).toHaveValue('25');
  await expect(bCalendar.policy.getByLabel('Буфер после сеанса, мин',{exact:true})).toHaveValue('5');
  await expect(bCalendar.slots).toHaveCount(0);
  expect((await read(firstId)).agreement).toEqual(savedA);
  expect((await read(secondId)).agreement).toEqual(savedB);

  await removeHistoricalDuration(b.quote_id);
  const [historical]=await Promise.all([
   page.waitForResponse(response=>response.request().method()==='GET'&&new URL(response.url()).pathname===`${endpoint}/${secondId}/quote`),
   requests.selectOption(secondId),
  ]);
  expect(historical.status()).toBe(409);
  expect(await historical.json()).toEqual({error:{code:'DURATION_UNAVAILABLE'}});
  await expect(panel.getByRole('alert')).toHaveText('Длительность согласованного сеанса не подтверждена.');
  await expect(panel.getByRole('button',{name:'Варианты времени',exact:true})).toHaveCount(0);
  await expect(panel.getByRole('list',{name:'Подходящие окна'})).toHaveCount(0);
  expect((await readHistory()).filter(item=>item.direction==='OUTBOUND').map(item=>item.message_id)).toEqual(beforeOutbound);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  console.log('M7.1A-R1 Chromium narrow '+JSON.stringify({conversation,dates:{date,otherDate,withoutHours:unscheduled.date},
   a:{request:firstId,quote:a.quote_id,order:savedA.order_id,session:savedA.session_id,duration_source:opened.duration_reference_id},
   b:{request:secondId,quote:b.quote_id,order:savedB.order_id,session:savedB.session_id,duration_source:secondWork.duration_reference_id},
   before:opened.windows,closed:closed.windows,other:other.windows,
   staleDate:staleDate.proof,staleWeek:{...staleWeek.proof,timezone:staleWeek.view.timezone,week:staleWeek.view.week},
   stalePolicy:{...stalePolicy.proof,policy:stalePolicy.view.policy},
   withoutHours:noHours.reason,replacement:replaced.windows,shortDay:short.reason,
   historical:{status:historical.status(),reason:'DURATION_UNAVAILABLE',windows:0},newOutgoing:0,scheduledAt:null}));
  await bTab.close();
 });
});

test('@narrow M6.3C-R1 keeps A declined and asks for the code only on open B',async({page},info)=>{
 test.setTimeout(120_000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const journey='quote-clarification';
 const {input,conversation,intake,inbox,cardId,panel,firstId,execute,read,evaluateAndPrice}=await beginQuoteJourney(page,variant,journey);
 const reply=(operation:QuoteReply,id:string)=>intakeFixture<QuoteReplyResult>(operation,journey,variant,conversation,id);
 const a=await evaluateAndPrice(firstId);
 expect(await execute('deliver-quote',firstId)).toMatchObject({status:'SENT',calls:1,effects:1});
 const other=await input('quote-second',conversation);
 await refreshIntake(inbox,intake);
 await (await chooseWork(page,other.message_id,'swallow','shoulder','101 mm','linework')).click();
 await expect(cardId).not.toHaveText(firstId);
 const secondId=(await cardId.textContent())!;
 const b=await evaluateAndPrice(secondId);
 expect(a.code).not.toBe(b.code);
 const requests=intake.getByLabel('Сохранённая заявка',{exact:true});
 await requests.selectOption(firstId);
 await expect(panel.getByTestId('quote-text')).toContainText(a.code);
 const decline=await reply('decline-quote',firstId);
 expect(decline).toMatchObject({outcome:'DECLINED',quote_id:a.quote_id});
 const declined=panel.getByRole('status').filter({hasText:'Клиент отклонил предложение.'});
 const clarify=panel.getByRole('status').filter({hasText:'Уточните, какое предложение он принимает'});
 const source=panel.getByRole('link',{name:'Ответ клиента',exact:true});
 const order=panel.getByRole('region',{name:'Согласованный заказ',exact:true});
 const closedYes=await reply('ambiguous-agreement',firstId);
 expect(closedYes).toMatchObject({outcome:null,order_id:null});
 await refreshIntake(inbox,intake);
 await expect(declined).toBeVisible();
 await expect(clarify).toHaveCount(0);
 await expect(source).toHaveAttribute('href','#message-'+decline.message_id);
 await expect(order).toHaveCount(0);

 await requests.selectOption(secondId);
 await expect(panel.getByTestId('quote-text')).toContainText(b.code);
 expect(await execute('deliver-quote',secondId)).toMatchObject({status:'SENT',calls:1,effects:1});
 const bBefore=await read(secondId,'SENT');
 expect(bBefore.reply_notice).toBeUndefined();
 const openYes=await reply('ambiguous-agreement',secondId);
 expect(openYes).toMatchObject({outcome:'NEEDS_CLARIFICATION',acceptance_id:null,order_id:null,session_id:null});
 await refreshIntake(inbox,intake);
 await expect(clarify).toBeVisible();
 await expect(declined).toHaveCount(0);
 await expect(source).toHaveAttribute('href','#message-'+openYes.message_id);
 await expect(order).toHaveCount(0);

 await requests.selectOption(firstId);
 await expect(panel.getByTestId('quote-text')).toContainText(a.code);
 await expect(declined).toBeVisible();
 await expect(clarify).toHaveCount(0);
 await expect(source).toHaveAttribute('href','#message-'+decline.message_id);
 await expect(order).toHaveCount(0);
 const [aView,bView]=await Promise.all([read(firstId,'SENT'),read(secondId,'SENT')]);
 expect(aView.agreement).toBeUndefined();
 expect(bView.agreement).toBeUndefined();
 expect(aView.reply_notice).toEqual({outcome:'DECLINED',message_id:decline.message_id});
 expect(bView.reply_notice).toEqual({outcome:'NEEDS_CLARIFICATION',message_id:openYes.message_id});
 console.log('M6.3C-R1 Chromium '+info.project.name+' '+JSON.stringify({conversation,a:aView.reply_notice,b:bView.reply_notice,closedYes:closedYes.message_id,orders:0}));

 const newer=await intakeFixture<{count:number;last_message_id:string}>('page-reply-history',journey,variant,conversation,secondId);
 expect(newer.count).toBe(25);
 const history=inbox.getByRole('region',{name:'История сообщений',exact:true}).locator('ol.message-list');
 const historyPath=`/api/v1/workspaces/${owner.workspace_id}/conversations/${conversation}/messages`;
 const historyReads:boolean[]=[];
 function recordHistory(request:Request){
  const url=new URL(request.url());
  if(request.method()==='GET'&&url.pathname===historyPath)historyReads.push(url.searchParams.has('cursor'));
 }
 page.on('request',recordHistory);
 try{
  for(const [work,requestId,messageId,expectedText] of [
   ['A',firstId,decline.message_id,`Отклоняю ${a.code}`],
   ['B',secondId,openYes.message_id,'да'],
  ]){
   await page.goto('/');
   await openWorkspace(page);
   await openConversation(page,conversation);
   await expect(page.getByTestId(`conversation-${conversation}`)).toHaveAttribute('aria-pressed','true');
   await expect(history.getByTestId(`message-${newer.last_message_id}`)).toHaveText(/Synthetic reply history 25/);
   await expect(history.getByRole('listitem')).toHaveCount(25);
   await requests.selectOption(requestId);
   await expect(cardId).toHaveText(requestId);
   const elementId=`message-${messageId}`;
   const row=history.getByTestId(elementId);
   await expect(row).toHaveCount(0);
   await expect(source).toHaveAttribute('href',`#${elementId}`);
   const beforeClick=historyReads.length;
   await source.click();
   await expect.soft(row,`${work} opens and focuses the older reply`).toBeFocused();
   const activeId=await page.evaluate(()=>document.activeElement?.id||null);
   const observed=await row.evaluateAll(rows=>rows.map(row=>({
    id:row.id,text:row.querySelector('.message-text')?.textContent,
   })));
   const reads=historyReads.slice(beforeClick);
   let repeatGets:number|null=null;
   if(observed.length){
    await expect.soft(row.locator('.message-text')).toHaveText(expectedText);
    await expect.soft(row).toBeInViewport();
    const beforeRepeat=historyReads.length;
    await source.click();
    await expect.soft(row,`${work} refocuses the loaded reply`).toBeFocused();
    repeatGets=historyReads.length-beforeRepeat;
   }
   console.log('M6.3C-R2 Chromium '+info.project.name+' '+JSON.stringify({work,requestId,messageId,expectedText,newer:newer.count,observed,activeId,historyGets:reads.length,cursorGets:reads.filter(Boolean).length,repeatGets}));
   expect.soft(observed).toEqual([{id:elementId,text:expectedText}]);
   expect.soft(reads).toEqual([true]);
   expect.soft(repeatGets).toBe(0);
  }
 }finally{
  page.off('request',recordHistory);
 }
});

test('M6.4B follows automatic and owner quotes to two planned sessions and clarifies a cover-up', async ({page}, info) => {
  test.setTimeout(150_000);
  const variant: Viewport = info.project.name === 'chromium-narrow' ? 'narrow' : 'desktop';
  const journey = 'quote-pilot';
  await configureQuoteService(page, variant, journey);
  const {conversation, input, collected, inbox, intake} = await collectIntake(page, variant, journey);
  const workspace = '/api/v1/workspaces/' + owner.workspace_id;
  const requests = (conversationId: string) =>
    workspace + '/businesses/' + owner.business_id + '/intake/conversations/' + conversationId + '/service-requests';
  async function get<T>(path: string): Promise<T> {
    const response = await page.request.get(path);
    expect(response.status()).toBe(200);
    return response.json();
  }
  type HistoryMessage = {message_id: string; direction: string; text: string; delivery: {status: string} | null};
  const history = async (id: string) =>
    (await get<{items: HistoryMessage[]}>(workspace + '/conversations/' + id + '/messages')).items;
  const quoteView = (id: string) => get<QuoteDelivery>(requests(conversation) + '/' + id + '/quote');
  const transport = (id: string) => intakeFixture<QuoteAttempt>('deliver-quote', journey, variant, conversation, id);
  const work = intake.getByRole('region', {name: 'Черновик заявки', exact: true});
  const selection = intake.getByLabel('Сохранённая заявка', {exact: true});
  const a = collected.service_intents!;
  expect(a).toMatchObject({approval_id: null, quote_id: expect.any(String)});

  type PilotQuote = RequestQuote & {material: {
    facts: ServiceRequestDraft['facts']; release_id: string; deposit_terms_version: string;
    deposit: {mode: string; amount_minor: number};
  }};
  async function deliver(id: string, idea: string, size: string, origin: string, sizeSource: string, price: number) {
    const view = await quoteView(id);
    expect(view.status).toBe('QUEUED');
    expect(view.agreement).toBeUndefined();
    const quote = view.quote as PilotQuote;
    const material = quote.material;
    expect(material).toMatchObject({
      conversation_id: conversation, request_id: id, request_revision: '1',
      amount_minor: price, occupied_minutes: 65, duration_reference_id: material.assessment_id,
      intent_source: {message_id: origin}, deposit: {mode: 'FIXED_DEPOSIT', amount_minor: 50000},
      deposit_terms_version: material.release_id,
    });
    expect(material.facts.find(f => f.field === 'idea')).toMatchObject({value: idea, source: {message_id: origin}});
    expect(material.facts.find(f => f.field === 'approximate_size')).toMatchObject({value: size, source: {message_id: sizeSource}});
    expect(quote.text).toContain('Предоплата — 500 ₽.');
    expect(quote.text).toContain('Принимаю ' + quote.code);
    const sent = await transport(id);
    expect(sent).toMatchObject({quote_id: quote.quote_id, status: 'SENT', calls: 1, effects: 1, text: quote.text});
    const replay = await transport(id);
    expect(replay).toMatchObject({quote_id: quote.quote_id, status: 'SENT', job_claimed: false, calls: 0, effects: 0});
    return quote;
  }

  const rose = await deliver(a.request_id, 'роза', '20 мм', collected.message_id, collected.message_id, 350000);
  expect(rose.quote_id).toBe(a.quote_id);
  expect(rose.material.price_reference_id).toBe(rose.material.price_calculation_id);
  const started = await input('agent-start-second', conversation);
  expect([started.calls, started.effects, started.status]).toEqual([1, 1, 'CLARIFY']);
  const completed = await input('agent-second', conversation);
  expect([completed.calls, completed.effects]).toEqual([0, 0]);
  const b = completed.service_intents!;
  expect(b).toMatchObject({approval_id: expect.any(String), quote_id: null});
  expect(b.request_id).not.toBe(a.request_id);
  expect((await quoteView(b.request_id)).quote).toBeNull();

  const center = page.getByRole('region', {name: 'Решения по заявкам', exact: true});
  await center.getByRole('button', {name: 'Обновить решения по заявкам'}).click();
  await center.getByTestId('approval-' + b.approval_id).click();
  const detail = center.getByTestId('approval-detail-' + b.approval_id);
  await expect(detail.getByRole('list', {name: 'Проверенные сведения'})).toContainText('ласточка');
  const beforeDecision = (await history(conversation)).filter(m => m.direction === 'INBOUND');
  const decisionPath = requests(conversation) + '/' + b.request_id + '/approvals/' + b.approval_id;
  const saved = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === decisionPath);
  await detail.getByLabel('Цена, ₽', {exact: true}).fill('4600');
  await detail.getByRole('button', {name: 'Подтвердить условия'}).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const approved = await response.json() as ApprovalCard;
  expect(approved.decision).toMatchObject({submitted: {amount_minor: 460000, occupied_minutes: null}});
  const swallow = await deliver(b.request_id, 'ласточка', '101 мм', started.message_id, completed.message_id, 460000);
  expect(swallow.material.price_reference_id).toBe(approved.decision!.decision_id);
  expect(swallow.material.duration_reference_id).toBe(approved.basis.assessment_id);
  expect(swallow.material.client_id).toBe(rose.material.client_id);
  const deliveredHistory = await history(conversation);
  expect(deliveredHistory.filter(m => m.direction === 'INBOUND')).toEqual(beforeDecision);
  const outbound = deliveredHistory.filter(m => m.direction === 'OUTBOUND');
  expect(outbound.map(m => m.text).sort()).toEqual([rose.text, swallow.text, 'На каком месте тела вы хотите татуировку?'].sort());
  for (const m of outbound) expect(m.delivery?.status).toBe('SENT');
  for (const id of [a.request_id, b.request_id]) expect((await quoteView(id)).agreement).toBeUndefined();

  async function accept(quote: PilotQuote) {
    const id = quote.material.request_id;
    const reply = await intakeFixture<QuoteReplyResult>('agree-quote', journey, variant, conversation, id);
    expect(reply).toMatchObject({outcome: 'ACCEPTED', quote_id: quote.quote_id, source_message_id: reply.message_id});
    const agreement = (await quoteView(id)).agreement!;
    expect(agreement).toMatchObject({
      quote, acceptance_id: reply.acceptance_id, order_id: reply.order_id, session_id: reply.session_id,
      status: 'PLANNED', scheduled_at: null,
      source: {message_id: reply.message_id, text: 'Принимаю ' + quote.code, status: 'AVAILABLE'},
    });
    await refreshIntake(inbox, intake);
    await intake.getByRole('button', {name: 'Обновить карточку заявки'}).click();
    await selection.selectOption(id);
    const order = work.getByRole('region', {name: 'Согласованный заказ', exact: true});
    await expect(work.getByTestId('service-request-id')).toHaveText(id);
    await expect(order.getByTestId('quote-acceptance-id')).toHaveText(agreement.acceptance_id);
    await expect(order.getByTestId('service-order-id')).toHaveText(agreement.order_id);
    await expect(order.getByTestId('service-session-id')).toHaveText(agreement.session_id);
    await expect(order.getByText(/Запланирован без даты · 65 мин/)).toBeVisible();
    await order.getByRole('link', {name: 'Первая подтверждающая реплика'}).click();
    await expect(order.getByText('Принимаю ' + quote.code, {exact: true})).toBeVisible();
    await order.getByText('Принятые условия · ' + quote.code, {exact: true}).click();
    await expect(order.getByTestId('quote-text')).toHaveText(quote.text);

    const repeat = await intakeFixture<QuoteReplyResult>('repeat-agreement', journey, variant, conversation, id);
    expect(repeat.message_id).not.toBe(reply.message_id);
    expect(repeat).toMatchObject({source_message_id: reply.message_id, quote_id: quote.quote_id,
      acceptance_id: reply.acceptance_id, order_id: reply.order_id, session_id: reply.session_id});
    expect((await quoteView(id)).agreement).toEqual(agreement);
    return {request: id, quote: quote.quote_id, code: quote.code, version: quote.version,
      release: quote.material.release_id, priceBasis: quote.material.price_reference_id,
      durationBasis: quote.material.duration_reference_id, original: reply, repeat,
      outboundMessage: outbound.find(m => m.text === quote.text)!.message_id};
  }
  const acceptedB = await accept(swallow);
  expect((await quoteView(a.request_id)).agreement).toBeUndefined();
  const acceptedA = await accept(rose);
  expect(new Set([acceptedA, acceptedB].flatMap(({original}) =>
    [original.acceptance_id, original.order_id, original.session_id])).size).toBe(6);
  expect((await history(conversation)).filter(m => m.direction === 'OUTBOUND')).toEqual(outbound);
  console.log('M6.4B GJ-AB ' + JSON.stringify({variant, conversation, client: rose.material.client_id,
    rose: acceptedA, roseSource: collected.message_id, swallow: acceptedB, swallowOrigin: started.message_id,
    swallowSizeSource: completed.message_id, approval: b.approval_id, decision: approved.decision!.decision_id,
    inboundBefore: beforeDecision.length, inboundAfter: deliveredHistory.filter(m => m.direction === 'INBOUND').length}));

  const complexJourney = 'pilot-complex';
  const c = await intakeFixture<{conversation_id: string}>('seed', complexJourney, variant);
  expect(c.conversation_id).not.toBe(conversation);
  const complexInbox = await openConversation(page, c.conversation_id);
  const controls = page.getByRole('region', {name: 'Управление диалогом', exact: true});
  await controls.getByRole('button', {name: 'Разрешить автоматику'}).click();
  await expect(controls.getByText('Автоматика разрешена', {exact: true})).toBeVisible();
  const handoff = await intakeFixture<{message_id: string; status: string; calls: number; effects: number}>(
    'pilot-cover-up', complexJourney, variant, c.conversation_id);
  expect(handoff).toMatchObject({status: 'OWNER_HANDOFF', calls: 0, effects: 0});
  await refreshIntake(complexInbox, intake);
  await expect(complexInbox.getByTestId('message-' + handoff.message_id)).toContainText('перекрыть старую татуировку');
  const cards = requests(c.conversation_id) + '/cards';
  expect((await get<{items: unknown[]}>(cards)).items).toHaveLength(0);
  expect((await history(c.conversation_id)).filter(m => m.direction === 'OUTBOUND')).toHaveLength(0);
  const queue = page.getByRole('region', {name: 'Запросы владельцу', exact: true});
  await queue.getByRole('button', {name: 'Обновить очередь'}).click();
  const open = (await get<{items: {conversation_id: string; escalation_id: string; status: string}[]}>(workspace + '/escalations?status=PENDING'))
    .items.filter(item => item.conversation_id === c.conversation_id);
  expect(open).toHaveLength(1);
  await queue.getByTestId('escalation-' + open[0].escalation_id).click();
  const ownerQuestion = 'Мастер, уточните, можно ли продолжить консультацию по этому запросу.';
  await expect(queue.getByText(ownerQuestion, {exact: true})).toBeVisible();
  await expect(queue.getByLabel('Сводка запроса для решения')).toContainText('пион');
  await expect(queue.getByLabel('Сводка запроса для решения')).toContainText(handoff.message_id);
  const clientQuestion = 'Пришлите фото старой татуировки при дневном свете, чтобы мастер оценил перекрытие.';
  await complexInbox.getByLabel('Ручной текстовый ответ').fill(clientQuestion);
  const sent = page.waitForResponse(r => r.request().method() === 'POST' &&
    new URL(r.url()).pathname === workspace + '/conversations/' + c.conversation_id + '/messages');
  await complexInbox.getByRole('button', {name: 'Проверить и отправить'}).click();
  const manual = await sent;
  expect(manual.status()).toBe(202);
  const receipt = parseReceipt(await manual.json());
  const key = await manual.request().headerValue('Idempotency-Key');
  expect(key).toBeTruthy();
  const delivery = await intakeFixture<{message_id: string; outbox_id: string; calls: number; effects: number}>(
    'deliver-pilot-question', complexJourney, variant, c.conversation_id, key!);
  expect(delivery).toMatchObject({message_id: receipt.message_id, calls: 1, effects: 1});
  const clientInbox = (await history(c.conversation_id)).filter(m => m.direction === 'OUTBOUND');
  expect(clientInbox).toHaveLength(1);
  expect(clientInbox[0]).toMatchObject({message_id: receipt.message_id, text: clientQuestion, delivery: {status: 'SENT'}});
  expect((await get<{items: unknown[]}>(cards)).items).toHaveLength(0);
  await complexInbox.getByRole('button', {name: 'Обновить сообщения'}).click();
  await expect(complexInbox.getByTestId('message-' + receipt.message_id)).toContainText(clientQuestion);
  console.log('M6.4B GJ-C ' + JSON.stringify({variant, conversation: c.conversation_id, source: handoff.message_id,
    escalation: open[0].escalation_id, ownerQuestion, clientQuestion, manual: delivery}));
});
