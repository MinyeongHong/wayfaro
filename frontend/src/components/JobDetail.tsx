import type { JobDetail as Detail } from '../types';
import { safeUrl } from '../api';

export function dateLabel(value: string | null): string {
  if (!value) return '정보 없음';
  return new Date(value).toLocaleString('ko-KR');
}
export const remoteLabels = {
  PRESENT: '원격근무 관련 표현 있음',
  NOT_MENTIONED: '위치 원문에 관련 표현 없음',
  UNKNOWN: '위치 정보 없음 · 확인되지 않음',
};

export function JobDetail({ job, onClose }: { job: Detail; onClose: () => void }) {
  const sourceUrl = safeUrl(job.source_url);
  return <article aria-labelledby="detail-title">
    <button className="secondary close" onClick={onClose}>상세 닫기</button>
    <p className="eyebrow">{job.origin === 'manual' ? '수동 등록' : `${job.provider} · ${job.board_token}`}</p>
    <h2 id="detail-title">{job.title || '제목 정보 없음'}</h2>
    <dl className="metadata">
      <div><dt>회사</dt><dd>{job.company_name || '정보 없음'}</dd></div>
      <div><dt>위치 원문</dt><dd>{job.location_text || '정보 없음'}</dd></div>
      <div><dt>부서</dt><dd>{job.department || '정보 없음'}</dd></div>
      <div><dt>원격 표현</dt><dd>{remoteLabels[job.remote_mention]}</dd></div>
      <div><dt>게시 시각</dt><dd>{dateLabel(job.published_at)}</dd></div>
      <div><dt>{job.origin === 'manual' ? '등록 시각' : '최초 수집 시각'}</dt><dd>{dateLabel(job.ingested_at)}</dd></div>
      <div><dt>최근 저장 시각</dt><dd>{dateLabel(job.updated_at)}</dd></div>
      <div><dt>출처의 수정 시각</dt><dd>{dateLabel(job.source_updated_at)}</dd></div>
    </dl>
    <p className="notice">원격 표현의 언급 여부는 실제 원격근무나 해외 거주자의 근무 가능 여부를 뜻하지 않습니다. 비자 스폰서십과 취업 자격은 확인되지 않았습니다.</p>
    {sourceUrl ? <a className="source-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">원본 채용공고 열기 ↗</a> : <p>원본 링크 정보 없음</p>}
    <h3>공고 내용</h3>
    <div className="description">{(job.description_text ?? job.raw_text) || '설명 정보 없음'}</div>
  </article>;
}
