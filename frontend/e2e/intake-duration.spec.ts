import {expect,test,type Page,type Route} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';

const fixtureFile=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE;
if(!fixtureFile||!passwordFile)throw new Error('E2E_INTAKE_PRIVATE_FIXTURES_REQUIRED');
const fixture=JSON.parse(readFileSync(fixtureFile,'utf8')) as {messaging_fixtures:{knowledge:{login:string;workspace_id:string;business_id:string;user_account_id:string}}};
const password=readFileSync(passwordFile,'utf8'),owner=fixture.messaging_fixtures.knowledge;

type Viewport='desktop'|'narrow';
type IntakeOperation='seed'|'collect'|'complex'|'ambiguous'|'second';

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

async function beginIntake(page:Page,variant:Viewport,journey:'intake'|'request'){
 const serviceName='Synthetic intake consultation '+variant+' '+randomUUID();
 const envFile=process.env.ASM_BROWSER_ENV_FILE;
 if(!envFile||!owner?.user_account_id)throw new Error('E2E_INTAKE_TEST_RUNTIME_REQUIRED');
 async function input(operation:IntakeOperation,conversation?:string){
  const args=['compose','--env-file',envFile!,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'browser-runtime','python','scripts/m5_intake_fixture.py','--variant',variant,'--journey',journey,'--operation',operation,'--actor',owner.user_account_id,'--workspace',owner.workspace_id,'--business',owner.business_id,...(conversation?['--conversation',conversation]:[])];
  let stdout:string;
  try{stdout=(await promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:30000,maxBuffer:16384})).stdout;}catch(error){const code=(error as {code?:unknown}).code;throw new Error('E2E_INTAKE_RUNTIME_REFUSED:exit='+String(typeof code==='number'?code:'UNKNOWN'));}
  return JSON.parse(stdout) as {conversation_id:string;message_id:string;model_calls:number;calls:number;effects:number;status:string};
 }
 await page.goto('/');await page.getByLabel('Логин',{exact:true}).fill(owner.login);await page.getByLabel('Пароль',{exact:true}).fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await openWorkspace(page);
 await page.getByRole('button',{name:/Synthetic business/}).click();
 const settings=page.getByRole('region',{name:'Настройки бизнеса',exact:true});
 await expect(settings.getByRole('button',{name:'Добавить услугу',exact:true})).toBeEnabled();
 if(await settings.getByLabel('Название услуги 1',{exact:true}).count()===0)await settings.getByRole('button',{name:'Добавить услугу',exact:true}).click();
 await settings.getByLabel('Название услуги 1',{exact:true}).fill(serviceName);const description=settings.getByLabel('Описание услуги 1');await expect(description).toHaveCount(1);await description.fill('Synthetic browser template '+variant+', owner review required.');
 await settings.getByRole('button',{name:'Применить шаблон новой татуировки v1',exact:true}).first().click();
 await settings.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await expect(settings.getByText('Команда подтверждена. Текущее состояние получено.',{exact:true})).toBeVisible();
 await settings.getByRole('button',{name:'Проверить и показать предпросмотр',exact:true}).click();await expect(settings.getByRole('button',{name:'Опубликовать черновик',exact:true})).toBeEnabled();await settings.getByRole('button',{name:'Опубликовать черновик',exact:true}).click();await expect(settings.getByRole('region',{name:'Опубликованные сведения'}).getByRole('heading',{name:serviceName+' · Активна',exact:true})).toBeVisible();
 const seed=await input('seed');expect([seed.model_calls,seed.calls,seed.effects]).toEqual([0,0,0]);
 const inbox=await openConversation(page,seed.conversation_id);
 const control=page.getByRole('region',{name:'Управление диалогом',exact:true});await expect(control.getByRole('button',{name:'Разрешить автоматику',exact:true})).toBeEnabled();await control.getByRole('button',{name:'Разрешить автоматику',exact:true}).click();await expect(control.getByText('Автоматика разрешена',{exact:true})).toBeVisible();
 const collected=await input('collect',seed.conversation_id);expect([collected.model_calls,collected.calls,collected.effects,collected.status]).toEqual([1,1,1,'CLARIFY']);
 await inbox.getByRole('button',{name:'Обновить сообщения',exact:true}).click();const intake=page.getByRole('region',{name:'Предварительный запрос',exact:true});await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();await expect(intake.getByLabel('Идея',{exact:true})).toHaveValue('flower');await expect(intake.getByText('Какой примерный размер вы представляете, в сантиметрах?',{exact:true})).toBeVisible();
 return {input,conversation:seed.conversation_id,collected,intake,inbox,serviceName};
}

