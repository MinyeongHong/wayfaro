import type { AnalysisState } from '../../analysisController';
import { Button } from '../ui/Button';

type AnalysisStatusProps = {
  state: AnalysisState;
  confirmDelete: boolean;
  onRetryPoll: () => void;
  onForget: () => void;
  onConfirmDelete: () => void;
};

function diagnostic(error: Record<string, string> | null): string {
  if (!error) return '';
  return ['code', 'error_type', 'stage', 'http_status'].flatMap(key => {
    const value = error[key];
    let safe: boolean;
    if (key === 'stage') safe = ['extraction', 'comparison'].includes(value);
    else if (key === 'http_status') safe = /^[1-5]\d{2}$/.test(value);
    else safe = /^[A-Z][A-Z0-9_]{0,70}$/.test(value);
    return safe ? [`${key}: ${value}`] : [];
  }).join(' · ');
}

export function AnalysisStatus({
  state, confirmDelete, onRetryPoll, onForget, onConfirmDelete,
}: AnalysisStatusProps) {
  const { view, phase, message } = state;
  if (phase === 'waiting' && view?.status !== 'completed' && view?.status !== 'failed') {
    return (
      <section className="max-w-[740px] pt-[50px] pb-[70px] max-mobile:pt-[25px]" role="status">
        <span className="inline-block size-2.5 rounded-full bg-[#527b62]" aria-hidden="true" />
        <h1 className="text-[42px] max-mobile:text-[33px]">
          {view?.status === 'processing' ? 'Reading your documents.'
            : view?.error ? 'Waiting for a server retry.' : 'Your analysis is queued.'}
        </h1>
        <p>
          {view?.status === 'pending' && view.error
            ? 'The worker encountered a temporary error and has scheduled another attempt. You do not need to submit again.'
            : 'We’ll check for the result automatically. There is no estimated completion time.'}
        </p>
      </section>
    );
  }
  if (phase === 'poll_error' || phase === 'unavailable') {
    return (
      <div className="notice my-[25px]" role="alert">
        <h2>{phase === 'unavailable' ? 'Analysis unavailable' : 'Status check interrupted'}</h2>
        <p>{message}</p>
        <Button variant="secondary" onClick={onRetryPoll}>Check status again</Button>
        {phase === 'unavailable' && (
          <Button variant="text" onClick={onForget}>Clear this screen only</Button>
        )}
      </div>
    );
  }
  if (phase === 'deleting') return <p role="status">Deleting your temporary analysis…</p>;
  if (phase === 'delete_error' && !confirmDelete) {
    return (
      <div role="alert">
        <p>{message}</p>
        <Button variant="secondary" onClick={onConfirmDelete}>Retry deletion</Button>
        <Button variant="text" onClick={onRetryPoll}>Check status again</Button>
      </div>
    );
  }
  if (view?.status === 'failed' && phase === 'waiting') {
    const details = diagnostic(view.error);
    return (
      <section className="notice my-[25px]" role="alert">
        <h1 className="text-[32px]">This comparison could not be completed.</h1>
        <p>
          No conclusion about your qualifications can be drawn from this failure.
          Delete this temporary analysis to start a new one.
        </p>
        {details && (
          <details>
            <summary>Safe diagnostic details</summary>
            <p className="font-mono text-xs">{details}</p>
          </details>
        )}
      </section>
    );
  }
  return null;
}
