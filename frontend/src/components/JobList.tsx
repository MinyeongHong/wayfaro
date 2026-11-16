import type { JobPage } from '../types';
import { dateLabel, remoteLabels } from './JobDetail';

export function JobList({ data, selected, onSelect }: { data: JobPage; selected: string | null; onSelect: (id: string) => void }) {
  return <ul className="job-list">{data.items.map(job => <li key={job.id}>
    <button className={`job-card ${selected === job.id ? 'selected' : ''}`} aria-pressed={selected === job.id} onClick={() => onSelect(job.id)}>
      <span className="eyebrow">{job.origin === 'manual' ? 'Manually added' : job.provider}</span>
      <strong>{job.title || 'Title unavailable'}</strong>
      <span>{job.company_name || 'Company unavailable'}</span>
      <span>{job.location_text || 'Location unavailable'}</span>
      <span className="badge">{remoteLabels[job.remote_mention]}</span>
      <small>{job.origin === 'manual' ? 'Added' : 'First collected'} {dateLabel(job.ingested_at)}</small>
    </button>
  </li>)}</ul>;
}

export function Pagination({ data, onPage }: { data: JobPage; onPage: (page: number) => void }) {
  return <nav className="pagination" aria-label="Job search pages">
    <button className="secondary" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button>
    <span>Page {data.page} of {Math.max(1, data.total_pages)}</span>
    <button className="secondary" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}>Next</button>
  </nav>;
}
