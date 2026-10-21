import { Link } from 'react-router-dom';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  date,
  label,
} from '../components';
import type { AlertSummary, Dashboard as DashboardData } from '../types';
import { useResource } from '../useResource';
export function Dashboard() {
  const resource = useResource<DashboardData>('/dashboard/summary');
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Estado operativo de la revisión de fraude empresarial."
      />
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : (
        resource.data && <DashboardContent data={resource.data} />
      )}
    </>
  );
}
function DashboardContent({ data }: { data: DashboardData }) {
  const recent = useResource<AlertSummary[]>('/alerts?limit=5');
  const risks = Object.entries(data.risk_distribution);
  const maxRisk = Math.max(1, ...risks.map(([, n]) => n));
  const maxTypes = Math.max(
    1,
    ...data.bec_type_distribution.map((t) => t.count),
  );
  const maxDays = Math.max(1, ...data.alerts_last_7_days.map((t) => t.count));
  return (
    <>
      <section className="workload">
        <div>
          <span>Alertas pendientes</span>
          <strong>{data.alerts.open + data.alerts.under_review}</strong>
          <Link to="/alerts?status=OPEN">Abrir cola de revisión</Link>
        </div>
        <dl>
          <div>
            <dt>Abiertas</dt>
            <dd>{data.alerts.open}</dd>
          </div>
          <div>
            <dt>En revisión</dt>
            <dd>{data.alerts.under_review}</dd>
          </div>
          <div>
            <dt>Cerradas</dt>
            <dd>{data.alerts.closed}</dd>
          </div>
        </dl>
      </section>
      <dl className="metric-strip">
        <div>
          <dt>Correos recibidos</dt>
          <dd>{data.emails_total}</dd>
        </div>
        <div>
          <dt>Análisis completados</dt>
          <dd>{data.analyses_completed}</dd>
        </div>
        <div>
          <dt>Errores de análisis</dt>
          <dd className={data.analyses_error ? 'error' : ''}>
            {data.analyses_error}
          </dd>
        </div>
        <div>
          <dt>BEC confirmados</dt>
          <dd>{data.verdicts.confirmed_bec}</dd>
        </div>
        <div>
          <dt>Falsos positivos</dt>
          <dd>{data.verdicts.false_positive}</dd>
        </div>
      </dl>
      <div className="dashboard-grid">
        <section className="panel">
          <h2>Distribución de riesgo</h2>
          <p className="muted">Solo análisis completados</p>
          <ul className="bar-list">
            {risks.map(([risk, count]) => (
              <li key={risk}>
                <div>
                  <Badge value={risk} />
                  <strong>{count}</strong>
                </div>
                <div className="bar-track">
                  <span
                    className={`bar-${risk.toLowerCase()}`}
                    style={{ width: `${(count / maxRisk) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <h2>Patrones identificados</h2>
          {!data.bec_type_distribution.length ? (
            <EmptyState>Aún no hay tipos BEC identificados.</EmptyState>
          ) : (
            <ul className="bar-list">
              {data.bec_type_distribution.map((t) => (
                <li key={t.bec_type}>
                  <div>
                    <span>{label(t.bec_type)}</span>
                    <strong>{t.count}</strong>
                  </div>
                  <div className="bar-track">
                    <span style={{ width: `${(t.count / maxTypes) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel activity-panel">
          <h2>Alertas de los últimos 7 días</h2>
          <div className="activity">
            {data.alerts_last_7_days.map((d) => (
              <div key={d.date}>
                <strong>{d.count}</strong>
                <div className="activity-track">
                  <span style={{ height: `${(d.count / maxDays) * 100}%` }} />
                </div>
                <span>
                  {new Date(`${d.date}T12:00:00Z`).toLocaleDateString('es-PE', {
                    month: 'short',
                    day: 'numeric',
                    timeZone: 'UTC',
                  })}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Alertas recientes</h2>
          <Link to="/alerts">Ver todas las alertas</Link>
        </div>
        {recent.loading ? (
          <LoadingState />
        ) : recent.error ? (
          <ErrorState error={recent.error} retry={recent.reload} />
        ) : !recent.data?.length ? (
          <EmptyState>No se han generado alertas.</EmptyState>
        ) : (
          <ul className="recent-alerts">
            {recent.data.map((a) => (
              <li key={a.id}>
                <Badge value={a.risk_level} />
                <div>
                  <Link to={`/alerts/${a.id}`}>
                    {a.subject || '(Sin asunto)'}
                  </Link>
                  <small>{a.sender_name || a.sender_email}</small>
                </div>
                <Badge value={a.status} />
                <small>{date(a.created_at)}</small>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
