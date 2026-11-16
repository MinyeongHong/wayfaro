import { useState } from 'react';
import { request } from '../api';
import type { JobCreated } from '../types';

export function ManualJobForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [text, setText] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true); setResult('');
    try {
      const body = await request<JobCreated>('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw_text: text }) });
      setResult(`Job added. Task ID: ${body.task_id}. AI extraction for manually added listings is not implemented yet.`);
      setText(''); onCreated(body.job_id);
    } catch (error) { setResult(error instanceof Error ? error.message : 'The job could not be added.'); }
    finally { setLoading(false); }
  }
  return <details className="panel manual"><summary>Add a job manually</summary>
    <p>This saves the original posting to public job discovery. The separate extraction task returns NOT_IMPLEMENTED. Do not paste your CV or other private information here.</p>
    <form onSubmit={submit}>
      <label htmlFor="manual-text">Original job posting</label>
      <textarea id="manual-text" value={text} onChange={event => setText(event.target.value)} minLength={30} required placeholder="Paste a job description of at least 30 characters." />
      <button disabled={loading || text.length < 30}>{loading ? 'Adding…' : 'Add job'}</button>
    </form>
    {result && <p role="status">{result}</p>}
  </details>;
}
