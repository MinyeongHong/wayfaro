import { useEffect, useRef } from 'react';

export function DeleteAnalysisDialog({ busy, error, onCancel, onDelete }: {
  busy: boolean; error: string; onCancel: () => void; onDelete: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal(); cancel.current?.focus();
    return () => { dialog.current?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={dialog} className="delete-dialog" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="delete-title">Delete this temporary analysis?</h2>
    <p id="delete-description">The server will delete its inputs and result and cancel pending work. This screen will also clear your documents. An external AI transfer cannot be undone; provider and backup retention remain separate.</p>
    {error && <p className="error-text" role="alert">{error}</p>}
    <div className="button-row"><button type="button" className="secondary" ref={cancel} disabled={busy} onClick={onCancel}>{error ? 'Close confirmation' : 'Keep analysis'}</button><button type="button" className="danger" disabled={busy} onClick={onDelete}>{busy ? 'Deleting…' : 'Delete analysis'}</button></div>
  </dialog>;
}
