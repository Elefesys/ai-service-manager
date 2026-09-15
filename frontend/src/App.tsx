import { useEffect, useState } from 'react';

type Readiness = 'checking' | 'ok' | 'unavailable';

export function App({ pathname = window.location.pathname }: { pathname?: string }) {
  const [readiness, setReadiness] = useState<Readiness>('checking');
  useEffect(() => {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 5000);
    let active = true;
    async function check() {
      try {
        const response = await fetch('/health/ready', { signal: abort.signal });
        const body: unknown = await response.json();
        const valid = response.ok && typeof body === 'object' && body !== null
          && 'status' in body && body.status === 'ok'
          && 'component' in body && body.component === 'database';
        if (active) setReadiness(valid ? 'ok' : 'unavailable');
      } catch {
        if (active) setReadiness('unavailable');
      } finally { clearTimeout(timeout); }
    }
    void check();
    return () => { active = false; clearTimeout(timeout); abort.abort(); };
  }, []);
  const ops = pathname.startsWith('/ops');
  return <main>
    <header><span className="eyebrow">AI SERVICE MANAGER · M0</span><h1>{ops ? 'Platform Operations' : 'Business Console'}</h1></header>
    <nav aria-label="Разделы"><a href="/">Business Console</a><a href="/ops/">Platform Operations</a></nav>
    <section className="notice"><h2>Инженерный каркас</h2><p>Вход и рабочие данные появятся в M1. Это локальная среда, не production и не готовая CRM.</p></section>
    <section><h2>Связь с backend и PostgreSQL</h2><p role="status">{readiness === 'checking' ? 'Проверка…' : readiness === 'ok' ? 'Проверка готовности пройдена' : 'Сервис недоступен или не готов'}</p></section>
    <section><h2>{ops ? 'Граница операторского доступа' : 'Следующий этап'}</h2><p>{ops ? 'Пока здесь только техническая проверка. Данные Workspace и операторские действия не подключены. Отдельная авторизация обязательна до их появления.' : 'Пользователи, Workspace, серверная авторизация и проверяемая изоляция данных.'}</p></section>
    <footer>Без реальных данных мастеров, AI-вызовов и платежей.</footer>
  </main>;
}
