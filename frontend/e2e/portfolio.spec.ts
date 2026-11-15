import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { deflateSync } from 'node:zlib';
import { active, bundle, business, businessId, command, draft, emptyBuildId, emptyReadyBuild, knowledgeState, preview, releaseId, session, stamp, workspace } from '../src/configuration-fixtures.test-helper';
import { assetId, versionId, uploadId, itemRevision, ownerState, photo, portfolioItem, confirmedItem, portfolioBuild, observation, portfolioCommand, portfolioBuildId } from '../src/portfolio-fixtures.test-helper';
import type { CommandBody, Operation, OwnerState } from '../src/portfolio-api';

// Browser UI mechanics with controlled HTTP responses. This is not PostgreSQL/S3 or model-quality evidence.
function png():Buffer{
  const crc=(bytes:Buffer)=>{let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;};
  const chunk=(type:string,data:Buffer)=>{const t=Buffer.from(type),size=Buffer.alloc(4),checksum=Buffer.alloc(4);size.writeUInt32BE(data.length);checksum.writeUInt32BE(crc(Buffer.concat([t,data])));return Buffer.concat([size,t,data,checksum]);};
  const header=Buffer.alloc(13);header.writeUInt32BE(64,0);header.writeUInt32BE(64,4);header[8]=8;header[9]=2;
  const pixels=Buffer.alloc(64*(64*3+1));let seed=195;for(let y=0;y<64;y++)for(let x=1;x<=64*3;x++){seed=(seed*1664525+1013904223)>>>0;pixels[y*(64*3+1)+x]=seed>>>24;}
  return Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',header),chunk('IDAT',deflateSync(pixels)),chunk('IEND',Buffer.alloc(0))]);
}
async function controlled(page:Page){
  let port:OwnerState={...ownerState(),vision_mode:'CONTROLLED',embedding_mode:'CONTROLLED',activation_version:'1',active_release_id:releaseId,active_knowledge_build_id:emptyBuildId};
  let config=draft(bundle(),'1','1',releaseId),published=active(bundle(),'1',releaseId);
  const bytes=png(),writes:{path:string;body:unknown}[]=[],counts={put:0,analysis:0,build:0,purge:0,legacyPublish:0};
  const kb=()=>({...knowledgeState(),active_build_id:emptyBuildId,activation_version:port.activation_version,release_id:port.active_release_id,builds:[emptyReadyBuild()],rollback_targets:[{release_id:port.active_release_id!,build_id:emptyBuildId,eligible:true,reason_code:null}]});
  const activate=()=>{port.activation_version=String(BigInt(port.activation_version)+1n);port.active_release_id=releaseId;config={...config,activation_version:port.activation_version,release_id:releaseId};published=active(config.bundle,port.activation_version,releaseId,config.draft_version);};
  await page.route('**/api/**',async route=>{
    const r=route.request(),path=new URL(r.url()).pathname,method=r.method(),json=async(value:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
    if(path.endsWith('/auth/session'))return json(session());
    if(path.endsWith('/businesses'))return json({businesses:[business()]});
    if(path.endsWith(`/businesses/${businessId}`))return json(business());
    if(path.endsWith('/configuration/draft')&&method==='GET')return json(config);
    if(path.endsWith('/configuration/active'))return json(published);
    if(path.endsWith('/configuration/preview'))return json(preview(config));
    if(path.endsWith('/configuration/draft')&&method==='PUT'){const b=r.postDataJSON();writes.push({path,body:b});config={...config,bundle:b.bundle,draft_version:String(BigInt(config.draft_version)+1n)};port.draft_version=config.draft_version;return json(command('EDIT',config.draft_version,port.activation_version,port.active_release_id));}
    if(path.endsWith('/configuration/publish')||path.endsWith('/knowledge/publish')){counts.legacyPublish++;return json({error:{code:'PORTFOLIO_BUILD_REQUIRED'}},409);}
    if(path.endsWith('/knowledge'))return json(kb());
    if(!path.includes('/portfolio'))return json({error:{code:'UNAVAILABLE'}},503);
    const suffix=path.split('/portfolio')[1];
    if(!suffix&&method==='GET')return json(port);
    if(suffix.endsWith('/preview'))return route.fulfill({status:200,contentType:'image/png',body:bytes,headers:{'Cache-Control':'private, no-store'}});
    if(suffix.endsWith('/content')){counts.put++;expect(r.postDataBuffer()?.equals(bytes)).toBe(true);port.assets[0].versions[0].state='STORED';return json({schema_version:1,version_id:versionId,upload_id:uploadId,state:'STORED',recorded:true});}
    if(suffix.endsWith('/analysis')){counts.analysis++;expect(r.headers()['idempotency-key']).toBeUndefined();port.assets[0].analysis=observation();return json({schema_version:1,outcome:'COMPLETE',analysis_id:observation().analysis_id,state:'SUCCESS',applied:true});}
    if(suffix.endsWith('/purge')){counts.purge++;port.pending_purges=[];return json({schema_version:1,version_id:versionId,state:'PURGED',outcome:'DELETED'});}
    const body=r.postDataJSON() as CommandBody;writes.push({path,body});let op:Operation,result:Parameters<typeof portfolioCommand>[1]={};
    if(suffix==='/assets/uploads'){
      op='PORTFOLIO_UPLOAD_CREATE';expect(body).toMatchObject({origin:'MY_WORK',size_bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});port.assets=[{...photo(),version:'1',state:'DRAFT',accepted_version_id:null,pending_version_id:versionId,versions:[{...photo().versions[0],state:'INIT',manifest:{mime_type:'image/png',size_bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),width:null,height:null}}]}];result={asset_id:assetId,asset_version:'1',version_id:versionId,upload_id:uploadId,upload_state:'INIT',upload_expires_at:stamp};
    }else if(suffix.endsWith('/finalize')){op='PORTFOLIO_UPLOAD_FINALIZE';expect(body).toEqual({schema_version:1,expected_asset_version:'1'});port.assets=[photo()];result={asset_id:assetId,asset_version:'2',version_id:versionId,upload_id:uploadId,upload_state:'READY',upload_expires_at:stamp};
    }else if(suffix==='/items'&&'description'in body){op='PORTFOLIO_SAVE';port.items=[{...portfolioItem(),head:{...portfolioItem().head,description:body.description,attributes:body.attributes,service_id:body.service_id,analysis_id:body.analysis_id}}];
    }else if(suffix.endsWith('/confirm')){op='PORTFOLIO_CONFIRM';expect(body).toMatchObject({confirm_my_work:true,show_permission:true,revision_id:itemRevision});port.items=[{...confirmedItem(),head:{...port.items[0].head,confirmed:true}}];
    }else if(suffix==='/builds'&&'revision_ids'in body){op='PORTFOLIO_BUILD_CREATE';counts.build++;port.builds=[portfolioBuild(body.revision_ids.length===0)];result={build_id:portfolioBuildId,build_version:'1',build_state:'PLANNED'};
    }else if(suffix==='/publish'&&'portfolio_build_id'in body){op='PORTFOLIO_PUBLISH';expect(body.knowledge_build_id).toBe(emptyBuildId);expect(body.expected_knowledge_build_version).toBe('1');expect(body.expected_portfolio_build_version).toBe(port.builds[0].version);port.active_portfolio_build_id=body.portfolio_build_id;activate();result={build_id:portfolioBuildId,build_version:port.builds[0].version,knowledge_build_id:emptyBuildId,release_id:releaseId,activation_version:port.activation_version};
    }else if(suffix.endsWith('/revoke')){op='PORTFOLIO_REVOKE';port.items=[{...port.items[0],state:'REVOKED',show_permission:false}];port.builds=port.builds.map(b=>({...b,eligible:false}));port.embedding_mode='DISABLED';activate();
    }else if(suffix.endsWith('/delete')){op='PORTFOLIO_DELETE';port.assets=[];port.items=[];port.pending_purges=[{asset_id:assetId,version_id:versionId,state:'PURGE_PENDING',outcome:'DEPENDENCY_TIMEOUT',deadline:null}];activate();
    }else return json({error:{code:'INVALID_INPUT'}},422);
    return json(portfolioCommand(op,{release_id:port.active_release_id,activation_version:port.activation_version,...result}));
  });
  const open=async()=>{await page.goto('/');await page.getByRole('button',{name:/Тестовая мастерская/}).click();await expect(page.getByRole('region',{name:'Портфолио мастера'})).toBeVisible();await expect(page.getByLabel('Файл портфолио')).toBeEnabled();};
  return {bytes,writes,counts,open,state:()=>port};
}

