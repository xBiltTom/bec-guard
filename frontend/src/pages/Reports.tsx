import { useState } from 'react';
import { authenticatedDownload, message } from '../api';
import { useAuth } from '../auth';
import { ErrorState, PageHeader } from '../components';
export function Reports() {
  const { user } = useAuth();
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState<'pdf' | 'xlsx' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const invalid = !!from && !!to && from > to;
  if (user?.role === 'ANALYST')
    return <ErrorState error="No tienes permisos para descargar reportes." />;
  async function download(format: 'pdf' | 'xlsx') {
    if (invalid) return;
    setBusy(format);
    setError('');
    setNotice('');
    const params = new URLSearchParams();
    if (from) params.set('from_date', from);
    if (to) params.set('to_date', to);
    try {
      await authenticatedDownload(
        `/reports/operational.${format}${params.size ? '?' + params : ''}`,
      );
      setNotice('Descarga preparada.');
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(null);
    }
  }
  return (
    <>
      <PageHeader
        title="Reporte operativo"
        description="Exporta un resumen de actividad para gestión y auditoría."
      />
      <section className="panel reports-panel">
        <h2>Periodo del reporte</h2>
        <p>
          Incluye correos recibidos, análisis y errores, distribución de riesgo,
          tipos BEC, estados y veredictos, y una lista de alertas. Sin fechas,
          incluye todos los datos disponibles.
        </p>
        <div className="filters report-dates">
          <label htmlFor="report-from">
            Fecha desde
            <input
              id="report-from"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              disabled={!!busy}
            />
          </label>
          <label htmlFor="report-to">
            Fecha hasta
            <input
              id="report-to"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              disabled={!!busy}
            />
          </label>
        </div>
        <p className="muted">
          Fechas inclusivas en UTC. Los estados y decisiones reflejan su valor
          actual. El reporte no incluye cuerpos de correo ni referencias
          bancarias.
        </p>
        {invalid && (
          <p role="alert" className="error">
            La fecha desde debe ser anterior o igual a la fecha hasta.
          </p>
        )}
        <div className="actions">
          <button
            disabled={!!busy || invalid}
            onClick={() => void download('pdf')}
          >
            {busy === 'pdf' ? 'Generando PDF…' : 'Descargar PDF'}
          </button>
          <button
            className="secondary"
            disabled={!!busy || invalid}
            onClick={() => void download('xlsx')}
          >
            {busy === 'xlsx' ? 'Generando Excel…' : 'Descargar Excel'}
          </button>
        </div>
        {error && (
          <p role="alert" className="error report-feedback">
            {error}
          </p>
        )}
        {(busy || notice) && (
          <p role="status" className="report-feedback">
            {busy ? 'Preparando el reporte…' : notice}
          </p>
        )}
      </section>
    </>
  );
}
