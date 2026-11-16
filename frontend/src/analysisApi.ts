import { API } from './config';
import type { AnalysisAccepted, AnalysisPolicy, AnalysisView, Evidence, MatchResult } from './analysisTypes';

export class AnalysisApiError extends Error {
  constructor(public status: number | null, public kind: 'http' | 'network' | 'invalid' = 'http') {
    super(kind === 'invalid' ? 'The server returned an unsupported response.' : status === null ? 'The connection was interrupted.' : `Request failed (HTTP ${status}).`);
  }
}
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const string = (value: unknown): value is string => typeof value === 'string';
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(string);
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
const evidence = (value: unknown): value is Evidence => record(value) && integer(value.start) && integer(value.end) && value.end > value.start && string(value.quote) && !!value.quote;
const evidenceList = (value: unknown): value is Evidence[] => Array.isArray(value) && value.every(evidence);
const statuses = ['pending', 'processing', 'completed', 'failed'];
const id = (value: unknown): value is string => string(value) && /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(value);
const date = (value: unknown): value is string => string(value) && Number.isFinite(Date.parse(value));

function validResult(value: unknown): value is MatchResult {
  if (!record(value) || value.schema_version !== '1' || value.score !== null || value.work_eligibility !== 'NOT_ASSESSED' || !['gemini', 'openai'].includes(String(value.provider)) || !string(value.model) || value.prompt_version !== '1' || !strings(value.limitations)) return false;
  if (!Array.isArray(value.requirements) || !value.requirements.every(item => record(item) && string(item.id) && string(item.text) && ['REQUIRED', 'PREFERRED', 'UNSPECIFIED'].includes(String(item.importance)) && evidenceList(item.jd_evidence) && item.jd_evidence.length > 0)) return false;
  const requirementIds = value.requirements.map(item => item.id);
  if (new Set(requirementIds).size !== requirementIds.length) return false;
  if (!Array.isArray(value.assessments) || !value.assessments.every(item => record(item) && requirementIds.includes(item.requirement_id) && ['MATCHED', 'UNVERIFIED'].includes(String(item.status)) && string(item.rationale) && evidenceList(item.cv_evidence) && (item.status !== 'MATCHED' || item.cv_evidence.length > 0))) return false;
  if (value.assessments.length !== requirementIds.length || new Set(value.assessments.map(item => item.requirement_id)).size !== requirementIds.length) return false;
  if (!evidenceList(value.excluded_eligibility_evidence) || !Array.isArray(value.cv_suggestions) || !value.cv_suggestions.every(item => record(item) && requirementIds.includes(item.requirement_id) && ['HIGHLIGHT_EXISTING_EVIDENCE', 'ASK_CONFIRMATION'].includes(String(item.kind)) && string(item.text) && evidenceList(item.cv_evidence) && (item.question === null || string(item.question)))) return false;
  return integer(value.matched_count) && integer(value.unverified_count) && value.matched_count === value.assessments.filter(item => item.status === 'MATCHED').length && value.unverified_count === value.assessments.filter(item => item.status === 'UNVERIFIED').length;
}
function validPolicy(value: unknown): value is AnalysisPolicy {
  return record(value) && ['policy_version', 'provider', 'notice', 'provider_retention_notice', 'provider_policy_url', 'deletion_notice'].every(key => string(value[key]) && !!value[key]) && value.consent_required === true && integer(value.retention_hours) && value.retention_hours > 0 && integer(value.session_retention_days) && value.score === null && value.work_eligibility === 'NOT_ASSESSED' && record(value.limits) && ['max_document_characters', 'max_request_bytes', 'analyses_per_session', 'global_daily_requests'].every(key => integer((value.limits as Record<string, unknown>)[key]) && Number((value.limits as Record<string, unknown>)[key]) > 0);
}
function validAccepted(value: unknown): value is AnalysisAccepted {
  return record(value) && id(value.analysis_id) && id(value.task_id) && statuses.includes(String(value.status)) && value.status_url === `/api/v1/analyses/${value.analysis_id}` && date(value.expires_at) && string(value.csrf_token) && /^[A-Za-z0-9_-]{20,200}$/.test(value.csrf_token);
}
function validView(value: unknown): value is AnalysisView {
  return record(value) && id(value.analysis_id) && id(value.task_id) && statuses.includes(String(value.status)) && date(value.expires_at) && (value.error === null || record(value.error) && Object.values(value.error).every(string)) && (value.result === null || validResult(value.result)) && (value.status !== 'completed' || validResult(value.result));
}

export function csrfCookie(): string | undefined {
  const entry = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('wayfaro_cv_csrf='));
  const value = entry?.slice('wayfaro_cv_csrf='.length);
  return value && /^[A-Za-z0-9_-]{20,200}$/.test(value) ? value : undefined;
}
async function send<T>(path: string, signal: AbortSignal, validate: (value: unknown) => value is T, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1${path}`, { ...options, credentials: 'include', cache: 'no-store', signal });
  } catch {
    // No original fetch exception, request URL, document or response is retained.
    throw new AnalysisApiError(null, 'network');
  }
  if (!response.ok) throw new AnalysisApiError(response.status);
  let value: unknown;
  try { value = await response.json(); } catch { throw new AnalysisApiError(response.status, 'invalid'); }
  if (!validate(value)) throw new AnalysisApiError(response.status, 'invalid');
  return value;
}
export const analysisApi = {
  policy: (signal: AbortSignal) => send('/analyses/policy', signal, validPolicy),
  create: (body: { cv_text: string; jd_text: string; consent: true; policy_version: string }, signal: AbortSignal, csrf?: string) => send('/analyses', signal, validAccepted, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify(body),
  }),
  read: (analysisId: string, signal: AbortSignal) => send(`/analyses/${encodeURIComponent(analysisId)}`, signal, validView),
  remove: async (analysisId: string, csrf: string, signal: AbortSignal) => {
    let response: Response;
    try {
      response = await fetch(`${API}/api/v1/analyses/${encodeURIComponent(analysisId)}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf }, credentials: 'include', cache: 'no-store', signal });
    } catch { throw new AnalysisApiError(null, 'network'); }
    if (response.status !== 204) throw new AnalysisApiError(response.status);
  },
};
export type AnalysisApi = typeof analysisApi;
