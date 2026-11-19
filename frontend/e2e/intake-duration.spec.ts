import {expect,test,type Locator,type Page,type Route} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import type {DraftCommand,DraftListItem,DraftRevisionCommand,Intake,ServiceAssessment} from '../src/intake-api';

const fixtureFile=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!fixtureFile||!passwordFile)throw new Error('E2E_INTAKE_PRIVATE_FIXTURES_REQUIRED');
const fixture=JSON.parse(readFileSync(fixtureFile,'utf8')) as {messaging_fixtures:{knowledge:{login:string;workspace_id:string;business_id:string;user_account_id:string}}};
const password=readFileSync(passwordFile,'utf8'),owner=fixture.messaging_fixtures.knowledge;

type Viewport='desktop'|'narrow';
type IntakeOperation='seed'|'collect'|'collect-sized'|'complex'|'ambiguous'|'second'|'late-size'|'assess-first'|'assess-second';
type IntakeJourney='intake'|'request'|'request-deferred'|'assessment';

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
 async function input(operation:IntakeOperation,conversation?:string){
  const args=['compose','--env-file',envFile!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-runtime','python','scripts/m5_intake_fixture.py','--variant',variant,'--journey',journey,'--operation',operation,'--actor',owner.user_account_id,'--workspace',owner.workspace_id,'--business',owner.business_id,...(conversation?['--conversation',conversation]:[])];
  let stdout:string;
  try{stdout=(await promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:16384})).stdout;}catch(error){const code=(error as {code?:unknown}).code;throw new Error('E2E_INTAKE_RUNTIME_REFUSED:exit='+String(typeof code==='number'?code:'UNKNOWN'));}
  return JSON.parse(stdout) as {conversation_id:string;message_id:string;model_calls:number;calls:number;effects:number;status:string};
 }
 const seed=await input('seed');expect([seed.model_calls,seed.calls,seed.effects]).toEqual([0,0,0]);
 const inbox=await openConversation(page,seed.conversation_id);
 const control=page.getByRole('region',{name:'Управление диалогом',exact:true});await expect(control.getByRole('button',{name:'Разрешить автоматику',exact:true})).toBeEnabled();await control.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();await expect(control.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
 const operation=journey==='intake'?'collect':journey==='assessment'?'assess-first':'collect-sized';
 const collected=await input(operation,seed.conversation_id);
 expect([collected.model_calls,collected.calls,collected.effects,collected.status]).toEqual([1,1,1,journey==='assessment'?'PRELIMINARILY_COMPLETE':'CLARIFY']);
 const intake=page.getByRole('region',{name:'Предварительный запрос',exact:true});
 await refreshIntake(inbox,intake);
 await expect(intake.getByLabel('Идея',{exact:true})).toHaveValue('flower');
 if(journey!=='intake')await expect(intake.getByLabel('Примерный размер',{exact:true})).toHaveValue('8 cm');
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

 await mode.selectOption('CONFIGURED_RULE');
 await settings.getByLabel('Порог размера, мм 1',{exact:true}).fill('80');
 await settings.getByLabel('Минуты до порога включительно 1',{exact:true}).fill('55');
 await settings.getByLabel('Минуты свыше порога 1',{exact:true}).fill('95');
 const ruleText='До 80 мм включительно — 55 мин. Свыше 80 мм — 95 мин.';
 await expect(settings.locator('form').first().getByText(ruleText,{exact:true})).toBeVisible();
 await publishIntakeService(settings,serviceName);
 await expect(published.getByText(ruleText)).toBeVisible();
 await refresh.click();
 await expect(panel.getByText(/Архивная оценка/)).toBeVisible();
 await expect(clock).toHaveCount(0);
 await expect(panel.getByText(fixed.release_id!,{exact:true})).toBeVisible();
 expect(await readAssessment(firstId)).toMatchObject({assessment_id:fixed.assessment_id,release_id:fixed.release_id,current:false});
 await evaluate.click();
 await expect(clock).toContainText('55 мин');
 await expect(panel.getByText('Порог опубликованного правила 80 мм.',{exact:true})).toBeVisible();
 await expect(panel.getByRole('link',{name:'Источник оценки для поля Примерный размер',exact:true})).toHaveAttribute('href',`#message-${collected.message_id}`);
 expect(await readAssessment(firstId)).toMatchObject({outcome:'FEASIBLE',reason:'SIZE_DURATION_RULE',size_mm:80,occupied_minutes:55});

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
 await expect(panel.getByText(/Архивная оценка/)).toBeVisible();
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
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
