import { useEffect, useState } from 'react';
import { request } from './api';
import type { JobDetail as Detail, JobPage } from './types';
import { DiscoveryFilters } from './components/DiscoveryFilters';
import { JobDetail } from './components/JobDetail';
import { JobList, Pagination } from './components/JobList';
import { ManualJobForm } from './components/ManualJobForm';

const filterKeys = ['q', 'location', 'country_text', 'region_text', 'origin', 'source_id', 'remote_mention', 'sort', 'page', 'page_size'];

export function DiscoveryPage() {
  const [query, setQuery] = useState(window.location.search);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<JobPage | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const params = new URLSearchParams(query);
  const selected = params.get('job');
  const listParams = new URLSearchParams();
  filterKeys.forEach(key => { const value = params.get(key); if (value) listParams.set(key, value); });
  const listQuery = listParams.toString();
  const formKey = JSON.stringify(Array.from(listParams.entries()).filter(([key]) => key !== 'page'));

  useEffect(() => {
    const onPop = () => setQuery(window.location.search);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    request<JobPage>(`/jobs?${listQuery}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'The job list could not be loaded.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [listQuery, refresh]);

  useEffect(() => {
    setDetail(null); setDetailError('');
    if (!selected) { setDetailLoading(false); return; }
    const controller = new AbortController();
    setDetailLoading(true);
    request<Detail>(`/jobs/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setDetail(result); })
      .catch(cause => { if (!controller.signal.aborted) setDetailError(cause instanceof Error ? cause.message : 'The job details could not be loaded.'); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selected, refresh]);

  function navigate(next: URLSearchParams) {
    next.set('view', 'discover');
    const search = next.toString();
    const url = `${window.location.pathname}${search ? `?${search}` : ''}`;
    window.history.pushState(null, '', url); setQuery(window.location.search);
  }
  function selectJob(id: string | null) {
    const next = new URLSearchParams(window.location.search);
    if (id) next.set('job', id); else next.delete('job');
    navigate(next);
  }
  function apply(values: FormData) {
    const next = new URLSearchParams();
    values.forEach((value, key) => { const text = String(value).trim(); if (text) next.set(key, text); });
    next.set('page', '1'); navigate(next);
  }

  return <div className="discovery-page">
    <header className="page-heading"><p className="eyebrow">DISCOVER OPPORTUNITIES BEYOND BORDERS</p><h1>Explore your next opportunity.</h1><p>Browse collected and manually added roles. Location wording is not a work-eligibility assessment.</p></header>
    <DiscoveryFilters key={formKey} params={params} sources={data?.source_options || []} onApply={apply} />
    <div className="discovery-layout">
      <section className="results" aria-labelledby="results-title" aria-busy={loading}>
        <h2 id="results-title">Job discovery {data && !loading && !error && <small>{data.total} jobs</small>}</h2>
        {loading ? <p role="status">Loading jobs…</p> : error ? <div role="alert"><p>{error}</p><button onClick={() => setRefresh(value => value + 1)}>Try again</button></div> : data && <>
          {data.items.length ? <JobList data={data} selected={selected} onSelect={selectJob} /> : <p role="status">No jobs match these conditions. Try another search or page.</p>}
          <Pagination data={data} onPage={page => { const next = new URLSearchParams(query); next.set('page', String(page)); navigate(next); }} />
        </>}
      </section>
      <section className="panel detail" aria-label="Job details" aria-busy={detailLoading}>
        {detailLoading ? <p role="status">Loading job details…</p> : detailError ? <div role="alert"><p>{detailError}</p><button onClick={() => setRefresh(value => value + 1)}>Try again</button><button className="secondary" onClick={() => selectJob(null)}>Close details</button></div> : detail ? <JobDetail job={detail} onClose={() => selectJob(null)} /> : <p>Select a job to read the details.</p>}
      </section>
    </div>
    <ManualJobForm onCreated={id => { setRefresh(value => value + 1); selectJob(id); }} />
  </div>;
}
