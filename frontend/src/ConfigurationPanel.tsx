import { FormEvent, useEffect, useRef, useState } from 'react';
import { Business, Session } from './api';
import { ActiveProjection, Bundle, CommandBody, ConfigurationError, DraftState, FAQ, Operation, Preview, Rule, Service, ValidationIssue, configurationApi, validateCommand, KnowledgeState, KnowledgeOperation, KnowledgeBody, KnowledgeSource, SourceInput, SourceRevision, knowledgeApi, validateKnowledgeCommand } from './configuration-api';

type Props = { session: Session | null; workspace: string; business: Business | null; recover: () => void; expired: () => void; accessDenied?: () => void };
type Intent = {scope:string;actor:string;key:string;phase:'sending'|'uncertain'|'confirmed'} & ({kind:'configuration';operation:Operation;body:CommandBody}|{kind:'knowledge';operation:KnowledgeOperation;body:KnowledgeBody;source?:string});
type View = { scope: string; session: Session | null; draft: DraftState | null; active: ActiveProjection | null; preview: Preview | null; knowledge: KnowledgeState | null; busy: boolean; error: string; notice: string; denied: boolean };
type Release = { id: string; version: string; activation: string };
const blank = (scope: string, session: Session | null): View => ({ scope, session, draft: null, active: null, preview: null, knowledge: null, busy: true, error: '', notice: '', denied: false });
const initialBundle = (): Bundle => ({ schema_version: 1, communication_style: 'NEUTRAL', services: [], rules: [], faqs: [] });
const newId = (prefix: string) => `${prefix}_${crypto.randomUUID().slice(0, 8)}`;
const newService = (): Service => ({ id: newId('service'), name: '', description: '', active: true, intake_fields: [], price: { mode: 'OWNER_QUOTE', amount_minor: null, formula_note: null }, duration: { mode: 'OWNER_DEFINED', minutes: null, rule_note: null }, deposit: { mode: 'NONE', amount_minor: null, percent: null } });
const errors: Record<string, string> = { CSRF_REJECTED: 'Защита сессии изменилась. Проверьте сессию перед новой командой.', ORIGIN_DENIED: 'Сервер отклонил источник запроса.', STALE_STATE: 'Конфликт версии. Загрузите актуальное состояние и проверьте свой черновик перед новым сохранением.', IDEMPOTENCY_KEY_CONFLICT: 'Конфликт ключа команды. Проверьте актуальное состояние перед новой командой.', VALIDATION_FAILED: 'Публикация отклонена: в черновике есть ошибки. Обновите предпросмотр.', VERSION_EXHAUSTED: 'Достигнут предел версии. Новая команда недоступна.', ROLLBACK_NOT_ALLOWED: 'Этот откат недопустим: удалённые или изменённые сведения нельзя восстановить старой публикацией.', BODY_TOO_LARGE: 'Набор слишком большой. Сократите описания, FAQ или число элементов.', INVALID_INPUT: 'Проверьте значения и ссылки в форме.', INVALID_REQUEST: 'Проверьте значения в форме.', RATE_LIMITED: 'Слишком много запросов. Повторите позже.' };
const errorText = (e: unknown) => e instanceof ConfigurationError && errors[e.code] ? errors[e.code] : 'Не удалось получить подтверждение сервера.';

