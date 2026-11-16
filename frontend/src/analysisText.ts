import type { AnalysisPolicy, Evidence, MatchResult, SubmittedSnapshot } from './analysisTypes';

// Faithful English renderings of the current backend's Korean policy/templates.
// Unknown policy text is not silently replaced with an old consent notice.
const translations: Record<string, string> = {
  'CV와 JD 원문이 비교 분석을 위해 Google Gemini API로 전송됩니다. 입력과 결과는 지정된 기간 동안만 임시 보관하며 영구 저장하지 않습니다.': 'Your CV and job description are sent to Google Gemini for comparison. Inputs and results are kept temporarily for the stated period, not saved permanently.',
  'Google Gemini의 데이터 사용·보관은 계정·서비스 이용 조건에 따라 달라집니다. 무보관이나 학습 제외를 보장하지 않습니다. 외부 전송은 삭제 요청으로 취소할 수 없습니다.': 'Google Gemini’s use and retention of data depend on the account and service terms. Zero retention and exclusion from training are not guaranteed. Deleting your analysis cannot undo an external transfer.',
  '만료 즉시 조회와 새 LLM 호출을 차단합니다. Worker가 실행 중이면 주기적으로 DB에서 삭제하며 백업·외부 제공자 보관은 별도입니다.': 'Access and new AI calls stop at expiry. The running worker periodically removes expired database records. Backup and external provider retention are separate.',
  '모델은 인용된 CV 근거가 요건에 대응한다고 판단했습니다. 요구 수준과 맥락을 원문으로 확인하세요.': 'The model considers the cited CV evidence relevant to this requirement. Check the required level and context against the original text.',
  'CV 근거만으로 충족 여부를 확인할 수 없습니다. 실제 역량 부족이나 CV 누락을 확정하지 않습니다.': 'The CV evidence is not sufficient to verify this requirement. This does not establish a missing skill or an omission from your CV.',
  '아래에 인용된 기존 경험이 해당 요건과 어떻게 연결되는지 CV에서 명확히 드러내세요. 원문에 없는 성과나 수치를 추가하지 마세요.': 'Make the connection between the cited existing experience and this requirement clear in your CV. Do not add achievements or numbers that are not supported by your experience.',
  'CV 근거만으로 판단할 수 없습니다. 경험 유무와 수준을 먼저 확인하세요.': 'The CV alone is not enough to decide. First confirm whether you have this experience and at what level.',
  '미언급은 실제 역량 부족을 뜻하지 않습니다. CV_GAP과 SKILL_GAP은 확정하지 않습니다.': 'An omission is not evidence of a missing skill. CV gaps and skill gaps are not confirmed.',
  '정확한 인용 검증은 의미적 판단의 정확성을 보장하지 않습니다. 원문과 함께 확인하세요.': 'Exact quotations do not guarantee that the interpretation is correct. Review the original context.',
  '필수·우대 요구사항의 추출 누락이나 오분류가 있을 수 있습니다. 종합 점수는 제공하지 않습니다.': 'Required or preferred qualifications may be missed or classified incorrectly. No aggregate score is provided.',
};
export function englishText(text: string): string | null {
  if (translations[text]) return translations[text];
  const question = '공고의 다음 요건에 해당하는 경험이 있나요? 있다면 실제 업무와 범위를 확인해주세요: ';
  if (text.startsWith(question)) return `Do you have experience relevant to this requirement? If so, confirm the actual work and scope: ${text.slice(question.length)}`;
  // Server/user content in English is preserved; no automatic rewriting or invented translation.
  return /[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u3040-\u30ff\u3400-\u9fff]/u.test(text) ? null : text;
}
export function supportedPolicy(policy: AnalysisPolicy): boolean {
  return [policy.notice, policy.provider_retention_notice, policy.deletion_notice].every(text => englishText(text) !== null);
}
export function matchingEvidence(source: string, span: Evidence): boolean {
  const points = Array.from(source);
  return Number.isSafeInteger(span.start) && Number.isSafeInteger(span.end) && span.start >= 0 && span.end > span.start && span.end <= points.length && points.slice(span.start, span.end).join('') === span.quote;
}
export function inputProblem(cv: string, jd: string, policy: AnalysisPolicy): string | null {
  for (const [name, text] of [['CV', cv], ['job description', jd]]) {
    const points = Array.from(text);
    if (Array.from(text.trim()).length < 30) return `Your ${name} must contain at least 30 characters, excluding surrounding whitespace.`;
    if (points.length > policy.limits.max_document_characters) return `Your ${name} exceeds the ${policy.limits.max_document_characters.toLocaleString('en-US')}-character limit.`;
    if (text.includes('\0') || points.some(point => point.length === 1 && point.charCodeAt(0) >= 0xd800 && point.charCodeAt(0) <= 0xdfff)) return `Your ${name} contains an unsupported character.`;
  }
  const body = JSON.stringify({ cv_text: cv, jd_text: jd, consent: true, policy_version: policy.policy_version });
  if (new TextEncoder().encode(body).length > policy.limits.max_request_bytes) return 'The combined documents exceed the request size limit. Shorten them before submitting.';
  return null;
}

export function resultEvidenceMatches(snapshot: SubmittedSnapshot, result: MatchResult): boolean {
  const cv = Array.from(snapshot.cv), jd = Array.from(snapshot.jd);
  const matches = (source: string[], span: Evidence) => span.start >= 0 && span.end <= source.length && source.slice(span.start, span.end).join('') === span.quote;
  return result.requirements.every(item => item.jd_evidence.every(span => matches(jd, span)))
    && result.excluded_eligibility_evidence.every(span => matches(jd, span))
    && result.assessments.every(item => item.cv_evidence.every(span => matches(cv, span)))
    && result.cv_suggestions.every(item => item.cv_evidence.every(span => matches(cv, span)));
}
