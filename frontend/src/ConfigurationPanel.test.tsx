import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigurationPanel } from './ConfigurationPanel';
import { App } from './App';
import { api } from './api';
vi.mock('./BillingPanel',()=>({BillingPanel:()=>null}));
vi.mock('./MessagingPanel',()=>({MessagingPanel:()=>null}));
vi.mock('./EscalationsPanel',()=>({EscalationsPanel:()=>null}));
import { ActiveProjection, Bundle, ConfigurationError, DraftState, configurationApi, KnowledgeState, KnowledgeCommand, knowledgeApi, normalizeSource } from './configuration-api';
import { active, bundle, business, businessId, command, deferred, draft, preview, releaseId, session, workspace, knowledgeSource, knowledgeState, knowledgeCommand, readyBuild, sourceId, revisionId, buildId, emptyReadyBuild, emptyBuildId } from './configuration-fixtures.test-helper';
import { portfolioApi } from './portfolio-api';
import { ownerState, photo, confirmedItem, portfolioBuild, portfolioBuildId, portfolioCommand } from './portfolio-fixtures.test-helper';
let state:DraftState,current:ActiveProjection;
beforeEach(()=>{state=draft();current=active();vi.spyOn(portfolioApi,'state').mockImplementation(async(w,b)=>{const kb=await vi.mocked(knowledgeApi.state).mock.results.at(-1)?.value;return {...ownerState(),workspace_id:w,business_id:b,draft_version:state.draft_version,activation_version:current.activation_version,active_release_id:current.release_id,active_knowledge_build_id:kb?.active_build_id??null};});vi.spyOn(knowledgeApi,'state').mockImplementation(async(w,b)=>structuredClone({...knowledgeState(),workspace_id:w,business_id:b,activation_version:current.activation_version,release_id:current.release_id}));vi.spyOn(configurationApi,'draft').mockImplementation(async()=>structuredClone(state));vi.spyOn(configurationApi,'active').mockImplementation(async()=>structuredClone(current));vi.spyOn(configurationApi,'preview').mockImplementation(async()=>preview(structuredClone(state)));vi.spyOn(configurationApi,'command').mockImplementation(async(_w,_b,op,body)=>{
  if(op==='EDIT'&&'bundle'in body)state={...state,draft_version:String(BigInt(state.draft_version)+1n),bundle:structuredClone(body.bundle)};
  else{const id=op==='ROLLBACK'&&'release_id'in body?body.release_id:releaseId;state={...state,activation_version:String(BigInt(state.activation_version)+1n),release_id:id};current=active(structuredClone(state.bundle!),state.activation_version,id,state.draft_version);}
  return command(op,state.draft_version,state.activation_version,state.release_id);
});});
afterEach(()=>vi.restoreAllMocks());
const setup=()=>{const props={session:session(),workspace,business:business(),recover:vi.fn(),expired:vi.fn(),accessDenied:vi.fn()};return{...render(<ConfigurationPanel {...props}/>),props};};
const ready=async()=>{await waitFor(()=>expect(screen.getByLabelText('Название услуги 1')).toBeEnabled());};
async function editFAQ(text='Новый подтверждённый ответ'){await ready();fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:text}});fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByText('Команда подтверждена. Текущее состояние получено.');}
describe('business configuration owner flow',()=>{
  it('attaches settings only to selected Business and propagates live owner denial in Console',async()=>{vi.spyOn(api,'session').mockResolvedValue(session());vi.spyOn(api,'businesses').mockResolvedValue([business()]);vi.spyOn(api,'business').mockResolvedValue(business());render(<App/>);await screen.findByRole('button',{name:/Тестовая мастерская/});expect(configurationApi.draft).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:/Тестовая мастерская/}));await ready();expect(configurationApi.draft).toHaveBeenCalledWith(workspace,businessId,expect.any(AbortSignal));vi.mocked(configurationApi.active).mockRejectedValueOnce(new ConfigurationError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить настройки'}));await screen.findByText('Нет доступа к данным владельца');expect(screen.queryByRole('region',{name:'Настройки бизнеса'})).toBeNull();});
  it('renders draft/active separately and saves FAQ while preserving independent nullable policies/intake/rule provenance',async()=>{setup();await ready();expect(screen.getByText('Публикации ещё нет. AI не получает сведения черновика.')).toBeVisible();await editFAQ();expect(configurationApi.command).toHaveBeenCalledTimes(1);const [_w,_b,op,body]=vi.mocked(configurationApi.command).mock.calls[0];expect(op).toBe('EDIT');expect(body).toEqual({expected_draft_version:'1',bundle:{...bundle(),faqs:[{...bundle().faqs[0],answer:'Новый подтверждённый ответ'}]}});expect(screen.getByLabelText('Цена, копейки 1')).toHaveValue(null);expect(screen.getByLabelText('Длительность, минуты 1')).toHaveValue(90);expect(screen.getByLabelText('Предоплата, процент 1')).toHaveValue(30);expect(screen.getByText('Публикации ещё нет. AI не получает сведения черновика.')).toBeVisible();});
  it('publishes only saved validated preview and shows active revision/source after a real response',async()=>{setup();await editFAQ();fireEvent.click(screen.getByRole('button',{name:'Опубликовать черновик'}));await screen.findByText(/Активация 1 · из черновика 2/);const region=within(screen.getByRole('region',{name:'Опубликованные сведения'}));expect(region.getByText('Новый подтверждённый ответ')).toBeVisible();expect(region.getByText(/Источник: Памятка владельца/)).toBeVisible();expect(vi.mocked(configurationApi.command).mock.calls[1][3]).toEqual({expected_draft_version:'2',expected_activation_version:'0'});});
  it('blocks publish for ERROR and for unsaved edits; deterministic preview is read-only',async()=>{vi.mocked(configurationApi.preview).mockResolvedValue(preview(state,false));setup();await ready();expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();expect(screen.getByText('ERROR — ошибка: Правила: Структурированные правила противоречат друг другу.')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Проверить и показать предпросмотр'}));await ready();expect(configurationApi.command).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('Источник FAQ 1'),{target:{value:'Мой источник'}});expect(screen.getByRole('button',{name:'Проверить и показать предпросмотр'})).toBeDisabled();expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();});
  it('provides service/rule/FAQ/style forms including intake and independent unknown inputs without JSON editing',async()=>{setup();await ready();fireEvent.change(screen.getByLabelText('Стиль общения'),{target:{value:'CONCISE'}});fireEvent.change(screen.getByLabelText('Длительность, минуты 1'),{target:{value:''}});fireEvent.click(screen.getByRole('button',{name:'Добавить услугу'}));fireEvent.change(screen.getByLabelText('Название услуги 2'),{target:{value:'Вторая услуга'}});fireEvent.click(screen.getByRole('button',{name:'Добавить вопрос услуги 2'}));fireEvent.change(screen.getByLabelText('Вопрос 1 услуги 2'),{target:{value:'Что нужно?'}});fireEvent.click(screen.getByRole('button',{name:'Добавить правило'}));fireEvent.change(screen.getByLabelText('Тип правила 2'),{target:{value:'OWNER_HANDOFF'}});fireEvent.click(screen.getByLabelText('Нужно решение владельца по правилу 2'));fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByText('Команда подтверждена. Текущее состояние получено.');const body=vi.mocked(configurationApi.command).mock.calls[0][3];expect('bundle'in body).toBe(true);if('bundle'in body){expect(body.bundle.communication_style).toBe('CONCISE');expect(body.bundle.services[0].duration.minutes).toBeNull();expect(body.bundle.services[0].price).toEqual(bundle().services[0].price);expect(body.bundle.rules[1].value).toBe(true);expect(body.bundle.services[1].intake_fields[0].label).toBe('Что нужно?');}expect(screen.queryByLabelText(/JSON/)).toBeNull();});
  it('keeps uncertain command exact, blocks duplicate submit, and recovers it after session refresh',async()=>{const pending=deferred<ReturnType<typeof command>>();vi.mocked(configurationApi.command).mockImplementationOnce(()=>pending.promise);const v=setup();await ready();fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:'Неизвестный результат'}});const form=screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!;fireEvent.submit(form);fireEvent.submit(form);expect(configurationApi.command).toHaveBeenCalledTimes(1);expect(screen.getByLabelText('Ответ FAQ 1')).toBeDisabled();await act(async()=>pending.reject(new TypeError('network')));await screen.findByRole('button',{name:'Повторить исходную команду'});const original=vi.mocked(configurationApi.command).mock.calls[0];v.rerender(<ConfigurationPanel {...v.props} session={session('new-csrf')}/>);await screen.findByRole('button',{name:'Повторить исходную команду'});fireEvent.click(screen.getByRole('button',{name:'Повторить исходную команду'}));await screen.findByText('Команда подтверждена. Текущее состояние получено.');const retry=vi.mocked(configurationApi.command).mock.calls[1];expect(retry.slice(0,5)).toEqual(original.slice(0,5));expect(retry[5]).toBe('new-csrf');});
  it('after acknowledged write/read failure retries only GET, never the command',async()=>{setup();await ready();vi.mocked(configurationApi.draft).mockRejectedValueOnce(new ConfigurationError(503,'UNAVAILABLE'));fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:'Confirmed'}});fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByRole('button',{name:'Повторить чтение настроек'});expect(configurationApi.command).toHaveBeenCalledTimes(1);fireEvent.click(screen.getByRole('button',{name:'Повторить чтение настроек'}));await screen.findByText('Команда подтверждена. Текущее состояние получено.');expect(configurationApi.command).toHaveBeenCalledTimes(1);});
  it('explains CSRF denial and checks session explicitly without replaying a rejected command',async()=>{vi.mocked(configurationApi.command).mockRejectedValueOnce(new ConfigurationError(403,'CSRF_REJECTED'));const v=setup();await ready();fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:'Checked after CSRF denial'}});fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByText('Защита сессии изменилась. Проверьте сессию перед новой командой.');expect(configurationApi.command).toHaveBeenCalledTimes(1);expect(v.props.accessDenied).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Проверить сессию настроек'}));expect(v.props.recover).toHaveBeenCalledTimes(1);expect(configurationApi.command).toHaveBeenCalledTimes(1);});
  it('stale version retains local changes, invalidates publish and requires explicit current read',async()=>{vi.mocked(configurationApi.command).mockRejectedValueOnce(new ConfigurationError(409,'STALE_STATE'));setup();await ready();fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:'Мой черновик'}});fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByText(/Конфликт версии/);expect(screen.getByLabelText('Ответ FAQ 1')).toHaveValue('Мой черновик');expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();state={...state,draft_version:'2'};fireEvent.click(screen.getByRole('button',{name:'Обновить настройки'}));await ready();expect(screen.getByLabelText('Ответ FAQ 1')).toHaveValue('Мой черновик');fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);await screen.findByText('Команда подтверждена. Текущее состояние получено.');expect(vi.mocked(configurationApi.command).mock.calls[1][3]).toMatchObject({expected_draft_version:'2'});expect(vi.mocked(configurationApi.command).mock.calls[1][4]).not.toBe(vi.mocked(configurationApi.command).mock.calls[0][4]);});
  it.each(['read','command'] as const)('ignores late %s after Business change, logout and unmount',async phase=>{const delayedRead=deferred<DraftState>(),delayedCommand=deferred<ReturnType<typeof command>>();if(phase==='read')vi.mocked(configurationApi.draft).mockImplementationOnce(()=>delayedRead.promise);const v=setup();if(phase==='command'){await ready();vi.mocked(configurationApi.command).mockImplementationOnce(()=>delayedCommand.promise);fireEvent.change(screen.getByLabelText('Ответ FAQ 1'),{target:{value:'Late private answer'}});fireEvent.submit(screen.getByRole('button',{name:'Сохранить черновик'}).closest('form')!);}const other=business('66666666-6666-4666-8666-666666666666');v.rerender(<ConfigurationPanel {...v.props} business={other}/>);v.rerender(<ConfigurationPanel {...v.props} session={null} business={null}/>);await act(async()=>{if(phase==='read')delayedRead.resolve({...draft(),bundle:{...bundle(),communication_style:'LATE_SECRET'}});else delayedCommand.resolve(command());});expect(screen.queryByRole('region',{name:'Настройки бизнеса'})).toBeNull();expect(screen.queryByText('LATE_SECRET')).toBeNull();expect(v.props.expired).not.toHaveBeenCalled();v.unmount();});
  it('hides owner data on live revocation and never requests settings for ADMIN/PROVIDER',async()=>{const v=setup();await ready();vi.mocked(configurationApi.active).mockRejectedValueOnce(new ConfigurationError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить настройки'}));await screen.findByText('Нет доступа к настройкам владельца.');expect(screen.queryByLabelText('Ответ FAQ 1')).toBeNull();expect(v.props.accessDenied).toHaveBeenCalledTimes(1);for(const role of ['ADMIN','PROVIDER'] as const){v.rerender(<ConfigurationPanel {...v.props} session={{...session(),memberships:[{...session().memberships[0],role}]}}/>);expect(screen.queryByRole('region',{name:'Настройки бизнеса'})).toBeNull();}});
  it('selects a previously observed publication and explains server-disallowed rollback',async()=>{current=active(bundle(),'1',releaseId);state=draft(bundle(),'1','1',releaseId);setup();await ready();await editFAQ('Revision2');const second='77777777-7777-4777-8777-777777777777';vi.mocked(configurationApi.command).mockImplementationOnce(async()=>{current=active(structuredClone(state.bundle!),'2',second,'2');state={...state,activation_version:'2',release_id:second};return command('PUBLISH','2','2',second);});fireEvent.click(screen.getByRole('button',{name:'Опубликовать черновик'}));await screen.findByText(/Активация 2 · из черновика 2/);fireEvent.change(screen.getByLabelText('Предыдущая публикация'),{target:{value:releaseId}});vi.mocked(configurationApi.command).mockRejectedValueOnce(new ConfigurationError(409,'ROLLBACK_NOT_ALLOWED'));fireEvent.click(screen.getByRole('button',{name:'Откатить публикацию'}));await screen.findByText(/Этот откат недопустим/);expect(vi.mocked(configurationApi.command).mock.calls.at(-1)?.[3]).toEqual({expected_activation_version:'2',release_id:releaseId});});
});


describe('confirmed source owner flow',()=>{
  let knowledge:KnowledgeState;
  beforeEach(()=>{
    knowledge=knowledgeState();
    vi.mocked(knowledgeApi.state).mockImplementation(async(w,b)=>structuredClone({...knowledge,workspace_id:w,business_id:b,activation_version:current.activation_version,release_id:current.release_id}));
    vi.spyOn(knowledgeApi,'command').mockImplementation(async(_w,_b,operation,body)=>{
      let result:Partial<KnowledgeCommand['result']>={};
      if(operation==='KNOWLEDGE_SAVE'&&'text'in body){
        const value=normalizeSource(body.text),source=knowledgeSource(value);
        source.head={...source.head,title:body.title,format:body.format,source_label:body.source_label,author_label:body.author_label,service_id:body.service_id,category:body.category,claim_key:body.claim_key,effective_from:body.effective_from,effective_until:body.effective_until};
        knowledge.sources=[source];result={source_id:sourceId,source_version:'1',revision_id:revisionId};
      }else if(operation==='KNOWLEDGE_CONFIRM'){
        knowledge.sources[0]={...knowledge.sources[0],source_version:'2',state:'CONFIRMED',head:{...knowledge.sources[0].head,confirmed:true}};result={source_id:sourceId,source_version:'2',revision_id:revisionId};
      }else if(operation==='KNOWLEDGE_BUILD_CREATE'){
        const prepared='revision_ids'in body&&body.revision_ids.length===0?emptyReadyBuild():readyBuild();
        knowledge.builds=[prepared,...knowledge.builds.filter(b=>b.build_id!==prepared.build_id)];result={build_id:prepared.build_id,build_version:'1'}; // nonempty creation ACK deliberately differs from fresh READY version3
      }else if(operation==='KNOWLEDGE_PUBLISH'){
        if(!('build_id'in body))throw new Error('Expected a joint publication');
        const prepared=knowledge.builds.find(b=>b.build_id===body.build_id)!;
        const activation=String(BigInt(current.activation_version)+1n),release=current.release_id?crypto.randomUUID():releaseId;
        knowledge.active_build_id=prepared.build_id;knowledge.release_id=release;knowledge.activation_version=activation;
        knowledge.rollback_targets=[{release_id:release,build_id:prepared.build_id,eligible:true,reason_code:null},...knowledge.rollback_targets];
        state={...state,activation_version:activation,release_id:release};current=active(structuredClone(state.bundle!),activation,release,state.draft_version);
        result={build_id:prepared.build_id,build_version:prepared.build_version,release_id:release,activation_version:activation};
      }else if(operation==='KNOWLEDGE_REVOKE'||operation==='KNOWLEDGE_DELETE'){
        const activation=String(BigInt(current.activation_version)+1n);
        if(operation==='KNOWLEDGE_REVOKE')knowledge.sources[0]={...knowledge.sources[0],source_version:'3',state:'REVOKED',head:{...knowledge.sources[0].head,confirmed:false}};else knowledge.sources=[];
        knowledge.rollback_targets=knowledge.rollback_targets.map(t=>({...t,eligible:false,reason_code:'ROLLBACK_NOT_ALLOWED'}));
        state={...state,activation_version:activation};current={...current,activation_version:activation};knowledge.activation_version=activation;
        result={source_id:sourceId,source_version:operation==='KNOWLEDGE_REVOKE'?'3':'4',release_id:current.release_id,activation_version:activation};
      }
      return knowledgeCommand(operation,result);
    });
  });
  async function openSources(){
    await ready();fireEvent.click(screen.getByRole('button',{name:'Посмотреть источники'}));await screen.findByLabelText('Текст источника');
  }
  async function saveSource(value='Подтверждённый текст источника.'){
    fireEvent.change(screen.getByLabelText('Заголовок источника'),{target:{value:'Памятка'}});
    fireEvent.change(screen.getByLabelText('Текст источника'),{target:{value}});
    fireEvent.submit(screen.getByRole('button',{name:'Сохранить источник'}).closest('form')!);
    await screen.findByRole('button',{name:'Подтвердить источник'});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Подтвердить источник'})).toBeEnabled());
  }
  it('previews, confirms, builds, publishes and revokes without manual JSON or SQL',async()=>{
    setup();await openSources();await saveSource();
    expect(screen.getByText('Подтверждённый текст источника.',{exact:true})).toBeVisible();
    expect(current.bundle).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Подтвердить источник'}));await waitFor(()=>expect(screen.getByText('Памятка · Подтверждён')).toBeVisible());
    fireEvent.click(screen.getByRole('button',{name:'Подготовить поиск'}));await screen.findByText('Поиск готов к публикации · фрагментов 1');
    fireEvent.click(screen.getByRole('button',{name:'Опубликовать источники'}));await screen.findByText('Опубликованный поиск подключён к текущим настройкам.');
    const publish=vi.mocked(knowledgeApi.command).mock.calls.find(c=>c[2]==='KNOWLEDGE_PUBLISH');
    expect(publish?.[3]).toEqual({schema_version:1,expected_draft_version:'1',expected_activation_version:'0',build_id:buildId,expected_build_version:'3'});
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'Отозвать источник'}));await screen.findByText('Памятка · Отозван');
    expect(vi.mocked(knowledgeApi.command).mock.calls.at(-1)?.slice(2,4)).toEqual(['KNOWLEDGE_REVOKE',{schema_version:1,expected_source_version:'2',expected_activation_version:'1'}]);
    expect(screen.getByRole('button',{name:'Опубликовать источники'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'Удалить источник'}));expect(screen.getByText('Текст и его индекс будут удалены без восстановления через старую публикацию.')).toBeVisible();
    fireEvent.click(screen.getByRole('button',{name:'Удалить текст и индекс'}));await screen.findByText('Сохранённых источников ещё нет.');
    expect(screen.queryByLabelText(/JSON/)).toBeNull();
  });
  it('keeps uncertain source intent exact across session recheck and blocks other writes',async()=>{
    vi.mocked(knowledgeApi.command).mockRejectedValueOnce(new TypeError('lost ACK'));
    const v=setup();await openSources();
    fireEvent.change(screen.getByLabelText('Заголовок источника'),{target:{value:'Памятка'}});
    fireEvent.change(screen.getByLabelText('Текст источника'),{target:{value:'Private synthetic source'}});
    const form=screen.getByRole('button',{name:'Сохранить источник'}).closest('form')!;
    fireEvent.submit(form);fireEvent.submit(form);await screen.findByRole('button',{name:'Повторить исходную команду'});
    expect(knowledgeApi.command).toHaveBeenCalledTimes(1);expect(screen.getByLabelText('Ответ FAQ 1')).toBeDisabled();
    const original=vi.mocked(knowledgeApi.command).mock.calls[0];
    v.rerender(<ConfigurationPanel {...v.props} session={session('fresh-csrf')}/>);
    await screen.findByRole('button',{name:'Повторить исходную команду'});
    fireEvent.click(screen.getByRole('button',{name:'Повторить исходную команду'}));await screen.findByText('Команда подтверждена. Текущее состояние получено.');
    const retry=vi.mocked(knowledgeApi.command).mock.calls[1];expect(retry.slice(0,5)).toEqual(original.slice(0,5));expect(retry[5]).toBe('fresh-csrf');
  });
  it('does not resend an acknowledged build when its fresh state read failed',async()=>{
    knowledge.sources=[{...knowledgeSource(),source_version:'2',state:'CONFIRMED',head:{...knowledgeSource().head,confirmed:true}}];
    setup();await openSources();
    vi.mocked(knowledgeApi.state).mockRejectedValueOnce(new ConfigurationError(503,'UNAVAILABLE'));
    fireEvent.click(screen.getByRole('button',{name:'Подготовить поиск'}));await screen.findByRole('button',{name:'Повторить чтение настроек'});
    expect(knowledgeApi.command).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Повторить чтение настроек'}));await screen.findByText('Поиск готов к публикации · фрагментов 1');expect(knowledgeApi.command).toHaveBeenCalledTimes(1);
  });
  it('renders Markdown as text and disables confirmation for a complete-plan error',async()=>{
    const payload='<img src=x onerror=alert(1)>';
    knowledge.sources=[{...knowledgeSource(payload),head:{...knowledgeSource(payload).head,format:'MARKDOWN'},preview:{chunks:[],issues:['CHUNK_LIMIT']}}];
    setup();await openSources();
    expect(screen.getByText(payload,{exact:true})).toBeVisible();expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('button',{name:'Подтвердить источник'})).toBeDisabled();
    expect(screen.getByText(/Текст не помещается в четыре фрагмента/)).toBeVisible();
  });
  it('shows failed and unknown build state while keeping publish disabled',async()=>{
    knowledge.sources=[{...knowledgeSource(),source_version:'2',state:'CONFIRMED',head:{...knowledgeSource().head,confirmed:true}}];
    knowledge.embedding_mode='DISABLED';knowledge.builds=[{...readyBuild(),state:'ERROR',error_code:'EMBEDDING_ERROR'}];
    setup();await openSources();expect(screen.getByText(/Ошибка индексации.*Индексация отключена/)).toBeVisible();expect(screen.getByRole('button',{name:'Опубликовать источники'})).toBeDisabled();
    knowledge.builds=[{...readyBuild(),state:'UNKNOWN',error_code:'EMBEDDING_UNKNOWN'}];
    fireEvent.click(screen.getByRole('button',{name:'Посмотреть источники'}));await screen.findByText(/Результат индексации неизвестен/);expect(knowledgeApi.command).not.toHaveBeenCalled();
  });
  it('hides a late source read after Business change and logout',async()=>{
    const delayed=deferred<KnowledgeState>();const v=setup();await ready();
    vi.mocked(knowledgeApi.state).mockImplementationOnce(()=>delayed.promise);fireEvent.click(screen.getByRole('button',{name:'Посмотреть источники'}));
    v.rerender(<ConfigurationPanel {...v.props} business={business('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')}/>);
    v.rerender(<ConfigurationPanel {...v.props} session={null} business={null}/>);
    await act(async()=>delayed.resolve({...knowledgeState(),sources:[knowledgeSource('PRIVATE_SOURCE_OTHER_SCOPE')]}));
    expect(screen.queryByText('PRIVATE_SOURCE_OTHER_SCOPE')).toBeNull();expect(screen.queryByRole('region',{name:'Настройки бизнеса'})).toBeNull();
  });
  function publishedSource(){
    current=active(bundle(),'1',releaseId);state=draft(bundle(),'1','1',releaseId);
    knowledge.sources=[{...knowledgeSource(),source_version:'2',state:'CONFIRMED',head:{...knowledgeSource().head,confirmed:true}}];
    knowledge.builds=[readyBuild()];knowledge.active_build_id=buildId;
    knowledge.rollback_targets=[{release_id:releaseId,build_id:buildId,eligible:true,reason_code:null}];
  }
  it('retains a published build after remount with sources closed and joint-publishes changed settings',async()=>{
    publishedSource();const first=setup();await openSources();first.unmount();
    setup();await ready();expect(screen.queryByRole('textbox',{name:'Текст источника'})).toBeNull();
    expect(knowledgeApi.state).toHaveBeenCalledTimes(3);
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
    await editFAQ('Settings after reload');
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
    expect(screen.queryByRole('textbox',{name:'Текст источника'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Выбрать набор для публикации'}));await screen.findByLabelText('Готовый набор источников');
    expect(screen.getByLabelText('Готовый набор источников')).toHaveValue(buildId);
    fireEvent.click(screen.getByRole('button',{name:'Опубликовать источники'}));
    await waitFor(()=>expect(current.bundle?.faqs[0].answer).toBe('Settings after reload'));
    expect(current.release_id).not.toBe(releaseId);expect(knowledge.active_build_id).toBe(buildId);
    expect(vi.mocked(configurationApi.command).mock.calls.map(c=>c[2])).toEqual(['EDIT']);
    expect(vi.mocked(knowledgeApi.command).mock.calls.map(c=>c[2])).toEqual(['KNOWLEDGE_PUBLISH']);
    expect(vi.mocked(knowledgeApi.command).mock.calls[0][3]).toEqual({schema_version:1,expected_draft_version:'2',expected_activation_version:'1',build_id:buildId,expected_build_version:'3'});
  });
  it.each(['KNOWLEDGE_REVOKE','KNOWLEDGE_DELETE'] as const)('explicitly publishes changed settings without sources after last-source %s',async operation=>{
    publishedSource();setup();await openSources();
    fireEvent.click(screen.getByRole('button',{name:operation==='KNOWLEDGE_REVOKE'?'Отозвать источник':'Удалить источник'}));
    if(operation==='KNOWLEDGE_DELETE')fireEvent.click(screen.getByRole('button',{name:'Удалить текст и индекс'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Подготовить пустой набор'})).toBeEnabled());
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Опубликовать источники'})).toBeDisabled();
    await editFAQ('Settings after '+operation);
    fireEvent.click(screen.getByRole('button',{name:'Подготовить пустой набор'}));
    await screen.findByText('Пустой набор готов к публикации · фрагментов 0');
    expect(screen.getByLabelText('Готовый набор источников')).toHaveValue(emptyBuildId);
    expect(knowledge.active_build_id).toBe(buildId);
    expect(vi.mocked(knowledgeApi.command).mock.calls.find(c=>c[2]==='KNOWLEDGE_BUILD_CREATE')?.[3]).toEqual({schema_version:1,expected_sources_hash:knowledge.sources_hash,revision_ids:[]});
    expect(knowledge.builds.find(b=>b.build_id===emptyBuildId)).toMatchObject({state:'READY',calls_reserved:0,calls_completed:0,chunk_count:0,revision_ids:[]});
    fireEvent.click(screen.getByRole('button',{name:'Опубликовать настройки без источников'}));
    await screen.findByText('Настройки опубликованы без источников для поиска.');
    expect(knowledge.active_build_id).toBe(emptyBuildId);expect(current.bundle?.faqs[0].answer).toBe('Settings after '+operation);
    expect(vi.mocked(knowledgeApi.command).mock.calls.map(c=>c[2])).toEqual([operation,'KNOWLEDGE_BUILD_CREATE','KNOWLEDGE_PUBLISH']);
    expect(vi.mocked(knowledgeApi.command).mock.calls.at(-1)?.[3]).toMatchObject({build_id:emptyBuildId,expected_build_version:'1'});
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
  });
  it('does not allow publication until the required knowledge state has been read',async()=>{
    publishedSource();vi.mocked(knowledgeApi.state).mockRejectedValueOnce(new ConfigurationError(503,'UNAVAILABLE'));
    setup();await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'Опубликовать черновик'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Обновить настройки'}));await ready();
    expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();expect(configurationApi.command).not.toHaveBeenCalled();
  });
  it('shows the definite server publication refusal without an uncertain POST retry',async()=>{
    setup();await ready();vi.mocked(configurationApi.command).mockRejectedValueOnce(new ConfigurationError(409,'KNOWLEDGE_BUILD_REQUIRED'));
    fireEvent.click(screen.getByRole('button',{name:'Опубликовать черновик'}));
    await screen.findByText('К настройкам подключён набор источников. Выберите его и опубликуйте настройки совместно с ним.');
    expect(screen.queryByRole('button',{name:'Повторить исходную команду'})).toBeNull();
    expect(configurationApi.command).toHaveBeenCalledTimes(1);expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();
  });

});

describe('composite settings and portfolio publication',()=>{
  beforeEach(()=>{vi.spyOn(knowledgeApi,'command');});
  it.each([false,true])('preserves knowledge and portfolio links after settings edit/reload (EMPTY=%s)',async empty=>{
    current=active(bundle(),'1',releaseId);state=draft(bundle(),'1','1',releaseId);
    const kb={...knowledgeState(),active_build_id:buildId,builds:[emptyReadyBuild(),readyBuild()],rollback_targets:[{release_id:releaseId,build_id:buildId,eligible:true,reason_code:null} as const]};
    kb.builds=kb.builds.filter(b=>b.build_id===buildId); // the linked KB has its actual READY version3
    const port={...ownerState(),assets:empty?[]:[photo()],items:empty?[]:[confirmedItem()],builds:[portfolioBuild(empty)],active_portfolio_build_id:portfolioBuildId,active_knowledge_build_id:buildId};
    vi.mocked(knowledgeApi.state).mockImplementation(async()=>({...kb,activation_version:current.activation_version,release_id:current.release_id}));
    vi.mocked(portfolioApi.state).mockImplementation(async()=>({...port,draft_version:state.draft_version,activation_version:current.activation_version,active_release_id:current.release_id}));
    vi.spyOn(portfolioApi,'command').mockImplementation(async(_w,_b,op)=>{const activation=String(BigInt(current.activation_version)+1n);state={...state,activation_version:activation};current={...current,activation_version:activation,bundle:structuredClone(state.bundle)};return portfolioCommand(op,{release_id:current.release_id,activation_version:activation});});
    const v=setup();await editFAQ('Новые сведения с сохранением материалов.');
    actionPortfolio();await waitFor(()=>expect(portfolioApi.command).toHaveBeenCalledTimes(1));await waitFor(()=>expect(screen.getByRole('button',{name:'Опубликовать настройки и портфолио'})).toBeEnabled());
    const body=vi.mocked(portfolioApi.command).mock.calls[0][3];expect(body).toEqual({schema_version:1,expected_draft_version:'2',expected_activation_version:'1',knowledge_build_id:buildId,expected_knowledge_build_version:'3',portfolio_build_id:portfolioBuildId,expected_portfolio_build_version:empty?'1':'3'});
    expect(vi.mocked(configurationApi.command).mock.calls.map(c=>c[2])).toEqual(['EDIT']);expect(knowledgeApi.command).not.toHaveBeenCalled();
    v.unmount();setup();await ready();expect(screen.getByRole('button',{name:'Опубликовать черновик'})).toBeDisabled();expect(screen.getByLabelText('Готовый набор работ')).toHaveValue(portfolioBuildId);expect(screen.getByLabelText('Набор источников для совместной публикации')).toHaveValue(buildId);
  });
  it('publishes selected knowledge through composite API when an EMPTY portfolio is linked',async()=>{
    current=active(bundle(),'1',releaseId);state=draft(bundle(),'1','1',releaseId);
    const kb={...knowledgeState(),active_build_id:emptyBuildId,builds:[emptyReadyBuild()],rollback_targets:[{release_id:releaseId,build_id:emptyBuildId,eligible:true,reason_code:null} as const]};
    vi.mocked(knowledgeApi.state).mockImplementation(async()=>({...kb,activation_version:current.activation_version,release_id:current.release_id}));
    vi.mocked(portfolioApi.state).mockImplementation(async()=>({...ownerState(),builds:[portfolioBuild(true)],active_portfolio_build_id:portfolioBuildId,active_knowledge_build_id:emptyBuildId,draft_version:state.draft_version,activation_version:current.activation_version,active_release_id:current.release_id}));
    vi.spyOn(portfolioApi,'command').mockImplementation(async(_w,_b,op)=>portfolioCommand(op));setup();await ready();fireEvent.click(screen.getByRole('button',{name:'Посмотреть источники'}));await screen.findByLabelText('Текст источника');fireEvent.click(screen.getByRole('button',{name:'Опубликовать настройки без источников'}));await waitFor(()=>expect(portfolioApi.command).toHaveBeenCalledTimes(1));expect(vi.mocked(portfolioApi.command).mock.calls[0][3]).toMatchObject({knowledge_build_id:emptyBuildId,expected_knowledge_build_version:'1',portfolio_build_id:portfolioBuildId,expected_portfolio_build_version:'1'});expect(knowledgeApi.command).not.toHaveBeenCalled();
  });
  function actionPortfolio(){fireEvent.click(screen.getByRole('button',{name:'Опубликовать настройки и портфолио'}));}
});
