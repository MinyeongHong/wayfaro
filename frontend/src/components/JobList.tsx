import type { JobPage } from '../types';
import { dateLabel, remoteLabels } from './JobDetail';

export function JobList({ data, selected, onSelect }: { data: JobPage; selected: string | null; onSelect: (id: string) => void }) {
  return <ul className="job-list">{data.items.map(job => <li key={job.id}>
    <button className={`job-card ${selected === job.id ? 'selected' : ''}`} aria-pressed={selected === job.id} onClick={() => onSelect(job.id)}>
      <span className="eyebrow">{job.origin === 'manual' ? '수동 등록' : job.provider}</span>
      <strong>{job.title || '제목 정보 없음'}</strong>
      <span>{job.company_name || '회사 정보 없음'}</span>
      <span>{job.location_text || '위치 정보 없음'}</span>
      <span className="badge">{remoteLabels[job.remote_mention]}</span>
      <small>{job.origin === 'manual' ? '등록' : '최초 수집'} {dateLabel(job.ingested_at)}</small>
    </button>
  </li>)}</ul>;
}

export function Pagination({ data, onPage }: { data: JobPage; onPage: (page: number) => void }) {
  return <nav className="pagination" aria-label="검색 결과 페이지">
    <button className="secondary" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>이전</button>
    <span>{data.page} / {Math.max(1, data.total_pages)} 페이지</span>
    <button className="secondary" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}>다음</button>
  </nav>;
}
