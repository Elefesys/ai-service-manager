import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,waitFor,cleanup} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {DurationCasesPanel} from './DurationCasesPanel';
import {intakeApi} from './intake-api';
import {example,scope,session,w,b,message} from './intake-fixtures.test-helper';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('creates an owner example with explicit unknowns and renders only a durable read',async()=>{
 let items:ReturnType<typeof example>[]=[];vi.spyOn(intakeApi,'cases').mockImplementation(async()=>({workspace_id:w,business_id:b,items}));const command=vi.spyOn(intakeApi,'command').mockImplementation(async()=>{items=[example()];return {outcome:'ACCEPTED',receipt_id:message,version:'1'};});
 render(<DurationCasesPanel session={session()} scope={scope} expired={vi.fn()}/>);expect(intakeApi.cases).not.toHaveBeenCalled();await userEvent.click(screen.getByRole('button',{name:'Открыть примеры длительности'}));const input=await screen.findByLabelText('Описание работы');await userEvent.type(input,'Private owner flower');await userEvent.click(screen.getByRole('button',{name:'Создать пример'}));await screen.findByRole('heading',{name:'Private owner flower'});
 expect(command).toHaveBeenCalledTimes(1);expect(command.mock.calls[0][1]).toBe('case-create');expect(command.mock.calls[0][2]).toMatchObject({expected_version:'0',case_id:null,data:{description:'Private owner flower',working_minutes:null,occupied_minutes:null,asset:null}});
});
it('clears owner times, notes and edit form when the principal changes',async()=>{
 vi.spyOn(intakeApi,'cases').mockResolvedValue({workspace_id:w,business_id:b,items:[example({working_minutes:35,explanation:'Private owner note'})]});const owner=session(),view=render(<DurationCasesPanel session={owner} scope={scope} expired={vi.fn()}/>);await userEvent.click(screen.getByRole('button',{name:'Открыть примеры длительности'}));await screen.findByRole('heading',{name:'Private owner flower'});await userEvent.click(screen.getByRole('button',{name:'Исправить пример'}));expect(screen.getByLabelText('Пояснение')).toHaveValue('Private owner note');
 view.rerender(<DurationCasesPanel session={{...owner,csrf_token:'rechecked'}} scope={scope} expired={vi.fn()}/>);expect(screen.queryByDisplayValue('Private owner note')).not.toBeInTheDocument();expect(screen.queryByRole('heading',{name:'Private owner flower'})).not.toBeInTheDocument();await waitFor(()=>expect(screen.getByRole('button',{name:'Открыть примеры длительности'})).toBeVisible());
});