test('@narrow controlled owner UI uploads, reviews, jointly publishes, reloads and revokes without hidden analysis',async({page},testInfo)=>{
  const h=await controlled(page);await h.open();
  await page.getByLabel('Файл портфолио').setInputFiles({name:'synthetic-work.png',mimeType:'image/png',buffer:h.bytes});await page.getByRole('button',{name:'Загрузить фото',exact:true}).click();await expect(page.getByRole('button',{name:'Принять загруженное фото'})).toBeEnabled();expect(h.counts.put).toBe(1);expect(h.counts.analysis).toBe(0);
  await page.getByRole('button',{name:'Принять загруженное фото'}).click();await page.getByRole('button',{name:'Открыть приватное фото'}).click();await expect(page.getByAltText('Приватное фото 1')).toBeVisible();expect(h.counts.analysis).toBe(0);
  await page.getByRole('button',{name:'Анализировать фото',exact:true}).click();await expect(page.getByText('Масштаб: неизвестен.',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Редактировать описание фото 1'}).click();await page.getByRole('button',{name:'Скопировать наблюдения в черновик'}).click();await page.getByLabel('Описание работы').fill('Проверенная владельцем графическая работа с цветком.');await page.getByRole('button',{name:'Сохранить описание',exact:true}).click();await expect(page.getByRole('button',{name:'Редактировать описание фото 1'})).toBeEnabled();await page.getByRole('button',{name:'Редактировать описание фото 1'}).click();const confirm=page.getByRole('button',{name:'Подтвердить работу и разрешение'});await expect(confirm).toBeDisabled();await page.getByLabel('Подтверждаю: это моя реальная работа').check();await expect(confirm).toBeDisabled();await page.getByLabel('Разрешаю использовать работу для показа клиентам').check();await confirm.click();await expect(page.getByText('Подтверждено для показа',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Подготовить поиск по работам'}).click();await expect(page.getByText(/Поиск по работам готов/)).toBeVisible();await page.getByRole('button',{name:'Опубликовать настройки и портфолио'}).click();await expect(page.getByText(/К настройкам подключено портфолио/)).toBeVisible();expect(h.counts.analysis).toBe(1);
  if(process.env.ASM_PORTFOLIO_SCREENSHOT_DIR){mkdirSync(process.env.ASM_PORTFOLIO_SCREENSHOT_DIR,{recursive:true});await page.getByRole('region',{name:'Портфолио мастера'}).screenshot({path:join(process.env.ASM_PORTFOLIO_SCREENSHOT_DIR,`${testInfo.project.name}-portfolio.png`)});}
  await page.getByLabel('Ответ FAQ 1').fill('Подтверждённое обновление настроек.');await page.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await expect(page.getByRole('button',{name:'Опубликовать настройки и портфолио'})).toBeEnabled();await page.getByRole('button',{name:'Опубликовать настройки и портфолио'}).click();await expect(page.getByRole('button',{name:'Опубликовать настройки и портфолио'})).toBeEnabled();
  await h.open();await expect(page.getByLabel('Готовый набор работ')).toHaveValue(portfolioBuildId);await expect(page.getByLabel('Набор источников для совместной публикации')).toHaveValue(emptyBuildId);expect(h.counts.legacyPublish).toBe(0);expect(h.counts.analysis).toBe(1);
  await page.getByRole('button',{name:'Отозвать работу',exact:true}).click();await expect(page.getByRole('button',{name:'Подготовить пустое портфолио'})).toBeEnabled();await page.getByRole('button',{name:'Подготовить пустое портфолио'}).click();await expect(page.getByText(/Пустое портфолио готово/)).toBeVisible();await page.getByRole('button',{name:'Опубликовать настройки и портфолио'}).click();await expect(page.getByRole('button',{name:'Опубликовать настройки и портфолио'})).toBeEnabled();expect(h.counts.analysis).toBe(1);expect(h.counts.build).toBe(2);
  await page.getByRole('button',{name:'Удалить фото 1',exact:true}).click();await page.getByRole('button',{name:'Удалить фото и карточку'}).click();await expect(page.getByRole('region',{name:'Удаление из хранилища'})).toBeVisible();await h.open();expect(h.counts.purge).toBe(0);await page.getByRole('button',{name:'Повторить удаление файла 1'}).click();await expect(page.getByText('Удаление файла из хранилища подтверждено.',{exact:true})).toBeVisible();expect(h.counts.purge).toBe(1);expect(h.counts.put).toBe(1);expect(h.counts.analysis).toBe(1);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('controlled lost PUT acknowledgement is followed only by explicit HEAD/GET recovery after reload',async({page})=>{
  const h=await controlled(page);await h.open();let put=0,recovery=0;
  await page.route('**/portfolio/assets/*/versions/*/uploads/*/content',async route=>{put++;h.state().assets[0].versions[0].state='UNKNOWN';await route.abort('failed');});
  await page.route('**/portfolio/assets/*/versions/*/uploads/*/recover',async route=>{recovery++;expect(route.request().headers()['idempotency-key']).toBeUndefined();h.state().assets[0].versions[0].state='STORED';await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({schema_version:1,version_id:versionId,upload_id:uploadId,state:'STORED',recorded:true})});});
  await page.getByLabel('Файл портфолио').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:h.bytes});await page.getByRole('button',{name:'Загрузить фото',exact:true}).click();await expect(page.getByText('Результат передачи неизвестен',{exact:true})).toBeVisible();await h.open();expect(put).toBe(1);expect(recovery).toBe(0);await page.getByRole('button',{name:'Проверить сохранённый файл'}).click();await expect(page.getByRole('button',{name:'Принять загруженное фото'})).toBeEnabled();expect(put).toBe(1);expect(recovery).toBe(1);expect(h.counts.analysis).toBe(0);
});
