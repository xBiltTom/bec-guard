import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import type { Risk } from './types';
export const labels: Record<string, string> = {
  LOW: 'Bajo',
  MEDIUM: 'Medio',
  HIGH: 'Alto',
  CRITICAL: 'Crítico',
  OPEN: 'Abierta',
  UNDER_REVIEW: 'En revisión',
  CLOSED: 'Cerrada',
  CONFIRMED_BEC: 'BEC confirmado',
  FALSE_POSITIVE: 'Falso positivo',
  EXECUTIVE_IMPERSONATION: 'Suplantación ejecutiva',
  VENDOR_FRAUD: 'Fraude de proveedor',
  BANK_ACCOUNT_CHANGE: 'Cambio de cuenta',
  SENSITIVE_DATA_REQUEST: 'Solicitud de datos',
  OTHER: 'Otro patrón BEC',
  ADMIN: 'Administrador',
  MANAGER: 'Supervisor',
  ANALYST: 'Analista',
  AUDITOR: 'Auditor',
};
export const label = (value: string | null | undefined) =>
  value ? labels[value] || value : '—';
export const date = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString('es-PE', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—';
export function Badge({ value }: { value: string | null | undefined }) {
  return value ? (
    <span className={`badge badge-${value.toLowerCase()}`}>{label(value)}</span>
  ) : (
    <span>—</span>
  );
}
export function RiskBadge({ risk }: { risk: Risk | null }) {
  return <Badge value={risk} />;
}
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </div>
  );
}
export function LoadingState() {
  return (
    <p className="state" role="status">
      Cargando información…
    </p>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  return (
    <div className="state error" role="alert">
      <p>{error}</p>
      {retry && (
        <button className="secondary" onClick={retry}>
          Reintentar
        </button>
      )}
    </div>
  );
}
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state empty">{children}</div>;
}
export function Pagination({
  offset,
  count,
  onChange,
}: {
  offset: number;
  count: number;
  onChange: (offset: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Paginación">
      <span>{count ? `${offset + 1}–${offset + count}` : '0 resultados'}</span>
      <button
        className="secondary"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - 25))}
      >
        Anterior
      </button>
      <button
        className="secondary"
        disabled={count < 25}
        onClick={() => onChange(offset + 25)}
      >
        Siguiente
      </button>
    </nav>
  );
}
export function Dialog({
  title,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="dialog-header">
        <h2 id="dialog-title">{title}</h2>
        <button
          className="secondary"
          aria-label="Cerrar diálogo"
          disabled={busy}
          onClick={onClose}
        >
          Cerrar
        </button>
      </div>
      {children}
    </dialog>
  );
}
