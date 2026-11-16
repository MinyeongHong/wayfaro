import { useEffect, useRef } from 'react';
import { Button } from '../ui/Button';

type DeleteAnalysisDialogProps = {
  busy: boolean;
  error: string;
  onCancel: () => void;
  onDelete: () => void;
};

export function DeleteAnalysisDialog({ busy, error, onCancel, onDelete }: DeleteAnalysisDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    cancel.current?.focus();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);

  return (
    <dialog
      ref={dialog}
      className="m-auto w-[calc(100%_-_32px)] max-w-[520px] rounded-[7px] border border-[#c6cec0] bg-page p-[30px] text-ink backdrop:bg-[#17291e66]"
      aria-labelledby="delete-title"
      aria-describedby="delete-description"
      onCancel={event => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id="delete-title" className="font-editorial text-[28px] font-normal">Delete this temporary analysis?</h2>
      <p id="delete-description">
        The server will delete its inputs and result and cancel pending work. This screen
        will also clear your documents. An external AI transfer cannot be undone;
        provider and backup retention remain separate.
      </p>
      {error && <p className="text-[#833c32]" role="alert">{error}</p>}
      <div className="mt-6 flex flex-wrap justify-end gap-3.5">
        <Button variant="secondary" ref={cancel} disabled={busy} onClick={onCancel}>
          {error ? 'Close confirmation' : 'Keep analysis'}
        </Button>
        <Button variant="danger" disabled={busy} onClick={onDelete}>
          {busy ? 'Deleting…' : 'Delete analysis'}
        </Button>
      </div>
    </dialog>
  );
}
