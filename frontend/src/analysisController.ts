import { analysisApi, AnalysisApiError, csrfCookie, type AnalysisApi } from './analysisApi';
import { inputProblem, supportedPolicy, resultEvidenceMatches } from './analysisText';
import type { AnalysisAccepted, AnalysisPolicy, AnalysisView, SubmittedSnapshot } from './analysisTypes';

export type Phase = 'editing' | 'submitting' | 'submit_error' | 'submit_unknown' | 'waiting' | 'poll_error' | 'unavailable' | 'deleting' | 'delete_error' | 'deleted';
export interface AnalysisState {
  cv: string; jd: string; consent: boolean; policy: AnalysisPolicy | null; policyLoading: boolean; policyError: string;
  phase: Phase; accepted: AnalysisAccepted | null; view: AnalysisView | null; snapshot: SubmittedSnapshot | null; message: string;
}
const initial = (): AnalysisState => ({ cv: '', jd: '', consent: false, policy: null, policyLoading: false, policyError: '', phase: 'editing', accepted: null, view: null, snapshot: null, message: '' });
function errorMessage(error: unknown): string {
  if (!(error instanceof AnalysisApiError)) return 'The request could not be completed. Please try again.';
  if (error.kind === 'invalid') return 'The server response could not be safely displayed. Try checking the status again.';
  switch (error.status) {
    case 403: return 'The session security check failed. Use the same browser and host, allow cookies, and try again.';
    case 404: return 'This analysis may have expired, been deleted, or belong to another browser session.';
    case 413: return 'The documents are too large. Shorten them before submitting.';
    case 422: return 'Check your documents and refresh the consent policy before trying again.';
    case 429: return 'The temporary analysis limit has been reached. Please try later.';
    case 503: return 'The analysis service is not available. Please try later.';
    default: return 'The connection could not be completed. You can try again.';
  }
}
export interface ControllerOptions {
  api?: AnalysisApi; csrf?: () => string | undefined;
  schedule?: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel?: (timer: ReturnType<typeof setTimeout>) => void;
}
export class AnalysisController {
  private state = initial();
  private listeners = new Set<() => void>();
  private active = false;
  private epoch = 0;
  private abort: AbortController | null = null;
  private policyAbort: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private delay = 1500;
  private api: AnalysisApi;
  private csrf: () => string | undefined;
  private schedule: NonNullable<ControllerOptions['schedule']>;
  private cancel: NonNullable<ControllerOptions['cancel']>;
  constructor(options: ControllerOptions = {}) {
    this.api = options.api ?? analysisApi; this.csrf = options.csrf ?? csrfCookie;
    this.schedule = options.schedule ?? setTimeout; this.cancel = options.cancel ?? clearTimeout;
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<AnalysisState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(listener => listener()); }
  private stop() {
    this.epoch += 1; this.abort?.abort(); this.abort = null;
    if (this.timer !== null) this.cancel(this.timer);
    this.timer = null;
  }
  activate() {
    this.active = true;
    if (!this.state.policy) void this.loadPolicy();
    if (this.state.accepted && this.state.phase === 'waiting' && !['completed', 'failed'].includes(this.state.view?.status ?? '')) void this.poll();
  }
  pause() {
    this.active = false; this.policyAbort?.abort(); this.policyAbort = null; this.stop();
    if (this.state.phase === 'submitting') this.set({ phase: 'submit_unknown', message: 'The submission was interrupted. It may already be queued. It has not been sent again.' });
    if (this.state.phase === 'deleting') this.set({ phase: 'delete_error', message: 'Deletion could not be confirmed. Try deleting again.' });
    if (this.state.policyLoading) this.set({ policyLoading: false });
  }
  async loadPolicy() {
    this.policyAbort?.abort(); const abort = new AbortController(); this.policyAbort = abort;
    this.set({ policyLoading: true, policyError: '', consent: false });
    try {
      const policy = await this.api.policy(abort.signal);
      if (abort.signal.aborted || !this.active) return;
      if (!supportedPolicy(policy)) throw new Error('unsupported policy');
      this.set({ policy, policyLoading: false });
    } catch {
      if (!abort.signal.aborted && this.active) this.set({ policy: null, policyLoading: false, policyError: 'The current consent notice could not be loaded in English. Please retry before submitting.' });
    }
  }
  setText(field: 'cv' | 'jd', value: string) {
    if (this.state.accepted || this.state.phase === 'submitting') return;
    this.set({ [field]: value, message: '' });
  }
  setConsent(value: boolean) { this.set({ consent: value }); }
  async submit() {
    const state = this.state;
    if (!this.active || state.accepted || state.phase === 'submitting' || state.phase === 'submit_unknown' || !state.policy || state.policyLoading || !state.consent) return;
    const problem = inputProblem(state.cv, state.jd, state.policy);
    if (problem) { this.set({ message: problem }); return; }
    this.stop(); const epoch = this.epoch; const abort = new AbortController(); this.abort = abort;
    const snapshot = Object.freeze({ cv: state.cv, jd: state.jd });
    this.set({ phase: 'submitting', snapshot, message: '' });
    try {
      const accepted = await this.api.create({ cv_text: snapshot.cv, jd_text: snapshot.jd, consent: true, policy_version: state.policy.policy_version }, abort.signal, this.csrf());
      if (epoch !== this.epoch || !this.active) return;
      this.set({ accepted, phase: 'waiting' }); this.delay = 1500;
      void this.poll();
    } catch (error) {
      if (epoch !== this.epoch || !this.active) return;
      // Any lost/malformed response or server 5xx may follow a committed POST. Never resend it.
      const ambiguous = !(error instanceof AnalysisApiError) || error.kind !== 'http' || error.status === null || error.status >= 500;
      this.set({ phase: ambiguous ? 'submit_unknown' : 'submit_error', message: ambiguous ? 'We could not confirm whether your request was accepted. It may already be queued. We have not sent it again. Any accepted data remains subject to the temporary retention policy.' : errorMessage(error) });
    }
  }
  acknowledgeUnknown() {
    if (this.state.phase === 'submit_unknown') this.set({ phase: 'editing', consent: false, message: 'If you submit again, it will be a separate request and may incur another AI call.' });
  }
  private async poll() {
    const accepted = this.state.accepted;
    if (!accepted || !this.active || this.state.phase !== 'waiting') return;
    const epoch = this.epoch; const abort = new AbortController(); this.abort = abort;
    try {
      const view = await this.api.read(accepted.analysis_id, abort.signal);
      if (epoch !== this.epoch || !this.active) return;
      if (view.analysis_id !== accepted.analysis_id || view.task_id !== accepted.task_id) throw new AnalysisApiError(null, 'invalid');
      if (view.result && (!this.state.snapshot || !resultEvidenceMatches(this.state.snapshot, view.result))) throw new AnalysisApiError(null, 'invalid');
      this.set({ view, message: '' });
      if (view.status === 'pending' || view.status === 'processing') {
        this.timer = this.schedule(() => { this.timer = null; void this.poll(); }, this.delay);
        this.delay = Math.min(this.delay * 1.5, 8000);
      }
    } catch (error) {
      if (epoch !== this.epoch || !this.active) return;
      this.set({ phase: error instanceof AnalysisApiError && error.status === 404 ? 'unavailable' : 'poll_error', message: errorMessage(error) });
    }
  }
  retryPoll() {
    if (!this.state.accepted || !this.active || !['poll_error', 'unavailable', 'delete_error'].includes(this.state.phase)) return;
    this.stop(); this.set({ phase: 'waiting', message: '' }); void this.poll();
  }
  async deleteAnalysis() {
    const accepted = this.state.accepted;
    if (!accepted || !this.active || this.state.phase === 'deleting') return;
    this.stop(); const epoch = this.epoch; const abort = new AbortController(); this.abort = abort;
    this.set({ phase: 'deleting', message: '' });
    try {
      await this.api.remove(accepted.analysis_id, this.csrf() ?? accepted.csrf_token, abort.signal);
      if (epoch !== this.epoch || !this.active) return;
      this.forget(true);
    } catch (error) {
      if (epoch !== this.epoch || !this.active) return;
      this.set({ phase: 'delete_error', message: `Deletion was not confirmed. ${errorMessage(error)}` });
    }
  }
  forget(deleted = false) {
    this.stop(); this.set({ ...initial(), policy: this.state.policy, phase: deleted ? 'deleted' : 'editing', message: deleted ? 'Your temporary analysis was deleted. The documents and result have also been cleared from this screen.' : '' });
  }
}
