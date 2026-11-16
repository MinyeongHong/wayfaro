import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { AnalysisController } from '../analysisController';
import { AnalysisForm } from '../components/analysis/AnalysisForm';
import { AnalysisStatus } from '../components/analysis/AnalysisStatus';
import { AnalysisResults } from '../components/analysis/AnalysisResults';
import { DeleteAnalysisDialog } from '../components/analysis/DeleteAnalysisDialog';
import { Button } from '../components/ui/Button';

export function AnalysisPage({ controller }: { controller: AnalysisController }) {
  // Subscribe once here, then pass data and callbacks to the child widgets.
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const hero = useRef<HTMLHeadingElement>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    controller.activate();
    return () => controller.pause();
  }, [controller]);
  useEffect(() => {
    if (!state.accepted) setConfirmDelete(false);
  }, [state.accepted]);
  useEffect(() => {
    if (state.phase === 'deleted') hero.current?.focus();
  }, [state.phase]);

  const { accepted, view, snapshot, phase } = state;
  const showResult = phase === 'waiting' || phase === 'delete_error';

  return (
    <div>
      {!accepted ? (
        <>
          <section className="mt-[68px] mb-12 max-w-[800px] max-mobile:mt-10" aria-labelledby="hero-title">
            <p className="eyebrow">A CLEARER NEXT APPLICATION</p>
            <h1 id="hero-title" ref={hero} tabIndex={-1}>
              See where your experience<br className="max-mobile:hidden" /> meets the opportunity.
            </h1>
            <p className="max-w-[620px] text-lg leading-[1.7] text-[#59675e] max-mobile:text-base">
              Compare your CV with a job description. Understand the evidence,
              what remains unverified, and what to clarify next.
            </p>
            <p className="mt-6 text-[13px] text-[#5a665e]">No account. Text only. Temporary by design.</p>
          </section>
          <AnalysisForm
            state={state}
            onTextChange={(field, value) => controller.setText(field, value)}
            onConsentChange={checked => controller.setConsent(checked)}
            onSubmit={() => void controller.submit()}
            onReloadPolicy={() => void controller.loadPolicy()}
            onAcknowledgeUnknown={() => controller.acknowledgeUnknown()}
          />
          <p className="session-note">
            Documents and results are held only in this page’s memory. Refreshing or leaving
            the site clears this screen; an accepted server analysis may remain until deletion or expiry.
          </p>
        </>
      ) : (
        <>
          <div className="my-[42px] flex items-center justify-between gap-5 max-mobile:gap-3">
            <span className="eyebrow max-mobile:text-[10px]">PRIVATE COMPARISON</span>
            <Button variant="dangerText" disabled={phase === 'deleting'} onClick={() => setConfirmDelete(true)}>
              Delete temporary analysis
            </Button>
          </div>
          <AnalysisStatus
            state={state}
            confirmDelete={confirmDelete}
            onRetryPoll={() => controller.retryPoll()}
            onForget={() => controller.forget()}
            onConfirmDelete={() => setConfirmDelete(true)}
          />
          {showResult && view?.status === 'completed' && view.result && snapshot && (
            <AnalysisResults result={view.result} snapshot={snapshot} />
          )}
          <p className="session-note">
            Temporary analysis expires {new Date(accepted.expires_at).toLocaleString('en-US')}.
            Expired records are removed by the running worker. Deletion does not undo external processing.
          </p>
          {confirmDelete && (
            <DeleteAnalysisDialog
              busy={phase === 'deleting'}
              error={phase === 'delete_error' ? state.message : ''}
              onCancel={() => setConfirmDelete(false)}
              onDelete={() => void controller.deleteAnalysis()}
            />
          )}
        </>
      )}
    </div>
  );
}
