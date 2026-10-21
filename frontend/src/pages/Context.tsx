import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, message } from '../api';
import { useAuth } from '../auth';
import {
  Dialog,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
} from '../components';
import type { Executive, Vendor } from '../types';
import { useResource } from '../useResource';
type Kind = 'executives' | 'vendors';
type ContextRow = Executive | Vendor;
const fields = {
  executives: [
    ['name', 'Nombre', 'text', true, 200],
    ['position', 'Cargo', 'text', true, 200],
    ['department', 'Departamento', 'text', false, 200],
    ['email', 'Correo legítimo', 'email', true, 320],
  ],
  vendors: [
    ['name', 'Nombre', 'text', true, 200],
    ['domain', 'Dominio legítimo', 'text', true, 253],
    ['contact_email', 'Correo de contacto', 'email', false, 320],
    ['bank_account_reference', 'Referencia bancaria', 'text', false, 256],
  ],
} as const;
export function ContextPage({ kind }: { kind: Kind }) {
  const { user } = useAuth();
  const write = user?.role === 'ADMIN' || user?.role === 'MANAGER';
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const includeInactive = params.get('include_inactive') !== 'false';
  const resource = useResource<ContextRow[]>(
    `/${kind}?limit=25&offset=${offset}&include_inactive=${includeInactive}`,
  );
  const [selected, setSelected] = useState<ContextRow | null | undefined>(
    undefined,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const title = kind === 'executives' ? 'Ejecutivos' : 'Proveedores';
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const body = Object.fromEntries(
      fields[kind].map(([name]) => [
        name,
        String(data.get(name) || '').trim() || null,
      ]),
    );
    setBusy(true);
    setError('');
    try {
      await api(`/${kind}${selected ? `/${selected.id}` : ''}`, {
        method: selected ? 'PATCH' : 'POST',
        body: JSON.stringify(body),
      });
      setSelected(undefined);
      setNotice(selected ? 'Cambios guardados.' : 'Registro creado.');
      resource.reload();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function toggle(row: ContextRow) {
    setBusy(true);
    setNotice('');
    try {
      await api(`/${kind}/${row.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !row.is_active }),
      });
      setNotice(row.is_active ? 'Registro desactivado.' : 'Registro activado.');
      resource.reload();
    } catch (e) {
      setNotice(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title={title}
        description={
          kind === 'executives'
            ? 'Identidades legítimas que aportan contexto al análisis.'
            : 'Dominios y contactos legítimos de proveedores.'
        }
      >
        {write && (
          <button
            onClick={() => {
              setError('');
              setSelected(null);
            }}
          >
            {kind === 'executives' ? 'Añadir ejecutivo' : 'Añadir proveedor'}
          </button>
        )}
      </PageHeader>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <div className="filters">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) =>
              setParams({ include_inactive: String(e.target.checked) })
            }
          />
          Incluir inactivos
        </label>
        {!write && <p className="muted">Acceso de solo lectura</p>}
      </div>
      {resource.loading ? (
        <LoadingState />
      ) : resource.error ? (
        <ErrorState error={resource.error} retry={resource.reload} />
      ) : !resource.data?.length ? (
        <EmptyState>
          {kind === 'executives'
            ? 'No hay ejecutivos registrados.'
            : 'No hay proveedores registrados.'}
        </EmptyState>
      ) : (
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Tabla de contexto organizacional"
        >
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                {kind === 'executives' ? (
                  <>
                    <th>Cargo</th>
                    <th>Departamento</th>
                    <th>Correo legítimo</th>
                  </>
                ) : (
                  <>
                    <th>Dominio legítimo</th>
                    <th>Contacto</th>
                  </>
                )}
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                  </td>
                  {'position' in row ? (
                    <>
                      <td>{row.position}</td>
                      <td>{row.department || '—'}</td>
                      <td>{row.email}</td>
                    </>
                  ) : (
                    <>
                      <td>{row.domain}</td>
                      <td>{row.contact_email || '—'}</td>
                    </>
                  )}
                  <td>
                    <span
                      className={`badge ${row.is_active ? 'badge-low' : ''}`}
                    >
                      {row.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => {
                          setError('');
                          setSelected(row);
                        }}
                        aria-label={`${write ? 'Editar' : 'Ver'} ${row.name}`}
                      >
                        {write ? 'Editar' : 'Ver'}
                      </button>
                      {write && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => void toggle(row)}
                          aria-label={`${row.is_active ? 'Desactivar' : 'Activar'} ${row.name}`}
                        >
                          {row.is_active ? 'Desactivar' : 'Activar'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        offset={offset}
        count={resource.data?.length || 0}
        onChange={(n) =>
          setParams({
            offset: String(n),
            include_inactive: String(includeInactive),
          })
        }
      />
      {selected !== undefined && (
        <Dialog
          title={`${selected ? (write ? 'Editar' : 'Consultar') : 'Añadir'} ${kind === 'executives' ? 'ejecutivo' : 'proveedor'}`}
          busy={busy}
          onClose={() => setSelected(undefined)}
        >
          <form onSubmit={(e) => void save(e)}>
            {fields[kind].map(([name, title, type, required, maxLength]) => (
              <div key={name}>
                <label htmlFor={`context-${name}`}>
                  {title}
                  {!required && <small> (opcional)</small>}
                </label>
                <input
                  id={`context-${name}`}
                  name={name}
                  type={type}
                  required={required}
                  maxLength={maxLength}
                  readOnly={!write}
                  autoComplete="off"
                  defaultValue={
                    selected && name in selected
                      ? String(
                          (selected as unknown as Record<string, unknown>)[
                            name
                          ] || '',
                        )
                      : ''
                  }
                />
              </div>
            ))}
            {kind === 'vendors' && (
              <p className="muted form-hint">
                La referencia bancaria se usa únicamente como contexto
                organizacional.
              </p>
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {write && (
              <div className="actions">
                <button type="submit" disabled={busy}>
                  {busy ? 'Guardando…' : 'Guardar cambios'}
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => setSelected(undefined)}
                >
                  Cancelar
                </button>
              </div>
            )}
          </form>
        </Dialog>
      )}
    </>
  );
}
