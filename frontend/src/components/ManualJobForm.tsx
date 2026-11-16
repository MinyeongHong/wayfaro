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
      setResult(`공고가 등록되었습니다. 작업 ID: ${body.task_id}. AI 추출은 아직 구현되지 않았습니다.`);
      setText(''); onCreated(body.job_id);
    } catch (error) { setResult(error instanceof Error ? error.message : '등록에 실패했습니다.'); }
    finally { setLoading(false); }
  }
  return <details className="panel manual"><summary>채용공고 직접 등록</summary>
    <p>공고 원문을 저장합니다. AI 추출 작업은 NOT_IMPLEMENTED로 처리됩니다.</p>
    <form onSubmit={submit}>
      <label htmlFor="manual-text">채용공고 원문</label>
      <textarea id="manual-text" value={text} onChange={event => setText(event.target.value)} minLength={30} required placeholder="30자 이상의 채용공고를 붙여 넣으세요." />
      <button disabled={loading || text.length < 30}>{loading ? '등록 중…' : '공고 등록'}</button>
    </form>
    {result && <p role="status">{result}</p>}
  </details>;
}
