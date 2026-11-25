import {useEffect, useRef, useState} from 'react';
import {DraftCard} from './IntakePanel';
import {IntakeError, intakeApi} from './intake-api';
import type {ServiceRequestDraft} from './intake-api';
import {OwnerAppointmentActions} from './OwnerCalendarActions';
import {QuotePanel} from './QuotePanel';
import type {SchedulingScope} from './scheduling-api';

export function OwnerCalendarWork({scope, label, date, version, csrf, refresh, changed, expired, close}: {
  scope: SchedulingScope; label: string; date: string; version: string; csrf: string; refresh: number;
  changed: () => void; expired: () => void; close: () => void;
}) {
  const [draft, setDraft] = useState<ServiceRequestDraft | null>(null);
  const [error, setError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
    const controller = new AbortController();
    const {signal} = controller;
    void intakeApi.draft(scope, scope.request, signal).then(result => {
      if (!signal.aborted) setDraft(result);
    }).catch(cause => {
      if (signal.aborted) return;
      if (cause instanceof IntakeError && cause.status === 401) expired();
      setError('Не удалось открыть эту работу.');
    });
    return () => controller.abort();
  }, [scope, expired]);

  return <section className="calendar-work" aria-label="Работа из календаря">
    <div className="billing-heading">
      <h3 ref={heading} tabIndex={-1}>{label}</h3>
      <button className="secondary" type="button" onClick={close}>Закрыть работу</button>
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {!error && !draft && <p role="status">Открываем работу…</p>}
    {draft && <DraftCard draft={draft} linkedSources={false}>
      <QuotePanel scope={scope} draft={draft} refresh="" approvalChange={null} csrf={csrf} expired={expired}
        calendar={{expected: scope, date, version, refresh, changed, actions: booking =>
          <OwnerAppointmentActions key={date} scope={scope} booking={booking} date={date} csrf={csrf} changed={changed} expired={expired}/>}}/>
    </DraftCard>}
  </section>;
}
