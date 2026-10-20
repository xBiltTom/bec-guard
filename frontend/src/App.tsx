import { useEffect, useState } from 'react';

type ConnectionStatus = 'checking' | 'connected' | 'unavailable';

const messages: Record<ConnectionStatus, string> = {
  checking: 'Comprobando conexión…',
  connected: 'Backend conectado ✓',
  unavailable: 'Backend no disponible',
};

export function App() {
  const [status, setStatus] = useState<ConnectionStatus>('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    let active = true;

    async function checkHealth() {
      try {
        const response = await fetch('/health', {
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!response.ok) throw new Error('Health check failed');
        const body: unknown = await response.json();
        if (
          typeof body !== 'object' ||
          body === null ||
          !('status' in body) ||
          body.status !== 'ok' ||
          !('service' in body) ||
          body.service !== 'bec-guard-api'
        )
          throw new Error('Unexpected health response');
        if (active) setStatus('connected');
      } catch {
        if (active) setStatus('unavailable');
      } finally {
        window.clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  function retry() {
    setStatus('checking');
    setAttempt((current) => current + 1);
  }

  return (
    <main className="card">
      <p className="eyebrow">Ingeniería de Software · Fases 0 y 1</p>
      <h1>BEC Guard</h1>
      <p className="description">Detección y gestión de fraude ejecutivo.</p>
      <p className={`connection ${status}`} role="status" aria-live="polite">
        {messages[status]}
      </p>
      <button type="button" onClick={retry} disabled={status === 'checking'}>
        Comprobar conexión
      </button>
    </main>
  );
}
