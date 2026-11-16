import type { AnalysisPolicy } from '../../analysisTypes';
import { englishText } from '../../analysisText';
import { safeUrl } from '../../api';
import { Button } from '../ui/Button';

type ConsentPanelProps = {
  policy: AnalysisPolicy | null;
  loading: boolean;
  error: string;
  consent: boolean;
  disabled: boolean;
  onConsentChange: (checked: boolean) => void;
  onRetry: () => void;
};

export function ConsentPanel({
  policy, loading, error, consent, disabled, onConsentChange, onRetry,
}: ConsentPanelProps) {
  const policyUrl = policy ? safeUrl(policy.provider_policy_url) : null;

  return (
    <section className="mt-8 rounded-[5px] border border-[#d8ded0] bg-[#f0f2ea] px-[30px] py-[26px] text-sm max-mobile:p-[22px]" aria-labelledby="consent-title">
      <h2 id="consent-title" className="text-lg">Your documents, handled with care.</h2>
      {loading ? (
        <p role="status">Loading the current consent policy…</p>
      ) : error ? (
        <div role="alert">
          <p>{error}</p>
          <Button variant="secondary" onClick={onRetry}>Retry policy</Button>
        </div>
      ) : policy && (
        <>
          <p>{englishText(policy.notice)}</p>
          <p className="text-[13px]">
            <strong>Temporary retention: up to {policy.retention_hours} hours.</strong>{' '}
            You can delete your analysis earlier. The anonymous ownership session lasts up to{' '}
            {policy.session_retention_days} days; it is not permanent CV storage.
          </p>
          <details className="my-[18px]">
            <summary>External processing and deletion details</summary>
            <p>{englishText(policy.provider_retention_notice)}</p>
            <p>{englishText(policy.deletion_notice)}</p>
            {policyUrl && (
              <a href={policyUrl} target="_blank" rel="noopener noreferrer">
                Read the provider’s terms ↗
              </a>
            )}
          </details>
          <label className="mt-5 flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={consent}
              disabled={disabled}
              onChange={event => onConsentChange(event.target.checked)}
            />
            <span>
              I agree to send these documents to {policy.provider} for this comparison
              and to the temporary processing described above.
            </span>
          </label>
        </>
      )}
    </section>
  );
}
