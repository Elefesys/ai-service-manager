import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigurationPanel } from './ConfigurationPanel';
import { App } from './App';
import { api } from './api';
vi.mock('./BillingPanel',()=>({BillingPanel:()=>null}));
vi.mock('./MessagingPanel',()=>({MessagingPanel:()=>null}));
vi.mock('./EscalationsPanel',()=>({EscalationsPanel:()=>null}));
import { ActiveProjection, Bundle, ConfigurationError, DraftState, configurationApi, KnowledgeState, KnowledgeCommand, knowledgeApi, normalizeSource } from './configuration-api';
import { active, bundle, business, businessId, command, deferred, draft, preview, releaseId, session, workspace, knowledgeSource, knowledgeState, knowledgeCommand, readyBuild, sourceId, revisionId, buildId } from './configuration-fixtures.test-helper';
let state:DraftState,current:ActiveProjection;
beforeEach(()=>{state=draft();current=active();vi.spyOn(configurationApi,'draft').mockImplementation(async()=>structuredClone(state));vi.spyOn(configurationApi,'active').mockImplementation(async()=>structuredClone(current));vi.spyOn(configurationApi,'preview').mockImplementation(async()=>preview(structuredClone(state)));vi.spyOn(configurationApi,'command').mockImplementation(async(_w,_b,op,body)=>{
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
    vi.spyOn(knowledgeApi,'state').mockImplementation(async(w,b)=>structuredClone({...knowledge,workspace_id:w,business_id:b,activation_version:current.activation_version,release_id:current.release_id}));
    vi.spyOn(knowledgeApi,'command').mockImplementation(async(_w,_b,operation,body)=>{
      let result:Partial<KnowledgeCommand['result']>={};
      if(operation==='KNOWLEDGE_SAVE'&&'text'in body){
        const value=normalizeSource(body.text),source=knowledgeSource(value);
        source.head={...source.head,title:body.title,format:body.format,source_label:body.source_label,author_label:body.author_label,service_id:body.service_id,category:body.category,claim_key:body.claim_key,effective_from:body.effective_from,effective_until:body.effective_until};
        knowledge.sources=[source];result={source_id:sourceId,source_version:'1',revision_id:revisionId};
      }else if(operation==='KNOWLEDGE_CONFIRM'){
        knowledge.sources[0]={...knowledge.sources[0],source_version:'2',state:'CONFIRMED',head:{...knowledge.sources[0].head,confirmed:true}};result={source_id:sourceId,source_version:'2',revision_id:revisionId};
      }else if(operation==='KNOWLEDGE_BUILD_CREATE'){
        knowledge.builds=[readyBuild()];result={build_id:buildId,build_version:'1'}; // creation ACK deliberately differs from fresh READY version3
      }else if(operation==='KNOWLEDGE_PUBLISH'){
        knowledge.active_build_id=buildId;knowledge.release_id=releaseId;knowledge.activation_version='1';
        state={...state,activation_version:'1',release_id:releaseId};current=active(structuredClone(state.bundle!),'1',releaseId);
        result={build_id:buildId,build_version:'3',release_id:releaseId,activation_version:'1'};
      }else if(operation==='KNOWLEDGE_REVOKE'||operation==='KNOWLEDGE_DELETE'){
        const activation=String(BigInt(current.activation_version)+1n);
        if(operation==='KNOWLEDGE_REVOKE')knowledge.sources[0]={...knowledge.sources[0],source_version:'3',state:'REVOKED'};else knowledge.sources=[];
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
    const delayed=deferred<KnowledgeState>();vi.mocked(knowledgeApi.state).mockImplementationOnce(()=>delayed.promise);
    const v=setup();await ready();fireEvent.click(screen.getByRole('button',{name:'Посмотреть источники'}));
    v.rerender(<ConfigurationPanel {...v.props} business={business('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')}/>);
    v.rerender(<ConfigurationPanel {...v.props} session={null} business={null}/>);
    await act(async()=>delayed.resolve({...knowledgeState(),sources:[knowledgeSource('PRIVATE_SOURCE_OTHER_SCOPE')]}));
    expect(screen.queryByText('PRIVATE_SOURCE_OTHER_SCOPE')).toBeNull();expect(screen.queryByRole('region',{name:'Настройки бизнеса'})).toBeNull();
  });
});
