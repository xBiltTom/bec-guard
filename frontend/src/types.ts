export type Role = 'ADMIN' | 'MANAGER' | 'ANALYST' | 'AUDITOR';
export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}
export type Risk = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AlertStatus = 'OPEN' | 'UNDER_REVIEW' | 'CLOSED';
export type Verdict = 'CONFIRMED_BEC' | 'FALSE_POSITIVE';
export const becTypes = [
  'EXECUTIVE_IMPERSONATION',
  'VENDOR_FRAUD',
  'BANK_ACCOUNT_CHANGE',
  'SENSITIVE_DATA_REQUEST',
  'OTHER',
] as const;
export type BECType = (typeof becTypes)[number];
export interface Signal {
  code: string;
  description: string;
  source: 'RULE' | 'CONTEXT' | 'SEMANTIC';
  contribution?: number;
}
export interface Analysis {
  id: string;
  email_id: string;
  status: 'COMPLETED' | 'ERROR';
  deterministic_score: number;
  semantic_score: number | null;
  risk_score: number | null;
  risk_level: Risk | null;
  bec_type: BECType | null;
  signals: Signal[];
  summary: string | null;
  recommended_action: string | null;
  error_code: string | null;
  analyzed_at: string;
  policy_version: string;
  provider: string | null;
  model: string | null;
}
export interface EmailSummary {
  id: string;
  message_id: string;
  sender_name: string | null;
  sender_email: string;
  reply_to: string | null;
  subject: string;
  received_at: string;
  ingested_at: string;
}
export interface EmailDetail extends EmailSummary {
  return_path: string | null;
  to_recipients: string[];
  cc_recipients: string[];
  authentication_results: string | null;
  body_text: string;
}
export interface AlertSummary {
  id: string;
  analysis_id: string;
  email_id: string;
  status: AlertStatus;
  verdict: Verdict | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  risk_score: number;
  risk_level: Risk;
  bec_type: BECType | null;
  sender_name: string | null;
  sender_email: string;
  subject: string;
  received_at: string;
  created_at: string;
  updated_at: string;
}
export interface AlertDetail {
  id: string;
  analysis_id: string;
  status: AlertStatus;
  verdict: Verdict | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  resolution: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  analysis: Analysis;
}
export interface Dashboard {
  emails_total: number;
  analyses_completed: number;
  analyses_error: number;
  alerts: Record<'open' | 'under_review' | 'closed', number>;
  verdicts: Record<'confirmed_bec' | 'false_positive', number>;
  risk_distribution: Record<Risk, number>;
  bec_type_distribution: { bec_type: BECType; count: number }[];
  alerts_last_7_days: { date: string; count: number }[];
}
export interface Executive {
  id: string;
  name: string;
  position: string;
  department: string | null;
  email: string;
  is_active: boolean;
}
export interface Vendor {
  id: string;
  name: string;
  domain: string;
  contact_email: string | null;
  bank_account_reference: string | null;
  is_active: boolean;
}
export interface AuditEvent {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_role: Role | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  created_at: string;
  details: Record<string, string> | null;
}
