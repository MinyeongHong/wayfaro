import type { JobPage } from '../types';

export function DiscoveryFilters({ params, sources, onApply }: {
  params: URLSearchParams; sources: JobPage['source_options']; onApply: (values: FormData) => void;
}) {
  return <form className="filters panel" onSubmit={event => { event.preventDefault(); onApply(new FormData(event.currentTarget)); }}>
    <div className="filter-grid">
      <label>키워드<input name="q" defaultValue={params.get('q') || ''} maxLength={200} placeholder="직무, 회사, 설명" /></label>
      <label>위치 키워드<input name="location" defaultValue={params.get('location') || ''} maxLength={200} placeholder="국가·지역의 위치 원문 검색" /></label>
      <label>국가명 · 위치 원문 검색<input name="country_text" defaultValue={params.get('country_text') || ''} maxLength={200} placeholder="예: Italy" /></label>
      <label>지역명 · 위치 원문 검색<input name="region_text" defaultValue={params.get('region_text') || ''} maxLength={200} placeholder="예: Rome" /></label>
      <label>등록 유형<select name="origin" defaultValue={params.get('origin') || ''}><option value="">전체</option><option value="ats">ATS 수집</option><option value="manual">수동 등록</option></select></label>
      <label>ATS 출처<select key={sources.map(source => source.id).join(',')} name="source_id" defaultValue={params.get('source_id') || ''}><option value="">모든 출처</option>{params.get('source_id') && !sources.some(source => source.id === params.get('source_id')) && <option value={params.get('source_id')!}>선택한 출처 · 정보 없음</option>}{sources.map(source => <option key={source.id} value={source.id}>{source.company_name} · {source.board_token}</option>)}</select></label>
      <label>위치 원문의 원격 표현<select name="remote_mention" defaultValue={params.get('remote_mention') || ''}><option value="">전체</option><option value="PRESENT">관련 표현 있음</option><option value="NOT_MENTIONED">관련 표현 없음</option><option value="UNKNOWN">위치 정보 없음</option></select></label>
      <label>정렬<select name="sort" defaultValue={params.get('sort') || 'created_desc'}><option value="created_desc">등록 최신순</option><option value="published_desc">게시 최신순</option><option value="updated_desc">최근 갱신순</option></select></label>
    </div>
    <p className="filter-help">위치 원문에 적힌 표현을 검색합니다. 원격 관련 표현이 있어도 실제 원격근무 가능 여부는 확인되지 않았습니다.</p>
    <button type="submit">검색 적용</button>
  </form>;
}
