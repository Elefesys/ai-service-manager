// Actual owner HTTP -> private S3 -> guarded v6 Worker -> owner Inbox. No routes
// are patched, model/embedding wires are explicitly synthetic inside the finite
// runtime-only helper; API model/embedding defaults remain DISABLED.
import { expect, test, type APIResponse, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { deflateSync } from 'node:zlib';
import { parseOwnerState, parsePortfolioCommand, type OwnerState } from '../src/portfolio-api';
import { parseMessage, parsePage } from '../src/messaging-api';

const origin='http://127.0.0.1:8080',preset='portfolio_photo';
const caption='Подтверждённая тестовая работа мастера 🎨';
const safe=async<T,>(code:string,operation:()=>Promise<T>):Promise<T>=>{try{return await operation();}catch{throw new Error(`E2E_SAFE_FAILURE:${code}`);}};
const json=(r:APIResponse)=>safe('PORTFOLIO_PHOTO_BODY',()=>r.json());
function fixture(){
  const env=process.env.ASM_BROWSER_ENV_FILE,file=process.env.ASM_BROWSER_FIXTURE_FILE,passwordFile=process.env.ASM_BROWSER_PASSWORD_FILE,counters=process.env.ASM_BROWSER_COUNTER_DIR;
  if(!env||!file||!passwordFile||!counters)throw new Error('E2E_PORTFOLIO_PHOTO_PRIVATE_FIXTURE_REQUIRED');
  try{const f=JSON.parse(readFileSync(file,'utf8')).messaging_fixtures[preset];if(!f||!['workspace_id','business_id','login'].every(k=>typeof f[k]==='string'))throw new Error();return {...f,env,counters,password:readFileSync(passwordFile,'utf8')} as {workspace_id:string;business_id:string;login:string;env:string;counters:string;password:string};}catch{throw new Error('E2E_PORTFOLIO_PHOTO_PRIVATE_FIXTURE_SHAPE');}
}
async function helper(f:ReturnType<typeof fixture>,action:'publish'|'prepare'|'answer',viewport:'desktop'|'narrow',scenario:'sent'|'unknown'){
  const args=['compose','--env-file',f.env,'-f','compose.yaml','-f','compose.browser.yaml','--profile','browser','run','--no-deps','--rm','-T','--user',`${process.getuid!()}:${process.getgid!()}`,'-v',`${f.counters}:/run/m2-browser-counters:rw`,'browser-runtime','python','tests/m5_portfolio_delivery_fixtures.py','--action',action,'--viewport',viewport,'--scenario',scenario];
  const result=await safe('PORTFOLIO_PHOTO_FINITE_HELPER',()=>promisify(execFile)('docker',args,{cwd:resolve(process.cwd(),'..'),timeout:110000,maxBuffer:65536}));
  try{return JSON.parse(result.stdout) as Record<string,string|number|boolean>;}catch{throw new Error('E2E_PORTFOLIO_PHOTO_FINITE_OUTPUT');}
}
function pixels():Buffer{
  const crc=(bytes:Buffer)=>{let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;};
  const chunk=(type:string,data:Buffer)=>{const t=Buffer.from(type),length=Buffer.alloc(4),sum=Buffer.alloc(4);length.writeUInt32BE(data.length);sum.writeUInt32BE(crc(Buffer.concat([t,data])));return Buffer.concat([length,t,data,sum]);};
  const header=Buffer.alloc(13);header.writeUInt32BE(64,0);header.writeUInt32BE(64,4);header[8]=8;header[9]=2;
  const rows=Buffer.alloc(64*(64*3+1));let seed=Number.parseInt(randomUUID().slice(0,8),16);for(let y=0;y<64;y++)for(let x=1;x<=64*3;x++){seed=(seed*1664525+1013904223)>>>0;rows[y*(64*3+1)+x]=seed>>>24;}
  return Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',header),chunk('IDAT',deflateSync(rows)),chunk('IEND',Buffer.alloc(0))]);
}
async function csrf(page:Page){const r=await safe('PORTFOLIO_PHOTO_SESSION',()=>page.request.get('/api/v1/auth/session'));expect(r.status()).toBe(200);return (await json(r)).csrf_token as string;}
async function owner(page:Page,base:string):Promise<OwnerState>{const r=await safe('PORTFOLIO_PHOTO_STATE',()=>page.request.get(base));expect(r.status()).toBe(200);return parseOwnerState(await json(r));}
async function command(page:Page,base:string,suffix:string,body:unknown){const token=await csrf(page);const r=await safe('PORTFOLIO_PHOTO_OWNER_COMMAND',()=>page.request.post(base+suffix,{headers:{Origin:origin,'X-CSRF-Token':token,'Idempotency-Key':randomUUID()},data:body}));expect(r.status()).toBe(200);return parsePortfolioCommand(await json(r));}
const panel=(page:Page)=>page.getByRole('region',{name:'Переписка',exact:true});
async function choose(page:Page,conversation:string){await panel(page).getByRole('button',{name:'Обновить диалоги',exact:true}).click();await expect(page.getByTestId(`conversation-${conversation}`)).toBeVisible();await page.getByTestId(`conversation-${conversation}`).click();await expect(panel(page).getByRole('button',{name:'Обновить сообщения',exact:true})).toBeEnabled();}
async function refresh(page:Page){await panel(page).getByRole('button',{name:'Обновить сообщения',exact:true}).click();await expect(panel(page).getByRole('button',{name:'Обновить сообщения',exact:true})).toBeEnabled();}

test('@narrow actual private portfolio photo follows SENT/UNKNOWN delivery, owner preview, context switch, source withdrawal and logout',async({page},info)=>{
  test.setTimeout(240000);const f=fixture(),viewport=info.project.name==='chromium-narrow'?'narrow':'desktop',base=`/api/v1/workspaces/${f.workspace_id}/businesses/${f.business_id}/portfolio`,bytes=pixels(),digest=createHash('sha256').update(bytes).digest('hex');
  await page.goto('/');await page.getByLabel('Логин').fill(f.login);await safe('PORTFOLIO_PHOTO_LOGIN',()=>page.getByLabel('Пароль').fill(f.password));await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(panel(page)).toBeVisible();if(await page.getByLabel('Workspace',{exact:true}).inputValue()!==f.workspace_id)await page.getByLabel('Workspace',{exact:true}).selectOption(f.workspace_id);
  let asset:string|null=null,grants=0;page.on('request',r=>{if(new URL(r.url()).pathname.endsWith('/read-grant'))grants++;});
  try{
    const initial=await owner(page,base);expect(initial.vision_mode).toBe('DISABLED');expect(initial.embedding_mode).toBe('DISABLED');expect(initial.items.filter(i=>i.state==='CONFIRMED')).toHaveLength(0);
    // Owner-issued upload intent and real API content PUT supply the bytes. No
    // fixture writes a storage key, READY row, outgoing message or receipt.
    const created=(await command(page,base,'/assets/uploads',{schema_version:1,asset_id:null,expected_asset_version:'0',origin:'MY_WORK',mime_type:'image/png',size_bytes:bytes.length,sha256:digest})).result;
    if(!created.asset_id||!created.version_id||!created.upload_id)throw new Error('E2E_PORTFOLIO_PHOTO_UPLOAD_BINDING');asset=created.asset_id;
    const token=await csrf(page),uploaded=await safe('PORTFOLIO_PHOTO_PRIVATE_PUT',()=>page.request.put(`${base}/assets/${asset}/versions/${created.version_id}/uploads/${created.upload_id}/content`,{headers:{Origin:origin,'Content-Type':'image/png','X-CSRF-Token':token},data:bytes}));expect(uploaded.status()).toBe(200);
    await command(page,base,`/assets/${asset}/versions/${created.version_id}/uploads/${created.upload_id}/finalize`,{schema_version:1,expected_asset_version:created.asset_version});
    const saved=(await command(page,base,'/items',{schema_version:1,item_id:null,expected_item_version:'0',asset_id:asset,description:'Synthetic owner-confirmed flower work',attributes:{subject:'flower',styles:['linework'],placement:null},service_id:null,analysis_id:null})).result;
    await command(page,base,`/items/${saved.item_id}/confirm`,{schema_version:1,expected_item_version:saved.item_version,revision_id:saved.revision_id,canonical_sha256:saved.canonical_sha256,confirm_my_work:true,show_permission:true});
    const published=await helper(f,'publish',viewport,'sent');expect(published).toMatchObject({published:true,embedding_calls:1});const mainConversation=String(published.main_conversation_id);
    let lastConversation='',lastMessage='';
    for(const scenario of ['sent','unknown'] as const){
      const prepared=await helper(f,'prepare',viewport,scenario);expect(typeof prepared.conversation_id).toBe('string');lastConversation=String(prepared.conversation_id);await choose(page,lastConversation);
      await expect(panel(page).getByText('Управление у мастера',{exact:true})).toBeVisible();await panel(page).getByRole('button',{name:'Разрешить автоматику',exact:true}).click();await expect(panel(page).getByText('Автоматика разрешена',{exact:true})).toBeVisible();
      const result=await helper(f,'answer',viewport,scenario);expect(result).toMatchObject({model_calls:2,calls:1,effects:1,status:scenario.toUpperCase()});lastMessage=String(result.message_id);await refresh(page);
      const card=page.getByTestId(`message-${lastMessage}`);await expect(card.getByText(caption,{exact:true})).toBeVisible();await expect(card.getByText(scenario==='sent'?'Канал принял':/Результат неизвестен — повтора нет/)).toBeVisible();await expect(card.getByText(/Фото из портфолио/)).toBeVisible();
      const received=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname===`${base}/assets/${asset}/versions/${created.version_id}/preview`);await card.getByRole('button',{name:'Посмотреть фото из портфолио',exact:true}).click();const response=await received;expect(response.status()).toBe(200);expect(response.headers()['cache-control']).toContain('no-store');expect(createHash('sha256').update(await safe('PORTFOLIO_PHOTO_PRIVATE_BODY',()=>response.body())).digest('hex')===digest).toBe(true);
      const image=card.getByRole('img',{name:'Работа из портфолио в исходящем сообщении'});await expect.poll(()=>safe('PORTFOLIO_PHOTO_PRIVATE_IMAGE',()=>image.evaluate(n=>(n as HTMLImageElement).naturalWidth))).toBe(64);expect((await image.getAttribute('src'))?.startsWith('blob:')).toBe(true);expect(await card.getByRole('button',{name:/повторить фото|отправить фото|retry/i}).count()).toBe(0);
      await refresh(page);await expect(image).toHaveCount(0);await expect(card.getByText(scenario==='sent'?'Канал принял':/Результат неизвестен — повтора нет/)).toBeVisible();
      const history=await safe('PORTFOLIO_PHOTO_HISTORY',()=>page.request.get(`/api/v1/workspaces/${f.workspace_id}/conversations/${lastConversation}/messages?limit=25`));const projection=parsePage(await json(history),parseMessage);expect(projection.items.filter(m=>m.content_type==='PORTFOLIO_PHOTO')).toHaveLength(1);
      await card.getByRole('button',{name:'Посмотреть фото из портфолио',exact:true}).click();await expect(image).toBeVisible();await choose(page,mainConversation);await expect(image).toHaveCount(0);await choose(page,lastConversation);await expect(image).toHaveCount(0);
    }
    const state=await owner(page,base),item=state.items.find(i=>i.asset_id===asset)!;await command(page,base,`/items/${item.item_id}/revoke`,{schema_version:1,expected_item_version:item.version,expected_activation_version:state.activation_version});await choose(page,lastConversation);await refresh(page);const unavailable=page.getByTestId(`message-${lastMessage}`);await expect(unavailable.getByText('Источник портфолио недоступен.',{exact:true})).toBeVisible();await expect(unavailable.getByRole('img')).toHaveCount(0);await expect(unavailable.getByRole('button',{name:'Посмотреть фото из портфолио',exact:true})).toHaveCount(0);await expect(unavailable.getByText(/Результат неизвестен — повтора нет/)).toBeVisible();
    expect(grants).toBe(0);const defaults=await owner(page,base);expect(defaults.vision_mode==='DISABLED'&&defaults.embedding_mode==='DISABLED').toBe(true);await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.getByLabel('Логин')).toBeVisible();await expect(page.getByRole('img',{name:'Работа из портфолио в исходящем сообщении'})).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  }finally{
    // Login may have ended after the successful logout assertion; restore only
    // this finite owner session for cleanup of the asset created above.
    if(asset){
      const session=await safe('PORTFOLIO_PHOTO_CLEANUP_SESSION',()=>page.request.get('/api/v1/auth/session'));
      if(session.status()===401){
        const bootstrap=await safe('PORTFOLIO_PHOTO_CLEANUP_BOOTSTRAP',()=>page.request.post('/api/v1/auth/bootstrap',{headers:{Origin:origin,'X-CSRF-Bootstrap':'1'},data:{}}));expect(bootstrap.status()).toBe(200);
        const token=(await json(bootstrap)).csrf_token as string;
        const login=await safe('PORTFOLIO_PHOTO_CLEANUP_LOGIN',()=>page.request.post('/api/v1/auth/login',{headers:{Origin:origin,'X-CSRF-Token':token},data:{login:f.login,password:f.password}}));expect(login.status()).toBe(200);
      }else expect(session.status()).toBe(200);
      const state=await owner(page,base),current=state.assets.find(a=>a.asset_id===asset);if(current)await command(page,base,`/assets/${asset}/delete`,{schema_version:1,expected_asset_version:current.version,expected_activation_version:state.activation_version});
    }
  }
});
