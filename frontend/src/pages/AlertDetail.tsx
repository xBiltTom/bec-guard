import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError, message } from '../api';
import { useAuth } from '../auth';
import { AnalysisHeadline, AnalysisView, EmailContent } from '../analysis';
import {
  Badge,
  Dialog,
  ErrorState,
  LoadingState,
  PageHeader,
  date,
  label,
} from '../components';
import type { AlertDetail as AlertData, EmailDetail, Verdict } from '../types';
import { useResource } from '../useResource';
export function AlertDetail() {
  const { alertId } = useParams();
  const resource = useResource<AlertData>(`/alerts/${alertId}`);
  const [notice, setNotice] = useState('');
  const alert = resource.data;
  const email = useResource<EmailDetail>(
    alert ? `/emails/${alert.analysis.email_id}` : null,
  );
  return (
    <>
      <Link className="back-link" to="/alerts">
        Volver a alertas
      </Link>
      <PageHeader
        title="Detalle de alerta"
        description="Evidencia del sistema y revisión humana."
      />
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : (
        alert && (
          <>
            <section className="alert-overview">
              <div>
                <AnalysisHeadline analysis={alert.analysis} />
                {email.data && (
                  <div className="overview-identity">
                    <h2>{email.data.subject || '(Sin asunto)'}</h2>
                    <p>
                      {email.data.sender_name} &lt;{email.data.sender_email}&gt;
                    </p>
                    <small>Recibido {date(email.data.received_at)}</small>
                  </div>
                )}
              </div>
              <div className="overview-status">
                <Badge value={alert.status} />
                {alert.verdict && <Badge value={alert.verdict} />}
                <small>Creada {date(alert.created_at)}</small>
              </div>
            </section>
            <div className="detail-grid">
              <div>
                <AnalysisView analysis={alert.analysis} />
                {email.loading ? (
                  <LoadingState />
                ) : email.error ? (
                  <ErrorState error={email.error} retry={email.reload} />
                ) : (
                  email.data && <EmailContent email={email.data} />
                )}
              </div>
              <ReviewPanel
                alert={alert}
                onUpdate={resource.reload}
                notify={setNotice}
              />
            </div>
          </>
        )
      )}
    </>
  );
}
function ReviewPanel({
  alert,
  onUpdate,
  notify,
}: {
  alert: AlertData;
  onUpdate: () => void;
  notify: (text: string) => void;
}) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const own = alert.assigned_to === user?.id;
  const allowed = user?.role !== 'AUDITOR';
  const supervisor = user?.role === 'ADMIN' || user?.role === 'MANAGER';
  async function mutate(action: string, body?: unknown) {
    setBusy(true);
    setError('');
    try {
      await api<AlertData>(`/alerts/${alert.id}/${action}`, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      });
      setVerdict(null);
      notify(
        action === 'claim'
          ? 'Revisión asignada a ti.'
          : action === 'release'
            ? 'Alerta liberada.'
            : 'Decisión guardada. Alerta cerrada.',
      );
      onUpdate();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setVerdict(null);
        notify('La alerta cambió durante la revisión. Se actualizó su estado.');
        onUpdate();
      } else setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function resolve(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const resolution = String(
      new FormData(e.currentTarget).get('resolution') || '',
    ).trim();
    if (resolution) void mutate('resolve', { verdict, resolution });
  }
  return (
    <aside className="panel review-panel">
      <h2>Revisión humana</h2>
      {alert.status === 'CLOSED' ? (
        <>
          <Badge value={alert.verdict} />
          <dl className="facts">
            <div>
              <dt>Responsable</dt>
              <dd>{alert.assigned_to_name || alert.assigned_to}</dd>
            </div>
            <div>
              <dt>Cerrada</dt>
              <dd>{date(alert.closed_at)}</dd>
            </div>
          </dl>
          <h3>Resolución</h3>
          <p className="resolution">{alert.resolution}</p>
          <p className="muted">Decisión final registrada en auditoría.</p>
        </>
      ) : (
        <>
          <p>
            {alert.status === 'OPEN'
              ? 'Esta alerta está disponible para revisión.'
              : own
                ? 'En revisión por ti'
                : `En revisión por ${alert.assigned_to_name || alert.assigned_to}`}
          </p>
          {!allowed && (
            <p className="muted">
              Tu rol permite consultar la evidencia y la decisión.
            </p>
          )}
          {allowed && alert.status === 'OPEN' && (
            <button disabled={busy} onClick={() => void mutate('claim')}>
              Tomar revisión
            </button>
          )}
          {allowed &&
            alert.status === 'UNDER_REVIEW' &&
            (own || supervisor) && (
              <div className="review-actions">
                <button
                  disabled={busy}
                  onClick={() => setVerdict('CONFIRMED_BEC')}
                >
                  Confirmar BEC
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => setVerdict('FALSE_POSITIVE')}
                >
                  Marcar falso positivo
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void mutate('release')}
                >
                  Liberar revisión
                </button>
              </div>
            )}
          {allowed &&
            alert.status === 'UNDER_REVIEW' &&
            !own &&
            !supervisor && (
              <p className="muted">
                Solo la persona asignada o un supervisor puede resolverla.
              </p>
            )}
        </>
      )}
      {error && !verdict && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {busy && <p role="status">Guardando…</p>}
      {verdict && (
        <Dialog
          title={label(verdict)}
          busy={busy}
          onClose={() => setVerdict(null)}
        >
          <p>
            Esta decisión cerrará la alerta. Explica la evidencia que sustenta
            tu conclusión.
          </p>
          <form onSubmit={resolve}>
            <label htmlFor="resolution">Resolución</label>
            <textarea
              id="resolution"
              name="resolution"
              required
              minLength={1}
              maxLength={2000}
              rows={5}
            />
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="actions">
              <button type="submit" disabled={busy}>
                {busy ? 'Guardando…' : 'Confirmar decisión'}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setVerdict(null)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </aside>
  );
}
