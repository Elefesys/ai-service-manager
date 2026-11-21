import {expect,test,type Locator,type Page,type Route} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import type {ApprovalBody,ApprovalCard} from '../src/escalation-api';
import type {DraftCommand,DraftListItem,DraftRevisionCommand,Intake,PriceCalculation,PriceHistory,ServiceAssessment} from '../src/intake-api';

const fixtureFile=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!fixtureFile||!passwordFile)throw new Error('E2E_INTAKE_PRIVATE_FIXTURES_REQUIRED');
const fixture=JSON.parse(readFileSync(fixtureFile,'utf8')) as {messaging_fixtures:{knowledge:{login:string;workspace_id:string;business_id:string;user_account_id:string}}};
const password=readFileSync(passwordFile,'utf8'),owner=fixture.messaging_fixtures.knowledge;

type Viewport='desktop'|'narrow';
type IntakeOperation='seed'|'collect'|'collect-sized'|'complex'|'ambiguous'|'second'|'late-size'|'late-cover-up'|'complex-message'|'assess-first'|'assess-second'|'price-first'|'price-second'|'price-size'|'price-oversize';
type IntakeJourney='intake'|'request'|'request-deferred'|'assessment'|'assessment-complex'|'assessment-complex-source'|'pricing'|'owner-decision'|'owner-decision-partial'|'owner-source-other';

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

async function collectIntake(page:Page,variant:Viewport,journey:IntakeJourney){
 const envFile=process.env.ASM_BROWSER_ENV_FILE;
 if(!envFile||!owner?.user_account_id)throw new Error('E2E_INTAKE_TEST_RUNTIME_REQUIRED');
 async function input(operation:IntakeOperation,conversation?:string,fixtureJourney=journey){
  const args=['compose','--env-file',envFile!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-runtime','python','scripts/m5_intake_fixture.py','--variant',variant,'--journey',fixtureJourney,'--operation',operation,'--actor',owner.user_account_id,'--workspace',owner.workspace_id,'--business',owner.business_id,...(conversation?['--conversation',conversation]:[])];
  let stdout:string;
  try{stdout=(await promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:16384})).stdout;}catch(error){const code=(error as {code?:unknown}).code;throw new Error('E2E_INTAKE_RUNTIME_REFUSED:exit='+String(typeof code==='number'?code:'UNKNOWN'));}
  return JSON.parse(stdout) as {conversation_id:string;message_id:string;model_calls:number;calls:number;effects:number;status:string};
 }
 const seed=await input('seed');expect([seed.model_calls,seed.calls,seed.effects]).toEqual([0,0,0]);
 const inbox=await openConversation(page,seed.conversation_id);
 const control=page.getByRole('region',{name:'Управление диалогом',exact:true});await expect(control.getByRole('button',{name:'Разрешить автоматику',exact:true})).toBeEnabled();await control.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();await expect(control.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
 const assessment=journey.startsWith('assessment');
 const pricing=journey==='pricing'||journey.startsWith('owner-decision');
 const operation=journey==='intake'?'collect':pricing?'price-first':assessment?'assess-first':'collect-sized';
 const collected=await input(operation,seed.conversation_id);
 expect([collected.model_calls,collected.calls,collected.effects,collected.status]).toEqual([1,1,1,assessment||pricing?'PRELIMINARILY_COMPLETE':'CLARIFY']);
 const intake=page.getByRole('region',{name:'Предварительный запрос',exact:true});
 await refreshIntake(inbox,intake);
 await expect(intake.getByLabel('Идея',{exact:true})).toHaveValue('flower');
 if(journey!=='intake')await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue(pricing?'20 mm':'8 cm');
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
