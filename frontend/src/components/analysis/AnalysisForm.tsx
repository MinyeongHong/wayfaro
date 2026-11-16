import { useState } from 'react';
import type { AnalysisState } from '../../analysisController';
import { inputProblem } from '../../analysisText';
import { Button } from '../ui/Button';
import { ConsentPanel } from './ConsentPanel';
import { DocumentInput } from './DocumentInput';

type AnalysisFormProps = {
  state: AnalysisState;
  onTextChange: (field: 'cv' | 'jd', value: string) => void;
  onConsentChange: (checked: boolean) => void;
  onSubmit: () => void;
  onReloadPolicy: () => void;
  onAcknowledgeUnknown: () => void;
};

export function AnalysisForm({
  state, onTextChange, onConsentChange, onSubmit, onReloadPolicy, onAcknowledgeUnknown,
}: AnalysisFormProps) {
  const [understandDuplicate, setUnderstandDuplicate] = useState(false);
  const { policy } = state;
  const problem = policy ? inputProblem(state.cv, state.jd, policy) : null;
  const submitting = state.phase === 'submitting';
  const inputDisabled = submitting || state.phase === 'submit_unknown';

  return (
    <form
      aria-label="Compare your CV and job description"
      onSubmit={event => { event.preventDefault(); onSubmit(); }}
    >
      <div className="grid grid-cols-2 gap-7 max-mobile:grid-cols-1">
        <DocumentInput
          name="cv"
          label="Your CV"
          number="01"
          help="Paste the experience you want to compare. Remove personal details you do not need to share."
          placeholder="Paste your CV text here…"
          value={state.cv}
          limit={policy?.limits.max_document_characters}
          disabled={inputDisabled}
          onChange={value => onTextChange('cv', value)}
        />
        <DocumentInput
          name="jd"
          label="Job description"
          number="02"
          help="Paste the role and its requirements. This document is used only for your private comparison."
          placeholder="Paste the job description here…"
          value={state.jd}
          limit={policy?.limits.max_document_characters}
          disabled={inputDisabled}
          onChange={value => onTextChange('jd', value)}
        />
      </div>
      <ConsentPanel
        policy={policy}
        loading={state.policyLoading}
        error={state.policyError}
        consent={state.consent}
        disabled={inputDisabled}
        onConsentChange={onConsentChange}
        onRetry={onReloadPolicy}
      />
      {state.message && (
        <p className="notice" role={state.phase === 'deleted' ? 'status' : 'alert'}>
          {state.message}
        </p>
      )}
      {problem && (state.cv || state.jd) && (
        <p className="text-[13px]" id="input-problem">{problem}</p>
      )}
      {state.phase === 'submit_unknown' ? (
        <div className="notice [&>button]:mt-[18px]">
          <label className="mt-5 flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={understandDuplicate}
              onChange={event => setUnderstandDuplicate(event.target.checked)}
            />
            <span>I understand that a new submission may duplicate an accepted request.</span>
          </label>
          <Button
            variant="secondary"
            disabled={!understandDuplicate}
            onClick={() => {
              onAcknowledgeUnknown();
              setUnderstandDuplicate(false);
            }}
          >
            Return to inputs without resending
          </Button>
        </div>
      ) : (
        <div className="mt-7 flex items-center gap-6 max-mobile:flex-col max-mobile:items-stretch max-mobile:gap-2.5">
          <Button
            type="submit"
            size="large"
            disabled={submitting || !policy || state.policyLoading || !state.consent || !!problem}
          >
            {submitting ? 'Submitting once…' : 'Compare my documents'}
            <span className="ml-[18px]" aria-hidden="true"> ↗</span>
          </Button>
          <p className="text-[13px] text-muted">No match score. No visa or work-eligibility assessment.</p>
        </div>
      )}
      {state.phase === 'submit_error' && (
        <Button variant="text" onClick={onReloadPolicy}>Refresh consent policy</Button>
      )}
    </form>
  );
}
