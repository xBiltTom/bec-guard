import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  date,
  label,
} from '../components';
import type { AuditEvent } from '../types';
import { useResource } from '../useResource';
export function Audit() {
  const { user } = useAuth();
  return user?.role === 'ADMIN' || user?.role === 'AUDITOR' ? (
    <AuditList />
  ) : (
    <ErrorState error="No tienes permisos para consultar la auditoría." />
  );
}
function AuditList() {
  const [params, setParams] = useSearchParams();
  const [action, setAction] = useState(params.get('action') || '');
  const [resourceType, setResourceType] = useState(
    params.get('resource_type') || '',
  );
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const query = new URLSearchParams(params);
  query.set('limit', '25');
  query.set('offset', String(offset));
  const resource = useResource<AuditEvent[]>(`/audit?${query}`);
  function filter(e: FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams();
    if (action.trim()) next.set('action', action.trim());
    if (resourceType.trim()) next.set('resource_type', resourceType.trim());
    setParams(next);
  }
  return (
    <>
      <PageHeader
        title="Auditoría"
        description="Trazabilidad de acciones humanas y automatizadas. Solo lectura."
      />
      <form className="filters audit-filters" onSubmit={filter}>
        <label>
          Acción
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            maxLength={64}
            placeholder="BEC_ALERT_CONFIRMED"
          />
        </label>
        <label>
          Recurso
          <input
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            maxLength={64}
            placeholder="bec_alert"
          />
        </label>
        <button type="submit">Aplicar filtros</button>
      </form>
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>No hay eventos con estos filtros.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Acción</th>
                <th>Actor</th>
                <th>Rol</th>
                <th>Recurso</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((e) => (
                <tr key={e.id}>
                  <td>{date(e.created_at)}</td>
                  <td>
                    <strong>{e.action}</strong>
                    {e.details && Object.keys(e.details).length > 0 && (
                      <details>
                        <summary>Metadata</summary>
                        <dl className="facts">
                          {Object.entries(e.details).map(([key, value]) => (
                            <div key={key}>
                              <dt>{key}</dt>
                              <dd>{value}</dd>
                            </div>
                          ))}
                        </dl>
                      </details>
                    )}
                  </td>
                  <td>
                    {e.actor_name || e.actor_user_id || 'Sin actor humano'}
                  </td>
                  <td>{label(e.actor_role)}</td>
                  <td>
                    {e.resource_type || '—'}
                    <small>{e.resource_id}</small>
                  </td>
                  <td>{e.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        offset={offset}
        count={resource.data?.length || 0}
        onChange={(n) => {
          const next = new URLSearchParams(params);
          next.set('offset', String(n));
          setParams(next);
        }}
      />
    </>
  );
}