export function ConfigurationPanel({ session, workspace, business, recover, expired, accessDenied }: Props) {
  const permitted = !!session && !!business && business.workspace_id === workspace && session.memberships.some(m => m.workspace_id === workspace && m.role === 'OWNER');
  const scope = permitted ? `${session!.user_account_id}:${workspace}:${business!.id}` : '';
  const current = useRef({ session, workspace, business: business?.id, scope });
  current.current = { session, workspace, business: business?.id, scope };
  const [view, setView] = useState<View>(() => blank(scope, session));
  const [form, setForm] = useState<Bundle>(initialBundle), [rollback, setRollback] = useState('');
  const [showSources,setShowSources]=useState(false),[sourceEdit,setSourceEdit]=useState(''),[sourceForm,setSourceForm]=useState<SourceInput>(sourceInput);
  const [buildChoice,setBuildChoice]=useState(''),[knowledgeRollback,setKnowledgeRollback]=useState(''),[deleteSource,setDeleteSource]=useState('');
  const [, redraw] = useState(0);
  const generation = useRef(0), mounted = useRef(true), controllers = useRef(new Set<AbortController>());
  // Command intent survives a session recheck; it is never placed in browser storage.
  const intents = useRef(new Map<string, Intent>()), releases = useRef(new Map<string, Release[]>());
  const visible = view.scope === scope && view.session === session;
  const pending = scope ? intents.current.get(scope) : undefined;
  const attached = !!pending && pending.actor === session?.user_account_id;
  const loaded = visible && !!view.draft && !!view.active && !view.denied;
  const dirty = loaded && JSON.stringify(form) !== JSON.stringify(view.draft!.bundle ?? initialBundle());
  const locked = !loaded || view.busy || attached;
  const knownReleases = (releases.current.get(scope) ?? []).filter(r => r.id !== view.active?.release_id);
  const knowledgeVisible=loaded&&!!view.knowledge&&view.knowledge.activation_version===view.active!.activation_version&&view.knowledge.release_id===view.active!.release_id;
  const editingSource=knowledgeVisible?view.knowledge!.sources.find(s=>s.source_id===sourceEdit):undefined;
  const sourceDirty=JSON.stringify(sourceForm)!==JSON.stringify(sourceInput(editingSource?.head));
  const sourceBytes=new TextEncoder().encode(sourceForm.text).length;
  const sourceLocked=locked||!knowledgeVisible;
  const confirmedSources=knowledgeVisible?view.knowledge!.sources.filter(s=>s.state==='CONFIRMED'&&s.head.confirmed):[];
  const revisionIds=confirmedSources.map(s=>s.head.revision_id);
  const readyBuilds=knowledgeVisible?view.knowledge!.builds.filter(b=>b.state==='READY'&&b.revision_ids.length===revisionIds.length&&b.revision_ids.every(id=>revisionIds.includes(id))):[];
  const selectedBuild=readyBuilds.find(b=>b.build_id===buildChoice)??readyBuilds[0];
  const owns = (owner: number, principal: Session, context: string, c: AbortController) => mounted.current && !c.signal.aborted && generation.current === owner && current.current.session === principal && current.current.scope === context;
  function remember(context: string, active: ActiveProjection) {
    if (!active.release_id || !active.source_draft_version) return;
    const list = releases.current.get(context) ?? [];
    releases.current.set(context, [...list.filter(r => r.id !== active.release_id), { id: active.release_id, version: active.source_draft_version, activation: active.activation_version }].slice(-8));
  }
  function failure(e: unknown, owner: number, principal: Session, context: string, c: AbortController) {
    if (!owns(owner, principal, context, c)) return;
    if (e instanceof ConfigurationError && e.status === 401) { setView(blank('', null)); expired(); }
    else if (e instanceof ConfigurationError && e.status === 403 && e.code === 'ACCESS_DENIED') { setView({ ...blank(context, principal), busy: false, denied: true, error: 'Нет доступа к настройкам владельца.' }); accessDenied?.(); }
    else if (e instanceof ConfigurationError && e.status === 404) setView({ ...blank(context, principal), busy: false, error: 'Business не найден или недоступен. Обновите доступ.' });
    else setView(v => ({ ...v, busy: false, error: errorText(e) }));
  }
  async function load(preserve = false, confirmed = false, includeSources=false) {
    const context = current.current;
    if (!context.session || !context.scope || !context.business) return;
    const wantsSources=includeSources||showSources||intents.current.get(context.scope)?.kind==='knowledge';
    const principal = context.session, owner = ++generation.current, c = new AbortController();
    controllers.current.forEach(c => c.abort()); controllers.current.clear(); controllers.current.add(c);
    setView(v => v.scope === context.scope && v.session === principal ? { ...v, busy: true, error: '' } : blank(context.scope, principal));
    try {
      const [draft, active, preview, knowledge] = await Promise.all([configurationApi.draft(context.workspace, context.business, c.signal), configurationApi.active(context.workspace, context.business, c.signal), configurationApi.preview(context.workspace, context.business, c.signal),wantsSources?knowledgeApi.state(context.workspace,context.business,c.signal):Promise.resolve(null)]);
      if (!owns(owner, principal, context.scope, c)) return;
      if (preview.state.draft_version !== draft.draft_version || preview.state.activation_version !== draft.activation_version || active.activation_version !== draft.activation_version || JSON.stringify(preview.state.bundle) !== JSON.stringify(draft.bundle)||knowledge!==null&&(knowledge.activation_version!==active.activation_version||knowledge.release_id!==active.release_id)) throw new ConfigurationError(409, 'STALE_STATE');
      remember(context.scope, active); if (!preserve) {setForm(structuredClone(draft.bundle ?? initialBundle()));setSourceForm(sourceInput());setSourceEdit('');setDeleteSource('');}
      if (confirmed) intents.current.delete(context.scope);
      setView({ scope: context.scope, session: principal, draft, active, preview, knowledge, busy: false, error: '', notice: confirmed ? 'Команда подтверждена. Текущее состояние получено.' : '', denied: false });
    } catch (e) { if(wantsSources&&owns(owner,principal,context.scope,c))setView(v=>({...v,knowledge:null}));failure(e, owner, principal, context.scope, c); }
    finally { controllers.current.delete(c); }
  }
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current++; controllers.current.forEach(c => c.abort()); }; }, []);
  useEffect(() => {
    generation.current++; controllers.current.forEach(c => c.abort()); controllers.current.clear();
    for (const intent of intents.current.values()) if (intent.phase === 'sending') intent.phase = 'uncertain';
    setView(blank(scope, session)); setForm(initialBundle()); setRollback('');setShowSources(false);setSourceEdit('');setSourceForm(sourceInput());setBuildChoice('');setKnowledgeRollback('');setDeleteSource(''); if (permitted) void load();
    return () => { generation.current++; controllers.current.forEach(c => c.abort()); controllers.current.clear(); };
  }, [scope, session]);
  async function send(intent: Intent) {
    const context = current.current;
    if (!context.session || context.scope !== intent.scope || context.session.user_account_id !== intent.actor || !context.business || intent.phase === 'sending') return;
    const principal = context.session, owner = generation.current, c = new AbortController(); controllers.current.add(c);
    intent.phase = 'sending'; redraw(n => n + 1); setView(v => ({ ...v, error: '', notice: '' }));
    try {
      if(intent.kind==='knowledge'){
        const result=await knowledgeApi.command(context.workspace,context.business,intent.operation,intent.body,intent.key,principal.csrf_token,intent.source,c.signal);
        if(!owns(owner,principal,intent.scope,c)){intent.phase='uncertain';return;}
        if(result.result.build_id)setBuildChoice(result.result.build_id);
      }else{
        const result = await configurationApi.command(context.workspace, context.business, intent.operation, intent.body, intent.key, principal.csrf_token, c.signal);
        if (!owns(owner, principal, intent.scope, c)) { intent.phase = 'uncertain'; return; }
        if (result.result.release_id) { const list = releases.current.get(intent.scope) ?? []; releases.current.set(intent.scope, [...list.filter(r => r.id !== result.result.release_id), { id: result.result.release_id, version: result.result.draft_version, activation: result.result.activation_version }].slice(-8)); }
      }
      intent.phase = 'confirmed'; redraw(n => n + 1); await load(false, true);
    } catch (e) {
      if (!owns(owner, principal, intent.scope, c)) { intent.phase = 'uncertain'; return; }
      if (e instanceof ConfigurationError && [403,404,409,413,415,422,429].includes(e.status)) {
        intents.current.delete(intent.scope); redraw(n => n + 1); failure(e, owner, principal, intent.scope, c);
        if (e.code === 'STALE_STATE') setView(v => ({ ...v, preview: null }));
      } else {
        intent.phase = 'uncertain'; redraw(n => n + 1);
        if (e instanceof ConfigurationError && e.status === 401) expired();
        else setView(v => ({ ...v, error: 'Результат команды неизвестен. Сохранены исходные ключ и содержимое.' }));
      }
    } finally { controllers.current.delete(c); }
  }
  function start(operation: Operation, event?: FormEvent) {
    event?.preventDefault(); if (locked || !session || !view.draft || !view.active || intents.current.has(scope)) return;
    let body: CommandBody;
    if (operation === 'EDIT') body = { expected_draft_version: view.draft.draft_version, bundle: structuredClone(form) };
    else if (operation === 'PUBLISH') {
      if (dirty || knowledgeVisible&&view.knowledge!.active_build_id!==null || !view.preview?.validation.valid || view.preview.state.draft_version !== view.draft.draft_version) return;
      body = { expected_draft_version: view.draft.draft_version, expected_activation_version: view.active.activation_version };
    } else { if (!knownReleases.some(r => r.id === rollback)) return; body = { expected_activation_version: view.active.activation_version, release_id: rollback }; }
    try { validateCommand(operation, body); } catch (e) { setView(v => ({ ...v, error: e instanceof ConfigurationError && e.code === 'INVALID_RESPONSE' ? 'Заполните обязательные поля и проверьте допустимые размеры.' : errorText(e) })); return; }
    const intent: Intent = { kind:'configuration', scope, actor: session.user_account_id, operation, body, key: crypto.randomUUID(), phase: 'uncertain' };
    if (intents.current.size >= 8) { setView(v => ({ ...v, error: 'Сначала уточните результат предыдущих команд в других бизнесах.' })); return; }
    intents.current.set(scope, intent); void send(intent);
  }
  function startKnowledge(operation:KnowledgeOperation,source?:KnowledgeSource){
    if(sourceLocked||!session||!view.knowledge||!view.draft||intents.current.has(scope)||sourceDirty&&operation!=='KNOWLEDGE_SAVE')return;
    let body:KnowledgeBody;
    if(operation==='KNOWLEDGE_SAVE'){
      body={schema_version:1,source_id:editingSource?.source_id??null,expected_source_version:editingSource?.source_version??'0',...structuredClone(sourceForm)};
    }else if(operation==='KNOWLEDGE_CONFIRM'){
      if(!source||source.state!=='DRAFT'||source.head.confirmed||source.preview.issues.length)return;
      body={schema_version:1,expected_source_version:source.source_version,revision_id:source.head.revision_id,canonical_sha256:source.head.canonical_sha256};
    }else if(operation==='KNOWLEDGE_BUILD_CREATE'){
      if(!confirmedSources.length)return;
      body={schema_version:1,expected_sources_hash:view.knowledge.sources_hash,revision_ids:revisionIds};
    }else if(operation==='KNOWLEDGE_PUBLISH'){
      if(dirty||!selectedBuild||!view.preview?.validation.valid)return;
      body={schema_version:1,expected_draft_version:view.draft.draft_version,expected_activation_version:view.knowledge.activation_version,build_id:selectedBuild.build_id,expected_build_version:selectedBuild.build_version};
    }else if(operation==='KNOWLEDGE_ROLLBACK'){
      if(dirty||!view.knowledge.rollback_targets.some(t=>t.release_id===knowledgeRollback&&t.eligible))return;
      body={schema_version:1,expected_activation_version:view.knowledge.activation_version,release_id:knowledgeRollback};
    }else{
      if(!source)return;
      body={schema_version:1,expected_source_version:source.source_version,expected_activation_version:view.knowledge.activation_version};
    }
    const sourceId=['KNOWLEDGE_CONFIRM','KNOWLEDGE_REVOKE','KNOWLEDGE_DELETE'].includes(operation)?source?.source_id:undefined;
    try{validateKnowledgeCommand(operation,body,sourceId);}catch(e){setView(v=>({...v,error:e instanceof ConfigurationError&&e.code==='INVALID_RESPONSE'?'Проверьте текст, размер и поля источника.':errorText(e)}));return;}
    if(intents.current.size>=8){setView(v=>({...v,error:'Сначала уточните результат предыдущих команд в других бизнесах.'}));return;}
    const intent:Intent={kind:'knowledge',scope,actor:session.user_account_id,operation,body,key:crypto.randomUUID(),phase:'uncertain',source:sourceId};
    intents.current.set(scope,intent);void send(intent);
  }
  const change = (update: Partial<Bundle>) => setForm(b => ({ ...b, ...update }));
  const serviceAt = (i: number, update: Partial<Service>) => change({ services: form.services.map((s,j) => i===j ? { ...s, ...update } : s) });
  const ruleAt = (i: number, update: Partial<Rule>) => change({ rules: form.rules.map((r,j) => i===j ? { ...r, ...update } : r) });
  const faqAt = (i: number, update: Partial<FAQ>) => change({ faqs: form.faqs.map((f,j) => i===j ? { ...f, ...update } : f) });
  if (!permitted) return null;
  return <section className="panel configuration" aria-label="Настройки бизнеса">
    <div className="billing-heading"><div><span className="kicker">УСЛУГИ И ЗНАНИЯ</span><h2>Настройки: {business!.name}</h2><p>Опубликуйте подтверждённые сведения, которыми AI сможет пользоваться в разговоре.</p></div><button className="secondary" disabled={attached||(visible&&view.busy)} onClick={()=>void load(dirty)}>Обновить настройки</button></div>
    {(!visible||view.busy)&&<p role="status">Загружаем настройки…</p>}{visible&&view.error&&<p role="alert" className="error">{view.error}</p>}{visible&&view.denied&&<button onClick={recover}>Проверить доступ к настройкам</button>}{visible&&view.error===errors.CSRF_REJECTED&&<button onClick={recover}>Проверить сессию настроек</button>}
    {loaded&&<>
      <section aria-label="Опубликованные сведения"><h3>Сейчас опубликовано</h3>{view.active!.bundle?<><p>Активация {view.active!.activation_version} · из черновика {view.active!.source_draft_version} · {view.active!.published_at}</p><BundleView bundle={view.active!.bundle}/></>:<p>Публикации ещё нет. AI не получает сведения черновика.</p>}</section>
      <h3>Черновик · версия {view.draft!.draft_version}</h3><p>{dirty?'Есть несохранённые изменения.':'Форма соответствует сохранённому черновику.'} Пустые значения цены, времени и предоплаты означают «неизвестно».</p>
      <form onSubmit={e=>start('EDIT',e)}><fieldset disabled={locked} className="configuration-fields"><legend>Услуги, правила и FAQ</legend>
        <label>Стиль общения<Choice value={form.communication_style} values={{NEUTRAL:'Нейтральный',WARM:'Тёплый',CONCISE:'Краткий'}} change={communication_style=>change({communication_style})}/></label>
        <h4>Услуги</h4>{form.services.map((s,i)=><fieldset key={i} className="configuration-card"><legend>Услуга {i+1}</legend>
          <label>Название услуги {i+1}<input value={s.name} maxLength={100} required onChange={e=>serviceAt(i,{name:e.target.value})}/></label><label>Описание услуги {i+1}<textarea value={s.description} maxLength={500} rows={2} onChange={e=>serviceAt(i,{description:e.target.value})}/></label><label><input type="checkbox" checked={s.active} onChange={e=>serviceAt(i,{active:e.target.checked})}/>Услуга {i+1} доступна для консультации</label>
          <div className="configuration-policy-grid">
            <fieldset><legend>Цена</legend><label>Режим цены {i+1}<Choice value={s.price.mode} values={{FIXED:'Заданная цена',CONFIGURED_FORMULA:'Формула владельца',OWNER_QUOTE:'Решение владельца'}} change={mode=>serviceAt(i,{price:{...s.price,mode}})}/></label><NullableNumber label={`Цена, копейки ${i+1}`} value={s.price.amount_minor} change={amount_minor=>serviceAt(i,{price:{...s.price,amount_minor}})}/><label>Пояснение формулы {i+1}<input value={s.price.formula_note??''} maxLength={160} onChange={e=>serviceAt(i,{price:{...s.price,formula_note:e.target.value||null}})}/></label></fieldset>
            <fieldset><legend>Длительность</legend><label>Режим длительности {i+1}<Choice value={s.duration.mode} values={{FIXED:'Заданное время',CONFIGURED_RULE:'Правило владельца',OWNER_DEFINED:'Решение владельца'}} change={mode=>serviceAt(i,{duration:{...s.duration,mode}})}/></label><NullableNumber label={`Длительность, минуты ${i+1}`} value={s.duration.minutes} change={minutes=>serviceAt(i,{duration:{...s.duration,minutes}})}/><label>Пояснение времени {i+1}<input value={s.duration.rule_note??''} maxLength={160} onChange={e=>serviceAt(i,{duration:{...s.duration,rule_note:e.target.value||null}})}/></label></fieldset>
            <fieldset><legend>Предоплата</legend><label>Режим предоплаты {i+1}<Choice value={s.deposit.mode} values={{NONE:'Без предоплаты',FIXED_DEPOSIT:'Фиксированная сумма',PERCENT_DEPOSIT:'Процент',FULL_PREPAYMENT:'Полная предоплата'}} change={mode=>serviceAt(i,{deposit:{...s.deposit,mode}})}/></label><NullableNumber label={`Предоплата, копейки ${i+1}`} value={s.deposit.amount_minor} change={amount_minor=>serviceAt(i,{deposit:{...s.deposit,amount_minor}})}/><NullableNumber label={`Предоплата, процент ${i+1}`} value={s.deposit.percent} change={percent=>serviceAt(i,{deposit:{...s.deposit,percent}})}/></fieldset>
          </div><p className="muted">Режимы независимы. При смене режима проверьте и очистите неприменимые значения. Формулы и обязательства здесь не исполняются.</p>
          <h5>Что уточнить у клиента</h5>{s.intake_fields.map((f,j)=><div key={j}><label>Вопрос {j+1} услуги {i+1}<input required maxLength={100} value={f.label} onChange={e=>serviceAt(i,{intake_fields:s.intake_fields.map((x,k)=>j===k?{...x,label:e.target.value}:x)})}/></label><label><input type="checkbox" checked={f.required} onChange={e=>serviceAt(i,{intake_fields:s.intake_fields.map((x,k)=>j===k?{...x,required:e.target.checked}:x)})}/>Обязательный вопрос {j+1} услуги {i+1}</label><button type="button" className="secondary" onClick={()=>serviceAt(i,{intake_fields:s.intake_fields.filter((_,k)=>j!==k)})}>Удалить вопрос {j+1} услуги {i+1}</button></div>)}<div className="control-actions"><button type="button" className="secondary" disabled={s.intake_fields.length>=6} onClick={()=>serviceAt(i,{intake_fields:[...s.intake_fields,{id:newId('question'),label:'',required:false}]})}>Добавить вопрос услуги {i+1}</button><button type="button" className="danger" onClick={()=>change({services:form.services.filter((_,j)=>i!==j)})}>Удалить услугу {i+1}</button></div>
        </fieldset>)}<button type="button" className="secondary" disabled={form.services.length>=8} onClick={()=>change({services:[...form.services,newService()]})}>Добавить услугу</button>
        <h4>Структурированные правила</h4><p>Эти правила имеют приоритет над поясняющими FAQ.</p>{form.rules.map((r,i)=><fieldset key={i} className="configuration-card"><legend>Правило {i+1}</legend><ServiceChoice label={`Услуга правила ${i+1}`} value={r.service_id} services={form.services} change={service_id=>ruleAt(i,{service_id})}/><label>Тип правила {i+1}<Choice value={r.kind} values={{MIN_AGE:'Минимальный возраст',OWNER_HANDOFF:'Решение владельца'}} change={kind=>ruleAt(i,{kind,value:kind==='OWNER_HANDOFF'?false:18})}/></label>{r.kind==='OWNER_HANDOFF'?<label><input type="checkbox" checked={r.value===true} onChange={e=>ruleAt(i,{value:e.target.checked})}/>Нужно решение владельца по правилу {i+1}</label>:<NullableNumber label={`Значение правила ${i+1}`} value={typeof r.value==='number'?r.value:null} change={value=>ruleAt(i,{value:value??0})}/>}<button type="button" className="danger" onClick={()=>change({rules:form.rules.filter((_,j)=>i!==j)})}>Удалить правило {i+1}</button></fieldset>)}<button type="button" className="secondary" disabled={form.rules.length>=12} onClick={()=>change({rules:[...form.rules,{id:newId('rule'),service_id:null,kind:'MIN_AGE',value:18}]})}>Добавить правило</button>
        <h4>Подтверждённые FAQ</h4>{form.faqs.map((f,i)=><fieldset key={i} className="configuration-card"><legend>FAQ {i+1}</legend><ServiceChoice label={`Услуга FAQ ${i+1}`} value={f.service_id} services={form.services} change={service_id=>faqAt(i,{service_id})}/><label>Вопрос FAQ {i+1}<input required maxLength={200} value={f.question} onChange={e=>faqAt(i,{question:e.target.value})}/></label><label>Ответ FAQ {i+1}<textarea required maxLength={500} rows={3} value={f.answer} onChange={e=>faqAt(i,{answer:e.target.value})}/></label><label>Источник FAQ {i+1}<input maxLength={120} value={f.source} onChange={e=>faqAt(i,{source:e.target.value})}/></label><label><input type="checkbox" checked={f.confirmed} onChange={e=>faqAt(i,{confirmed:e.target.checked})}/>Владелец подтвердил FAQ {i+1}</label><fieldset><legend>Связанные правила FAQ {i+1}</legend>{[...form.rules.map(r=>r.id),...f.rule_ids.filter(id=>!form.rules.some(r=>r.id===id))].map(id=><label key={id}><input type="checkbox" checked={f.rule_ids.includes(id)} disabled={!f.rule_ids.includes(id)&&f.rule_ids.length>=6} onChange={e=>faqAt(i,{rule_ids:e.target.checked?[...f.rule_ids,id]:f.rule_ids.filter(x=>x!==id)})}/>{ruleLabel(form.rules.find(r=>r.id===id),form)}</label>)}</fieldset><button type="button" className="danger" onClick={()=>change({faqs:form.faqs.filter((_,j)=>i!==j)})}>Удалить FAQ {i+1}</button></fieldset>)}<button type="button" className="secondary" disabled={form.faqs.length>=12} onClick={()=>change({faqs:[...form.faqs,{id:newId('faq'),service_id:null,question:'',answer:'',source:'',confirmed:false,rule_ids:[]}]})}>Добавить FAQ</button><button type="submit" disabled={!dirty}>Сохранить черновик</button>
      </fieldset></form>
      <section aria-label="Предпросмотр публикации"><h3>Предпросмотр</h3><p>Детерминированная проверка сохранённого черновика. Вызовы AI и отправка клиенту не выполняются.</p><button className="secondary" disabled={locked||dirty} onClick={()=>void load()}>Проверить и показать предпросмотр</button>{dirty&&<p>Сначала сохраните изменения черновика.</p>}{view.preview&&<><ul className="configuration-issues">{view.preview.validation.issues.map((issue,i)=><li key={i} className={issue.severity==='ERROR'?'error':'muted'}>{issue.severity==='ERROR'?'ERROR — ошибка':'WARNING — предупреждение'}: {issueLabel(issue,view.preview!.state.bundle)}</li>)}</ul><p>{view.preview.validation.valid?'Ошибок публикации нет.':'Публикация заблокирована ошибками.'}</p>{view.preview.state.bundle&&<details><summary>Сведения сохранённого черновика</summary><BundleView bundle={view.preview.state.bundle}/></details>}</>}<p>Для совместной публикации настроек и поиска используйте готовый набор в разделе источников.</p>{knowledgeVisible&&view.knowledge!.active_build_id&&<p>Текущий набор источников подключён. Опубликуйте изменения кнопкой «Опубликовать источники».</p>}<button disabled={locked||dirty||!view.preview?.validation.valid||knowledgeVisible&&view.knowledge!.active_build_id!==null} onClick={()=>start('PUBLISH')}>Опубликовать черновик</button></section>
      <section aria-label="Откат публикации"><h3>Откат</h3><p>Можно выбрать прежнюю публикацию, просмотренную в этой сессии страницы. Сервер проверит допустимость; активация всегда будет новой.</p><label>Предыдущая публикация<select value={rollback} disabled={locked||knownReleases.length===0} onChange={e=>setRollback(e.target.value)}><option value="">Выберите публикацию</option>{knownReleases.map(r=><option key={r.id} value={r.id}>Из черновика {r.version} · активация {r.activation}</option>)}</select></label><button className="secondary" disabled={locked||!knownReleases.some(r=>r.id===rollback)} onClick={()=>start('ROLLBACK')}>Откатить публикацию</button></section>
    </>}

    {loaded&&<section aria-label="Источники для поиска" className="knowledge-sources">
      <h3>Источники для поиска</h3><p>Подготовьте небольшой текст, проверьте его и подтвердите перед публикацией.</p>
      <button className="secondary" disabled={locked} onClick={()=>{setShowSources(true);void load(dirty||sourceDirty,false,true);}}>Посмотреть источники</button>
      {showSources&&!knowledgeVisible&&<p role="status">Источники пока не загружены.</p>}
      {showSources&&knowledgeVisible&&<>
        <p>{view.knowledge!.active_build_id?'Опубликованный поиск подключён к текущим настройкам.':'Поиск по источникам ещё не опубликован.'}</p>
        {view.knowledge!.embedding_mode==='DISABLED'&&<p className="muted">Индексация сейчас отключена. Подготовленный текст можно сохранить и подтвердить.</p>}
        <form onSubmit={e=>{e.preventDefault();startKnowledge('KNOWLEDGE_SAVE');}}><fieldset disabled={sourceLocked} className="configuration-fields">
          <legend>{editingSource?'Новая ревизия источника':'Новый источник'}</legend>
          <label>Заголовок источника<input required maxLength={120} value={sourceForm.title} onChange={e=>setSourceForm(v=>({...v,title:e.target.value}))}/></label>
          <label>Формат источника<Choice value={sourceForm.format} values={{TEXT:'Текст',MARKDOWN:'Markdown как текст'}} change={format=>setSourceForm(v=>({...v,format:format as SourceInput['format']}))}/></label>
          <label>Текст источника<textarea required rows={6} maxLength={2048} value={sourceForm.text} onChange={e=>setSourceForm(v=>({...v,text:e.target.value}))}/></label>
          <p className={sourceBytes>2048?'error':'muted'}>Размер текста: {sourceBytes} из 2048 байт. {sourceDirty?'Есть несохранённый текст.':'Изменений текста нет.'}</p>
          <label>Происхождение источника<input required maxLength={120} value={sourceForm.source_label} onChange={e=>setSourceForm(v=>({...v,source_label:e.target.value}))}/></label>
          <label>Автор (необязательно)<input maxLength={80} value={sourceForm.author_label??''} onChange={e=>setSourceForm(v=>({...v,author_label:e.target.value||null}))}/></label>
          <ServiceChoice label="Услуга источника" value={sourceForm.service_id} services={view.draft!.bundle?.services??[]} change={service_id=>setSourceForm(v=>({...v,service_id}))}/>
          <details><summary>Тема, категория и срок действия</summary>
            <p className="muted">Короткие обозначения латиницей, без пробелов. Одинаковая тема связывает утверждения, которые нужно проверить на противоречие.</p>
            <label>Тема утверждения<input maxLength={40} pattern="[a-z][a-z0-9_-]{0,39}" value={sourceForm.claim_key??''} onChange={e=>setSourceForm(v=>({...v,claim_key:e.target.value||null}))}/></label>
            <label>Категория источника<input maxLength={40} pattern="[a-z][a-z0-9_-]{0,39}" value={sourceForm.category??''} onChange={e=>setSourceForm(v=>({...v,category:e.target.value||null}))}/></label>
            <label>Действует с<input type="datetime-local" value={localTime(sourceForm.effective_from)} onChange={e=>setSourceForm(v=>({...v,effective_from:wireTime(e.target.value)}))}/></label>
            <label>Действует до<input type="datetime-local" value={localTime(sourceForm.effective_until)} onChange={e=>setSourceForm(v=>({...v,effective_until:wireTime(e.target.value)}))}/></label>
          </details>
          <div className="control-actions"><button type="submit" disabled={!sourceDirty||sourceBytes>2048||!editingSource&&view.knowledge!.sources.length>=8}>Сохранить источник</button><button type="button" className="secondary" onClick={()=>{setSourceEdit('');setSourceForm(sourceInput());}}>Очистить форму источника</button></div>
        </fieldset></form>
        {view.knowledge!.sources.length===0&&<p>Сохранённых источников ещё нет.</p>}
        {view.knowledge!.sources.map(s=><article key={s.source_id} className="configuration-card" aria-label={`Источник: ${s.head.title}`}>
          <h4>{s.head.title} · {s.state==='CONFIRMED'?'Подтверждён':s.state==='REVOKED'?'Отозван':'Черновик'}</h4>
          <p className="muted">Источник: {s.head.source_label}{s.head.author_label?` · автор: ${s.head.author_label}`:''} · ревизия {s.head.revision_no}</p>
          <pre className="knowledge-source-text">{s.head.canonical_text}</pre>
          <p>Фрагментов после проверки: {s.preview.chunks.length}.</p>
          {s.preview.issues.map(issue=><p key={issue} role="alert" className="error">{issue==='CHUNK_LIMIT'?'Текст не помещается в четыре фрагмента. Сократите его и сохраните новую ревизию.':'Проверьте размер и содержимое текста.'}</p>)}
          <div className="control-actions">
            <button disabled={sourceLocked||sourceDirty||s.state!=='DRAFT'||s.head.confirmed||s.preview.issues.length>0} onClick={()=>startKnowledge('KNOWLEDGE_CONFIRM',s)}>Подтвердить источник</button>
            <button className="secondary" disabled={sourceLocked||sourceDirty} onClick={()=>{setSourceEdit(s.source_id);setSourceForm(sourceInput(s.head));}}>Редактировать источник</button>
            <button className="danger" disabled={sourceLocked||sourceDirty||s.state==='REVOKED'} onClick={()=>startKnowledge('KNOWLEDGE_REVOKE',s)}>Отозвать источник</button>
            <button className="danger" disabled={sourceLocked||sourceDirty} onClick={()=>setDeleteSource(s.source_id)}>Удалить источник</button>
          </div>
          {deleteSource===s.source_id&&<div className="notice"><p>Текст и его индекс будут удалены без восстановления через старую публикацию.</p><button className="danger" disabled={sourceLocked||sourceDirty} onClick={()=>startKnowledge('KNOWLEDGE_DELETE',s)}>Удалить текст и индекс</button><button className="secondary" disabled={sourceLocked} onClick={()=>setDeleteSource('')}>Сохранить источник без удаления</button></div>}
        </article>)}
        <p className="muted">Отзыв исключает опубликованные ревизии. Для возвращения текста сохраните новую ревизию и подтвердите её.</p>
        <section aria-label="Подготовка поиска"><h4>Подготовить и опубликовать поиск</h4>
          <button disabled={sourceLocked||sourceDirty||confirmedSources.length===0} onClick={()=>startKnowledge('KNOWLEDGE_BUILD_CREATE')}>Подготовить поиск</button>
          {view.knowledge!.builds.map(b=><p key={b.build_id} role={b.state==='ERROR'||b.state==='UNKNOWN'?'alert':undefined} className={b.state==='ERROR'||b.state==='UNKNOWN'?'error':'muted'}>{buildLabel[b.state]} · фрагментов {b.chunk_count}{b.error_code?` · ${buildError(b.error_code,view.knowledge!.embedding_mode)}`:''}</p>)}
          <label>Готовый набор источников<select disabled={sourceLocked||readyBuilds.length===0} value={selectedBuild?.build_id??''} onChange={e=>setBuildChoice(e.target.value)}><option value="">Нет готового набора</option>{readyBuilds.map((b,i)=><option key={b.build_id} value={b.build_id}>Набор {i+1} · фрагментов {b.chunk_count}</option>)}</select></label>
          <p>Публикация включает сохранённый черновик настроек и готовый набор источников.</p>
          {(dirty||sourceDirty)&&<p>Сначала сохраните изменения настроек и текста.</p>}
          <button disabled={sourceLocked||sourceDirty||dirty||!view.preview?.validation.valid||!selectedBuild} onClick={()=>startKnowledge('KNOWLEDGE_PUBLISH')}>Опубликовать источники</button>
        </section>
        <section aria-label="Откат источников"><h4>Предыдущая публикация с источниками</h4>
          <label>Набор для отката<select disabled={sourceLocked||sourceDirty} value={knowledgeRollback} onChange={e=>setKnowledgeRollback(e.target.value)}><option value="">Выберите публикацию</option>{view.knowledge!.rollback_targets.filter(t=>t.release_id!==view.knowledge!.release_id).map((t,i)=><option key={t.release_id} value={t.release_id} disabled={!t.eligible}>Публикация {i+1}{t.eligible?'':' · недоступна'}</option>)}</select></label>
          <button className="secondary" disabled={sourceLocked||sourceDirty||dirty||!view.knowledge!.rollback_targets.some(t=>t.release_id===knowledgeRollback&&t.eligible)} onClick={()=>startKnowledge('KNOWLEDGE_ROLLBACK')}>Вернуть публикацию источников</button>
        </section>
      </>}
    </section>}
    {visible&&view.notice&&<p role="status">{view.notice}</p>}{attached&&pending&&<div className="notice" aria-live="polite">{pending.phase==='sending'?<p>Выполняем команду. Повторный submit заблокирован.</p>:pending.phase==='confirmed'?<><p>Команда подтверждена. Нужно повторить только чтение состояния.</p><button onClick={()=>void load(false,true)}>Повторить чтение настроек</button></>:<><p>Результат команды неизвестен. Повтор использует исходные ключ и содержимое.</p><button onClick={recover}>Проверить сессию для команды</button><button onClick={()=>void send(pending)}>Повторить исходную команду</button></>}</div>}
  </section>;
}
function Choice({value,values,change}:{value:string;values:Record<string,string>;change:(v:string)=>void}){return <select value={value} onChange={e=>change(e.target.value)}>{!Object.hasOwn(values,value)&&<option value={value}>Неизвестный режим: {value}</option>}{Object.entries(values).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>;}
function NullableNumber({label,value,change}:{label:string;value:number|null;change:(n:number|null)=>void}){return <label>{label}<input type="number" min={0} max={100000000000} step={1} value={value??''} onChange={e=>change(e.target.value===''?null:e.target.valueAsNumber)}/></label>;}
function ServiceChoice({label,value,services,change}:{label:string;value:string|null;services:Service[];change:(v:string|null)=>void}){return <label>{label}<select value={value??''} onChange={e=>change(e.target.value||null)}><option value="">Все услуги</option>{value&&!services.some(s=>s.id===value)&&<option value={value}>Недоступная услуга</option>}{services.map((s,i)=><option key={i} value={s.id}>{s.name||`Услуга ${i+1}`}</option>)}</select></label>;}
function BundleView({bundle}:{bundle:Bundle}){return <div className="configuration-facts"><p>Стиль: {({NEUTRAL:'Нейтральный',WARM:'Тёплый',CONCISE:'Краткий'} as Record<string,string>)[bundle.communication_style]??bundle.communication_style}</p><h4>Услуги</h4>{bundle.services.map((s,i)=><article key={i}><h5>{s.name} · {s.active?'Активна':'Неактивна'}</h5><p>{s.description}</p><ul><li>Цена: {policyLabel[s.price.mode]??s.price.mode} · {s.price.amount_minor===null?'неизвестна':`${s.price.amount_minor/100} ₽`}{s.price.formula_note?` · ${s.price.formula_note}`:''}</li><li>Длительность: {policyLabel[s.duration.mode]??s.duration.mode} · {s.duration.minutes===null?'неизвестна':`${s.duration.minutes} мин`}{s.duration.rule_note?` · ${s.duration.rule_note}`:''}</li><li>Предоплата: {policyLabel[s.deposit.mode]??s.deposit.mode} · сумма {s.deposit.amount_minor===null?'неизвестна':`${s.deposit.amount_minor/100} ₽`} · процент {s.deposit.percent??'неизвестен'}</li></ul>{s.intake_fields.length>0&&<p>Уточнить: {s.intake_fields.map(f=>`${f.label}${f.required?' (обязательно)':''}`).join('; ')}</p>}</article>)}<h4>Правила</h4><ul>{bundle.rules.map((r,i)=><li key={i}>{ruleLabel(r,bundle)}</li>)}</ul><h4>FAQ</h4>{bundle.faqs.map((f,i)=><article key={i}><strong>{f.question}</strong><p className="message-text">{f.answer}</p><p className="muted">Источник: {f.source||'не указан'} · {f.confirmed?'подтверждено владельцем':'не подтверждено'}</p></article>)}</div>;}

const policyLabel:Record<string,string>={FIXED:'Задано владельцем',CONFIGURED_FORMULA:'Формула владельца',OWNER_QUOTE:'Решение владельца',CONFIGURED_RULE:'Правило владельца',OWNER_DEFINED:'Решение владельца',NONE:'Без предоплаты',FIXED_DEPOSIT:'Фиксированная сумма',PERCENT_DEPOSIT:'Процент',FULL_PREPAYMENT:'Полная предоплата'};
function ruleLabel(rule:Rule|undefined,bundle:Bundle){if(!rule)return 'Недоступное правило';return `${rule.kind==='MIN_AGE'?'Минимальный возраст':rule.kind==='OWNER_HANDOFF'?'Решение владельца':rule.kind}: ${typeof rule.value==='boolean'?(rule.value?'да':'нет'):rule.value} · ${rule.service_id?bundle.services.find(s=>s.id===rule.service_id)?.name??'Недоступная услуга':'Все услуги'}`;}
function issueLabel(issue:ValidationIssue,bundle:Bundle|null){const labels:Record<string,string>={INVALID_SHAPE:'Проверьте размер и заполнение набора.',INVALID_STYLE:'Выберите допустимый стиль общения.',NO_ACTIVE_SERVICE:'Добавьте хотя бы одну активную услугу.',DUPLICATE_ID:'В наборе повторяются элементы.',INVALID_MODE:'Выберите допустимый режим.',INVALID_POLICY:'Проверьте значения и очистите поля, неприменимые к выбранному режиму.',INVALID_REFERENCE:'Проверьте связанные услуги и правила.',INVALID_RULE:'Проверьте тип и значение правила.',CONFLICTING_RULES:'Структурированные правила противоречат друг другу.',UNCONFIRMED_FAQ:'Укажите источник FAQ и подтвердите сведения.',OWNER_HANDOFF:'Для неизвестного или нерассчитанного условия потребуется решение владельца.'};const parts=issue.path.split('.');let location=parts[0]==='services'?'Услуги':parts[0]==='faqs'?'FAQ':parts[0]==='rules'?'Правила':'Настройки';if(parts[0]==='services'&&parts[1])location=bundle?.services.find(s=>s.id===parts[1])?.name??location;if(parts[0]==='faqs'&&parts[1])location=bundle?.faqs.find(f=>f.id===parts[1])?.question??location;const field:Record<string,string>={price:'цена',duration:'длительность',deposit:'предоплата',intake_fields:'вопросы клиенту',source:'источник',rule_ids:'связанные правила',service_id:'услуга'};if(parts[2]&&field[parts[2]])location+=` · ${field[parts[2]]}`;return `${location}: ${labels[issue.code]??'Проверьте сведения.'}`;}


function sourceInput(head?:SourceRevision):SourceInput{
  return head?{title:head.title,format:head.format,text:head.canonical_text,source_label:head.source_label,author_label:head.author_label,service_id:head.service_id,category:head.category,claim_key:head.claim_key,effective_from:head.effective_from,effective_until:head.effective_until}:{title:'',format:'TEXT',text:'',source_label:'Владелец',author_label:null,service_id:null,category:null,claim_key:null,effective_from:null,effective_until:null};
}
function localTime(value:string|null):string{
  if(!value)return '';const d=new Date(value),pad=(n:number)=>String(n).padStart(2,'0');
  return `${String(d.getFullYear()).padStart(4,'0')}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function wireTime(value:string):string|null{if(!value)return null;const d=new Date(value);return Number.isNaN(d.valueOf())?null:d.toISOString().replace(/Z$/,'000Z');}
const buildLabel:Record<string,string>={PLANNED:'Набор подготовлен',BUILDING:'Идёт индексация',READY:'Поиск готов к публикации',ERROR:'Ошибка индексации',UNKNOWN:'Результат индексации неизвестен'};
function buildError(code:string,mode:string):string{return code==='SOURCE_STALE'?'Источники изменились. Подготовьте новый набор.':code==='DEADLINE'?'Время подготовки истекло. Прежняя публикация сохранена.':mode==='DISABLED'?'Индексация отключена. Текст и прежняя публикация сохранены.':'Прежняя публикация сохранена. Проверьте источники перед новым набором.';}
Object.assign(errors,{SOURCE_LIMIT:'Можно сохранить до восьми источников. Удалите ненужный источник.',SOURCE_DELETED:'Источник уже удалён. Обновите состояние.',SOURCE_REVOKED:'Эта ревизия отозвана. Сохраните новую ревизию.',SOURCE_EXPIRED:'Срок действия источника истёк.',SOURCE_STALE:'Источники изменились. Обновите состояние и подготовьте новый набор.',UNCONFIRMED_SOURCE:'Сначала подтвердите сохранённые источники.',CHUNK_LIMIT:'Текст не помещается в четыре фрагмента. Сократите его.',BUILD_NOT_READY:'Набор не готов или уже устарел. Обновите состояние.',PROFILE_MISMATCH:'Индексация недоступна. Прежняя публикация сохранена.',INVALID_REFERENCE:'Проверьте выбранную услугу источника.',INVALID_VECTOR:'Индексация отклонена. Прежняя публикация сохранена.',OPERATION_EXPIRED:'Время подготовки истекло. Обновите состояние.',BUDGET_EXHAUSTED:'Попытка индексации завершена. Обновите состояние.'});
