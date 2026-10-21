import type { AlertDetail, Dashboard, EmailDetail } from '../types';
export const user = {
  id: 'user-1',
  name: 'Lucía',
  role: 'ANALYST',
  email: 'lucia@example.com',
};
export const email: EmailDetail = {
  id: 'email-1',
  message_id: '<test@example.com>',
  sender_name: 'Dirección',
  sender_email: 'ceo@unknown.example',
  reply_to: 'reply@other.example',
  return_path: null,
  to_recipients: ['finance@example.com'],
  cc_recipients: [],
  subject: 'Cambio de cuenta pendiente',
  body_text: '<script>unsafe()</script>\nhttps://untrusted.example',
  authentication_results: 'spf=fail',
  received_at: '2026-10-21T12:00:00Z',
  ingested_at: '2026-10-21T12:01:00Z',
};
export const alert: AlertDetail = {
  id: 'alert-1',
  analysis_id: 'analysis-1',
  status: 'OPEN',
  assigned_to: null,
  assigned_to_name: null,
  verdict: null,
  resolution: null,
  closed_at: null,
  created_at: '2026-10-21T12:00:00Z',
  updated_at: '2026-10-21T12:00:00Z',
  analysis: {
    id: 'analysis-1',
    email_id: 'email-1',
    status: 'COMPLETED',
    deterministic_score: 90,
    semantic_score: 90,
    risk_score: 90,
    risk_level: 'CRITICAL',
    bec_type: 'BANK_ACCOUNT_CHANGE',
    signals: [
      {
        code: 'BANK_ACCOUNT_CHANGE',
        source: 'RULE',
        description: 'Cambio de cuenta solicitado.',
        contribution: 15,
      },
      {
        code: 'IDENTITY_MISMATCH',
        source: 'CONTEXT',
        description: 'La identidad no coincide.',
      },
      {
        code: 'SEMANTIC_REQUEST',
        source: 'SEMANTIC',
        description: 'Se solicita una transferencia.',
        contribution: 0,
      },
    ],
    summary: 'Solicitud de cambio de cuenta con identidad inconsistente.',
    recommended_action: 'Verificar por un canal conocido.',
    policy_version: 'hybrid-v1',
    error_code: null,
    analyzed_at: '2026-10-21T12:01:00Z',
    provider: 'openai',
    model: 'test',
  },
};
export const summary = {
  ...alert,
  ...email,
  id: alert.id,
  email_id: email.id,
  risk_level: 'CRITICAL',
  risk_score: 90,
  bec_type: 'BANK_ACCOUNT_CHANGE',
};
export const dashboard: Dashboard = {
  emails_total: 12,
  analyses_completed: 10,
  analyses_error: 2,
  alerts: { open: 3, under_review: 1, closed: 2 },
  verdicts: { confirmed_bec: 1, false_positive: 1 },
  risk_distribution: { LOW: 4, MEDIUM: 1, HIGH: 2, CRITICAL: 3 },
  bec_type_distribution: [{ bec_type: 'BANK_ACCOUNT_CHANGE', count: 3 }],
  alerts_last_7_days: Array.from({ length: 7 }, (_, i) => ({
    date: `2026-10-${15 + i}`,
    count: i % 3,
  })),
};
export const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
