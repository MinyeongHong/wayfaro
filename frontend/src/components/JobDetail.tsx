import type { JobDetail as Detail } from '../types';
import { safeUrl } from '../api';

export function dateLabel(value: string | null): string {
  if (!value) return 'Not provided';
  return new Date(value).toLocaleString('en-US');
}
export const remoteLabels = {
  PRESENT: 'Remote wording mentioned',
  NOT_MENTIONED: 'No remote wording in location',
  UNKNOWN: 'Location unavailable · not verified',
};

export function JobDetail({ job, onClose }: { job: Detail; onClose: () => void }) {
  const sourceUrl = safeUrl(job.source_url);
  return <article aria-labelledby="detail-title">
    <button className="secondary close" onClick={onClose}>Close details</button>
    <p className="eyebrow">{job.origin === 'manual' ? 'Manually added' : `${job.provider} · ${job.board_token}`}</p>
    <h2 id="detail-title">{job.title || 'Title unavailable'}</h2>
    <dl className="metadata">
      <div><dt>Company</dt><dd>{job.company_name || 'Not provided'}</dd></div>
      <div><dt>Original location</dt><dd>{job.location_text || 'Not provided'}</dd></div>
      <div><dt>Department</dt><dd>{job.department || 'Not provided'}</dd></div>
      <div><dt>Remote wording</dt><dd>{remoteLabels[job.remote_mention]}</dd></div>
      <div><dt>Published</dt><dd>{dateLabel(job.published_at)}</dd></div>
      <div><dt>{job.origin === 'manual' ? 'Added' : 'First collected'}</dt><dd>{dateLabel(job.ingested_at)}</dd></div>
      <div><dt>Last saved</dt><dd>{dateLabel(job.updated_at)}</dd></div>
      <div><dt>Updated at source</dt><dd>{dateLabel(job.source_updated_at)}</dd></div>
    </dl>
    <p className="notice">Remote wording does not confirm remote work or permission to work from another country. Visa sponsorship and work eligibility have not been assessed.</p>
    {sourceUrl ? <a className="source-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">Open original job posting ↗</a> : <p>Original link unavailable</p>}
    <h3>Job description</h3>
    <div className="description">{(job.description_text ?? job.raw_text) || 'Description unavailable'}</div>
  </article>;
}
