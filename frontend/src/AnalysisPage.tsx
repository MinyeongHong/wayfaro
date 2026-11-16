import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { AnalysisController } from './analysisController';
import { englishText, inputProblem } from './analysisText';
import { safeUrl } from './api';
import { AnalysisResults } from './components/analysis/AnalysisResults';
import { DeleteAnalysisDialog } from './components/analysis/DeleteAnalysisDialog';

function diagnostic(error: Record<string, string> | null): string {
  if (!error) return '';
  return ['code', 'error_type', 'stage', 'http_status'].flatMap(key => {
    const value = error[key];
    const safe = key === 'stage' ? ['extraction', 'comparison'].includes(value) : key === 'http_status' ? /^[1-5]\d{2}$/.test(value) : /^[A-Z][A-Z0-9_]{0,70}$/.test(value);
    return safe ? [`${key}: ${value}`] : [];
  }).join(' · ');
}
export function AnalysisPage({ controller }: { controller: AnalysisController }) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const hero = useRef<HTMLHeadingElement>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [understandDuplicate, setUnderstandDuplicate] = useState(false);
  useEffect(() => { controller.activate(); return () => controller.pause(); }, [controller]);
  useEffect(() => { if (!state.accepted) setConfirmDelete(false); }, [state.accepted]);
  useEffect(() => { if (state.phase === 'deleted') hero.current?.focus(); }, [state.phase]);
  const policy = state.policy;
  const problem = policy ? inputProblem(state.cv, state.jd, policy) : null;
  const submitting = state.phase === 'submitting';
  const view = state.view;
  const complete = view?.status === 'completed';
  const failed = view?.status === 'failed';
  const policyUrl = policy ? safeUrl(policy.provider_policy_url) : null;
  return <div className="analysis-page">
    {!state.accepted && <>
      <section className="hero" aria-labelledby="hero-title"><p className="eyebrow">A CLEARER NEXT APPLICATION</p><h1 id="hero-title" ref={hero} tabIndex={-1}>See where your experience<br className="desktop-break" /> meets the opportunity.</h1><p className="hero-description">Compare your CV with a job description. Understand the evidence, what remains unverified, and what to clarify next.</p><p className="hero-meta">No account. Text only. Temporary by design.</p></section>
      <form onSubmit={event => { event.preventDefault(); void controller.submit(); }} aria-label="Compare your CV and job description">
        <div className="input-grid">
          <div className="document-field"><div className="field-heading"><label htmlFor="cv-text">Your CV</label><span>01</span></div><p id="cv-help" className="small muted">Paste the experience you want to compare. Remove personal details you do not need to share.</p><textarea id="cv-text" name="cv-text" value={state.cv} onChange={event => controller.setText('cv', event.target.value)} autoComplete="off" spellCheck={false} disabled={submitting || state.phase === 'submit_unknown'} aria-describedby="cv-help cv-count" placeholder="Paste your CV text here…" /><span id="cv-count" className="character-count">{Array.from(state.cv).length.toLocaleString('en-US')} characters{policy ? ` · limit ${policy.limits.max_document_characters.toLocaleString('en-US')}` : ''}</span></div>
          <div className="document-field"><div className="field-heading"><label htmlFor="jd-text">Job description</label><span>02</span></div><p id="jd-help" className="small muted">Paste the role and its requirements. This private input will not be added to public job discovery.</p><textarea id="jd-text" name="jd-text" value={state.jd} onChange={event => controller.setText('jd', event.target.value)} autoComplete="off" spellCheck={false} disabled={submitting || state.phase === 'submit_unknown'} aria-describedby="jd-help jd-count" placeholder="Paste the job description here…" /><span id="jd-count" className="character-count">{Array.from(state.jd).length.toLocaleString('en-US')} characters{policy ? ` · limit ${policy.limits.max_document_characters.toLocaleString('en-US')}` : ''}</span></div>
        </div>
        <section className="consent-panel" aria-labelledby="consent-title"><h2 id="consent-title">Your documents, handled with care.</h2>
          {state.policyLoading ? <p role="status">Loading the current consent policy…</p> : state.policyError ? <div role="alert"><p>{state.policyError}</p><button type="button" className="secondary" onClick={() => void controller.loadPolicy()}>Retry policy</button></div> : policy && <>
            <p>{englishText(policy.notice)}</p><p className="small"><strong>Temporary retention: up to {policy.retention_hours} hours.</strong> You can delete your analysis earlier. The anonymous ownership session lasts up to {policy.session_retention_days} days; it is not permanent CV storage.</p>
            <details><summary>External processing and deletion details</summary><p>{englishText(policy.provider_retention_notice)}</p><p>{englishText(policy.deletion_notice)}</p>{policyUrl && <a href={policyUrl} target="_blank" rel="noopener noreferrer">Read the provider’s terms ↗</a>}</details>
            <label className="consent-checkbox"><input type="checkbox" checked={state.consent} disabled={submitting || state.phase === 'submit_unknown'} onChange={event => controller.setConsent(event.target.checked)} /><span>I agree to send these documents to {policy.provider} for this comparison and to the temporary processing described above.</span></label>
          </>}
        </section>
        {state.message && <p className="notice" role={state.phase === 'deleted' ? 'status' : 'alert'}>{state.message}</p>}
        {problem && (state.cv || state.jd) && <p className="small" id="input-problem">{problem}</p>}
        {state.phase === 'submit_unknown' ? <div className="unknown-submission"><label className="consent-checkbox"><input type="checkbox" checked={understandDuplicate} onChange={event => setUnderstandDuplicate(event.target.checked)} /><span>I understand that a new submission may duplicate an accepted request.</span></label><button type="button" className="secondary" disabled={!understandDuplicate} onClick={() => { controller.acknowledgeUnknown(); setUnderstandDuplicate(false); }}>Return to inputs without resending</button></div> : <div className="submit-row"><button className="primary" type="submit" disabled={submitting || !policy || state.policyLoading || !state.consent || !!problem}>{submitting ? 'Submitting once…' : 'Compare my documents'}<span aria-hidden="true"> ↗</span></button><p className="small muted">No match score. No visa or work-eligibility assessment.</p></div>}
        {state.phase === 'submit_error' && <button type="button" className="text-button" onClick={() => void controller.loadPolicy()}>Refresh consent policy</button>}
      </form>
      <p className="session-note">Documents and results are held only in this page’s memory. Refreshing or leaving the site clears this screen; an accepted server analysis may remain until deletion or expiry.</p>
    </>}
    {state.accepted && <>
      <div className="analysis-toolbar"><span className="eyebrow">PRIVATE COMPARISON</span><button className="text-button danger-text" disabled={state.phase === 'deleting'} onClick={() => setConfirmDelete(true)}>Delete temporary analysis</button></div>
      {state.phase === 'waiting' && !complete && !failed && <section className="processing-panel" role="status"><span className="activity-dot" aria-hidden="true" /><h1>{view?.status === 'processing' ? 'Reading your documents.' : view?.error ? 'Waiting for a server retry.' : 'Your analysis is queued.'}</h1><p>{view?.status === 'pending' && view.error ? 'The worker encountered a temporary error and has scheduled another attempt. You do not need to submit again.' : 'We’ll check for the result automatically. There is no estimated completion time.'}</p></section>}
      {['poll_error', 'unavailable'].includes(state.phase) && <div className="feedback-panel" role="alert"><h2>{state.phase === 'unavailable' ? 'Analysis unavailable' : 'Status check interrupted'}</h2><p>{state.message}</p><button className="secondary" onClick={() => controller.retryPoll()}>Check status again</button>{state.phase === 'unavailable' && <button className="text-button" onClick={() => controller.forget()}>Clear this screen only</button>}</div>}
      {state.phase === 'deleting' && <p role="status">Deleting your temporary analysis…</p>}
      {state.phase === 'delete_error' && !confirmDelete && <div role="alert"><p>{state.message}</p><button className="secondary" onClick={() => setConfirmDelete(true)}>Retry deletion</button><button className="text-button" onClick={() => controller.retryPoll()}>Check status again</button></div>}
      {failed && state.phase === 'waiting' && <section className="feedback-panel" role="alert"><h1>This comparison could not be completed.</h1><p>No conclusion about your qualifications can be drawn from this failure. Delete this temporary analysis to start a new one.</p>{diagnostic(view.error) && <details><summary>Safe diagnostic details</summary><p className="diagnostic">{diagnostic(view.error)}</p></details>}</section>}
      {complete && view.result && state.snapshot && ['waiting', 'delete_error'].includes(state.phase) && <AnalysisResults result={view.result} snapshot={state.snapshot} />}
      <p className="session-note">Temporary analysis expires {new Date(state.accepted.expires_at).toLocaleString('en-US')}. Expired records are removed by the running worker. Deletion does not undo external processing.</p>
      {confirmDelete && <DeleteAnalysisDialog busy={state.phase === 'deleting'} error={state.phase === 'delete_error' ? state.message : ''} onCancel={() => setConfirmDelete(false)} onDelete={() => void controller.deleteAnalysis()} />}
    </>}
  </div>;
}
