export interface AnalysisPolicy {
  policy_version: string;
  provider: string;
  consent_required: boolean;
  retention_hours: number;
  session_retention_days: number;
  notice: string;
  provider_retention_notice: string;
  provider_policy_url: string;
  deletion_notice: string;
  limits: { max_document_characters: number; max_request_bytes: number; analyses_per_session: number; global_daily_requests: number };
  score: null;
  work_eligibility: 'NOT_ASSESSED';
}
export interface Evidence { start: number; end: number; quote: string }
export interface Requirement {
  id: string; text: string; importance: 'REQUIRED' | 'PREFERRED' | 'UNSPECIFIED'; jd_evidence: Evidence[];
}
export interface Assessment {
  requirement_id: string; status: 'MATCHED' | 'UNVERIFIED'; rationale: string; cv_evidence: Evidence[];
}
export interface Suggestion {
  requirement_id: string; kind: 'HIGHLIGHT_EXISTING_EVIDENCE' | 'ASK_CONFIRMATION'; text: string;
  cv_evidence: Evidence[]; question: string | null;
}
export interface MatchResult {
  schema_version: '1'; requirements: Requirement[]; assessments: Assessment[];
  excluded_eligibility_evidence: Evidence[]; cv_suggestions: Suggestion[];
  matched_count: number; unverified_count: number; score: null; work_eligibility: 'NOT_ASSESSED';
  limitations: string[]; provider: 'openai' | 'gemini'; model: string; prompt_version: '1';
}
export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'failed';
export interface AnalysisAccepted {
  analysis_id: string; task_id: string; status: AnalysisStatus; status_url: string; expires_at: string; csrf_token: string;
}
export interface AnalysisView {
  analysis_id: string; task_id: string; status: AnalysisStatus; expires_at: string;
  result: MatchResult | null; error: Record<string, string> | null;
}
export interface SubmittedSnapshot { cv: string; jd: string }
