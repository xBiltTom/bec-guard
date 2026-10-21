import { Link } from 'react-router-dom';
import { Badge, EmptyState, date, label } from './components';
import type { Analysis, EmailDetail } from './types';
export function AnalysisView({ analysis }: { analysis: Analysis }) {
  if (analysis.status === 'ERROR')
    return (
      <section className="panel analysis-error">
        <h2>Análisis incompleto</h2>
        <p>El análisis no terminó. No hay un nivel de riesgo disponible.</p>
        <p className="error-code">{analysis.error_code}</p>
      </section>
    );
  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <h2>Evaluación del sistema</h2>
          <small>{date(analysis.analyzed_at)}</small>
        </div>
        <p className="summary">{analysis.summary}</p>
        <div className="recommendation">
          <h3>Acción recomendada</h3>
          <p>{analysis.recommended_action}</p>
        </div>
      </section>
      <section className="panel">
        <h2>Evidencia explicable</h2>
        {!analysis.signals.length && (
          <EmptyState>No se registraron señales adicionales.</EmptyState>
        )}
        {(['CONTEXT', 'RULE', 'SEMANTIC'] as const).map((source) => {
          const signals = analysis.signals.filter((s) => s.source === source);
          return (
            signals.length > 0 && (
              <div className="signal-group" key={source}>
                <h3>
                  {source === 'CONTEXT'
                    ? 'Contexto organizacional'
                    : source === 'RULE'
                      ? 'Reglas técnicas y de contenido'
                      : 'Análisis semántico'}
                </h3>
                <ul className="signals">
                  {signals.map((s, i) => (
                    <li key={`${s.code}-${i}`}>
                      <div>
                        <strong>{s.code}</strong>
                        {source !== 'SEMANTIC' && !!s.contribution && (
                          <small>+{s.contribution} puntos deterministas</small>
                        )}
                      </div>
                      <p>{s.description}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )
          );
        })}
        <details>
          <summary>Detalle del cálculo</summary>
          <dl className="facts">
            <div>
              <dt>Determinista</dt>
              <dd>{analysis.deterministic_score}/100</dd>
            </div>
            <div>
              <dt>Semántico</dt>
              <dd>{analysis.semantic_score}/100</dd>
            </div>
            <div>
              <dt>Política</dt>
              <dd>{analysis.policy_version}</dd>
            </div>
          </dl>
          <p className="muted">
            El score es una evaluación del sistema, no una probabilidad de
            fraude.
          </p>
        </details>
      </section>
    </>
  );
}
export function EmailContent({ email }: { email: EmailDetail }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Correo original</h2>
        <Link to={`/emails/${email.id}`}>Abrir correo</Link>
      </div>
      <h3 className="email-subject">{email.subject || '(Sin asunto)'}</h3>
      <dl className="facts email-headers">
        <div>
          <dt>From</dt>
          <dd>
            {email.sender_name} &lt;{email.sender_email}&gt;
          </dd>
        </div>
        <div>
          <dt>Reply-To</dt>
          <dd>{email.reply_to || '—'}</dd>
        </div>
        <div>
          <dt>Return-Path</dt>
          <dd>{email.return_path || '—'}</dd>
        </div>
        <div>
          <dt>To</dt>
          <dd>{email.to_recipients.join(', ') || '—'}</dd>
        </div>
        <div>
          <dt>Cc</dt>
          <dd>{email.cc_recipients.join(', ') || '—'}</dd>
        </div>
        <div>
          <dt>Fecha</dt>
          <dd>{date(email.received_at)}</dd>
        </div>
        <div>
          <dt>Authentication-Results</dt>
          <dd>{email.authentication_results || 'Sin resultados'}</dd>
        </div>
      </dl>
      <details open>
        <summary>Contenido en texto plano</summary>
        <pre className="email-body">{email.body_text || '(Sin contenido)'}</pre>
      </details>
    </section>
  );
}
export function AnalysisHeadline({ analysis }: { analysis: Analysis }) {
  return (
    <div className="risk-headline">
      <div>
        <Badge value={analysis.risk_level} />
        <strong className="score">
          {analysis.risk_score}
          <small>/100</small>
        </strong>
      </div>
      <p>{label(analysis.bec_type)}</p>
    </div>
  );
}