test('@narrow source-backed intake, owner field confirmation, Action Center and measured owner case',async({page},info)=>{
 test.setTimeout(90000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {input,conversation,intake}=await beginIntake(page,variant,'intake');
 const source=intake.getByRole('link',{name:'сообщение клиента',exact:true}).first();const anchor=await source.getAttribute('href');expect(anchor).toMatch(/^#message-[0-9a-f-]+$/);await source.click();await expect(page.locator(anchor!)).toContainText('Synthetic intake flower forearm');
 await page.getByRole('button',{name:'Открыть примеры длительности',exact:true}).click();const cases=page.getByRole('region',{name:'Примеры длительности',exact:true});
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

async function chooseWork(page:Page,message:string,idea:string,placement:string){
 const fields=page.getByRole('group',{name:'Выбор сведений для заявки'});
 const beginning=fields.getByLabel('Начало работы',{exact:true});
 await beginning.selectOption(message);
 await fields.getByRole('checkbox',{name:`Идея: ${idea}`,exact:true}).check();
 await fields.getByRole('checkbox',{name:`Место: ${placement}`,exact:true}).check();
 const create=fields.getByRole('button',{name:'Создать или открыть заявку',exact:true});
 await expect(create).toBeDisabled();
 await fields.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе',exact:true}).check();
 return create;
}

type DraftPost={key:string|undefined;body:unknown;requestId:string;status:number};

async function recordDraftPost(route:Route,posts:DraftPost[],dropFirst=false){
 const request=route.request();
 if(request.method()!=='POST')return route.continue();
 const response=await route.fetch();
 const result=await response.json() as {request_id:string};
 posts.push({key:request.headers()['idempotency-key'],body:request.postDataJSON(),requestId:result.request_id,status:response.status()});
 if(dropFirst&&posts.length===1)return route.abort('failed');
 await route.fulfill({response});
}

test('@narrow service request preserves intake sources across two tabs, lost response and separate work',async({page,context},info)=>{
 test.setTimeout(120000);
 const variant=info.project.name==='chromium-narrow'?'narrow':'desktop';
 const {input,conversation,collected,intake,inbox,serviceName}=await beginIntake(page,variant,'request');
 const secondTab=await context.newPage();
 await secondTab.goto('/');
 await openWorkspace(secondTab);
 await openConversation(secondTab,conversation);

 const firstPosts:DraftPost[]=[],secondPosts:DraftPost[]=[];
 const endpoint=`**/intake/conversations/${conversation}/service-requests`;
 await page.route(endpoint,route=>recordDraftPost(route,firstPosts,true));
 await secondTab.route(endpoint,route=>recordDraftPost(route,secondPosts));
 const [firstCreate,secondCreate]=await Promise.all([
  chooseWork(page,collected.message_id,'flower','forearm'),
  chooseWork(secondTab,collected.message_id,'flower','forearm'),
 ]);
 await Promise.all([firstCreate.click(),secondCreate.click()]);
 const retry=intake.getByRole('button',{name:'Повторить создание заявки',exact:true});
 await expect(retry).toBeVisible();
 const secondId=secondTab.getByTestId('service-request-id');
 await expect(secondId).toHaveText(/^[0-9a-f-]{36}$/);
 const firstId=(await secondId.textContent())!;
 expect(firstPosts).toHaveLength(1);
 expect(secondPosts).toHaveLength(1);
 expect(firstPosts[0]).toMatchObject({requestId:firstId,status:200});
 expect(secondPosts[0]).toMatchObject({requestId:firstId,status:200});
 expect(firstPosts[0].key).toBeTruthy();
 expect(secondPosts[0].key).toBeTruthy();
 expect(firstPosts[0].key).not.toBe(secondPosts[0].key);
 expect(firstPosts[0].body).toEqual(secondPosts[0].body);

 await retry.click();
 const card=page.getByRole('region',{name:'Черновик заявки',exact:true});
 const cardId=card.getByTestId('service-request-id');
 await expect(cardId).toHaveText(firstId);
 expect(firstPosts).toHaveLength(2);
 expect(firstPosts[1]).toEqual(firstPosts[0]);
 await expect(card.getByText(serviceName,{exact:true})).toBeVisible();
 await expect(card.getByText(/flower · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/forearm · Со слов клиента/)).toBeVisible();
 await expect(card.getByRole('link',{name:'Сообщение для поля Идея',exact:true})).toHaveAttribute('href',`#message-${collected.message_id}`);
 const selection=firstPosts[0].body as {intent_source:{source_version:string};fields:string[]};
 expect(selection.fields).toEqual(['idea','placement']);
 expect(selection.intent_source.source_version).toMatch(/^[0-9a-f]{64}$/);
 await expect(card.getByText(selection.intent_source.source_version,{exact:true}).first()).toBeVisible();
 await expect(card.getByText(/Не хватает/)).toContainText('Примерный размер');
 await expect(card.getByText('Какой примерный размер вы представляете, в сантиметрах?',{exact:true})).toBeVisible();

 await secondTab.close();
 await page.reload();
 await openWorkspace(page);
 await openConversation(page,conversation);
 await expect(cardId).toHaveText(firstId);
 expect(firstPosts).toHaveLength(2);

 const ambiguous=await input('ambiguous',conversation);
 expect([ambiguous.model_calls,ambiguous.calls,ambiguous.effects,ambiguous.status]).toEqual([1,1,1,'CLARIFY']);
 await inbox.getByRole('button',{name:'Обновить сообщения',exact:true}).click();
 await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();
 await expect(intake.getByText('Уточните, к какой услуге или отдельной идее относится сообщение.',{exact:true})).toBeVisible();
 await expect(intake.getByRole('button',{name:'Создать или открыть заявку',exact:true})).toHaveCount(0);
 await expect(cardId).toHaveText(firstId);
 expect(firstPosts).toHaveLength(2);

 const separate=await input('second',conversation);
 expect([separate.model_calls,separate.calls,separate.effects,separate.status]).toEqual([1,1,1,'CLARIFY']);
 await inbox.getByRole('button',{name:'Обновить сообщения',exact:true}).click();
 await intake.getByRole('button',{name:'Обновить сводку',exact:true}).click();
 await expect(intake.getByLabel('Идея',{exact:true})).toHaveValue('swallow');
 await (await chooseWork(page,separate.message_id,'swallow','shoulder')).click();
 await expect(card.getByText(/swallow · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/shoulder · Со слов клиента/)).toBeVisible();
 await expect(card.getByText(/flower|forearm/)).toHaveCount(0);
 await expect(card.getByRole('link',{name:'Сообщение для поля Идея',exact:true})).toHaveAttribute('href',`#message-${separate.message_id}`);
 await expect(card.getByText(serviceName,{exact:true})).toBeVisible();
 expect(firstPosts).toHaveLength(3);
 expect(firstPosts[2].status).toBe(200);
 expect(firstPosts[2].requestId).not.toBe(firstId);
 await expect(cardId).toHaveText(firstPosts[2].requestId);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
