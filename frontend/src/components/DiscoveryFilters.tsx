import type { JobPage } from '../types';

export function DiscoveryFilters({ params, sources, onApply }: {
  params: URLSearchParams; sources: JobPage['source_options']; onApply: (values: FormData) => void;
}) {
  return <form className="filters panel" onSubmit={event => { event.preventDefault(); onApply(new FormData(event.currentTarget)); }}>
    <div className="filter-grid">
      <label>Keywords<input name="q" defaultValue={params.get('q') || ''} maxLength={200} placeholder="Role, company, description" /></label>
      <label>Location keywords<input name="location" defaultValue={params.get('location') || ''} maxLength={200} placeholder="Search original location wording" /></label>
      <label>Country wording<input name="country_text" defaultValue={params.get('country_text') || ''} maxLength={200} placeholder="e.g. Italy" /></label>
      <label>Region wording<input name="region_text" defaultValue={params.get('region_text') || ''} maxLength={200} placeholder="e.g. Rome" /></label>
      <label>Listing type<select name="origin" defaultValue={params.get('origin') || ''}><option value="">All</option><option value="ats">ATS listings</option><option value="manual">Manually added</option></select></label>
      <label>ATS source<select key={sources.map(source => source.id).join(',')} name="source_id" defaultValue={params.get('source_id') || ''}><option value="">All sources</option>{params.get('source_id') && !sources.some(source => source.id === params.get('source_id')) && <option value={params.get('source_id')!}>Selected source · unavailable</option>}{sources.map(source => <option key={source.id} value={source.id}>{source.company_name} · {source.board_token}</option>)}</select></label>
      <label>Remote wording in location<select name="remote_mention" defaultValue={params.get('remote_mention') || ''}><option value="">All</option><option value="PRESENT">Mentioned</option><option value="NOT_MENTIONED">Not mentioned</option><option value="UNKNOWN">Location unavailable</option></select></label>
      <label>Sort by<select name="sort" defaultValue={params.get('sort') || 'created_desc'}><option value="created_desc">Newest added</option><option value="published_desc">Newest published</option><option value="updated_desc">Recently updated</option></select></label>
    </div>
    <p className="filter-help">Search the original location wording. A remote-work mention does not confirm permission to work remotely.</p>
    <button type="submit">Apply search</button>
  </form>;
}
