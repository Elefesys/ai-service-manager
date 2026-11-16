import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,waitFor,cleanup} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {IntakePanel} from './IntakePanel';
import {intakeApi,IntakeError} from './intake-api';
import {intake,scope,session,message} from './intake-fixtures.test-helper';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('shows one missing question, a source link and confirms only the selected field',async()=>{
 const value=intake(),owner=session();vi.spyOn(intakeApi,'summary').mockResolvedValue(value);const command=vi.spyOn(intakeApi,'command').mockResolvedValue({outcome:'ACCEPTED',receipt_id:message,version:'2'});
 render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);expect(await screen.findByText(value.question!)).toBeVisible();expect(screen.getByRole('link',{name:'сообщение клиента'})).toHaveAttribute('href',`#message-${message}`);
 await userEvent.click(screen.getByRole('button',{name:'Подтвердить поле Идея'}));await waitFor(()=>expect(command).toHaveBeenCalledTimes(1));const args=command.mock.calls[0];expect(args[1]).toBe('confirm');expect(args[2]).toEqual({expected_version:'1',expected_fingerprint:value.fingerprint,field:'idea',value:'flower',source:value.facts[0].source});
});
it('hides old facts immediately on auth/scope change and rejects a delayed response',async()=>{
 let resolve!:(v:ReturnType<typeof intake>)=>void;vi.spyOn(intakeApi,'summary').mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValue(intake());const owner=session();const view=render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);
 view.rerender(<IntakePanel session={null} scope={null} expired={vi.fn()}/>);resolve(intake());await waitFor(()=>expect(screen.queryByText('flower')).not.toBeInTheDocument());expect(screen.queryByRole('region',{name:'Предварительный запрос'})).not.toBeInTheDocument();
});
it('removes a stale summary after a version conflict',async()=>{
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());vi.spyOn(intakeApi,'command').mockRejectedValue(new IntakeError(409,'STALE_STATE'));render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);await screen.findByText('Со слов клиента');await userEvent.click(screen.getByRole('button',{name:'Подтвердить поле Идея'}));expect(await screen.findByRole('alert')).toHaveTextContent('Сводка изменилась');expect(screen.queryByLabelText('Идея')).not.toBeInTheDocument();
});
it('keeps owner comparisons scoped to the exact visible summary and hides delayed owner data',async()=>{
 const value=intake(),owner=session();vi.spyOn(intakeApi,'summary').mockResolvedValue(value);
 let finish!:(value:Awaited<ReturnType<typeof intakeApi.search>>)=>void;
 const search=vi.spyOn(intakeApi,'search').mockImplementation(()=>new Promise(r=>{finish=r;}));
 const view=render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);await screen.findByText('Со слов клиента');await userEvent.click(screen.getByRole('button',{name:'Сравнить с примерами мастера'}));
 expect(search).toHaveBeenCalledWith(scope,{},expect.any(AbortSignal));
 view.rerender(<IntakePanel session={null} scope={null} expired={vi.fn()}/>);finish({workspace_id:scope.workspace,business_id:scope.business,items:[]});await waitFor(()=>expect(screen.queryByLabelText('Сравнение примеров мастера')).not.toBeInTheDocument());
});
