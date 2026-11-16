import { useEffect, useRef } from 'react';
import type { Evidence, MatchResult, SubmittedSnapshot } from '../../analysisTypes';
import { englishText, matchingEvidence } from '../../analysisText';

function EvidenceList({ title, spans, source }: { title: string; spans: Evidence[]; source: string }) {
  return <div className="evidence-column"><h3>{title}</h3>{spans.length ? spans.map((span, index) => <figure key={`${span.start}-${span.end}-${index}`}>
    {matchingEvidence(source, span) ? <><blockquote>{span.quote}</blockquote><figcaption>Characters {span.start}–{span.end} · end exclusive</figcaption></> : <p className="error-text">This quotation could not be verified against the submitted document.</p>}
  </figure>) : <p className="muted">No supporting passage identified.</p>}</div>;
}
export function AnalysisResults({ result, snapshot }: { result: MatchResult; snapshot: SubmittedSnapshot }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return <section className="analysis-results" aria-labelledby="analysis-result-title">
    <div className="section-heading"><div><p className="eyebrow">YOUR COMPARISON</p><h1 id="analysis-result-title" tabIndex={-1} ref={heading}>The evidence, requirement by requirement.</h1></div></div>
    <div className="result-summary"><span><strong>{result.matched_count}</strong> with matching evidence</span><span><strong>{result.unverified_count}</strong> not verified</span></div>
    <p className="notice">UNVERIFIED means the documents do not establish a match. It does not mean you lack the skill. CV gaps and skill gaps are not confirmed in this analysis.</p>
    {!result.requirements.length && <p className="panel">No career requirements were identified. Review the job description before drawing conclusions.</p>}
    {result.requirements.map(requirement => {
      const assessment = result.assessments.find(item => item.requirement_id === requirement.id)!;
      const suggestions = result.cv_suggestions.filter(item => item.requirement_id === requirement.id);
      return <article className="requirement" key={requirement.id}>
        <div className="requirement-heading"><span className={`status-tag ${assessment.status === 'MATCHED' ? 'matched' : 'unverified'}`}>{assessment.status}</span><span className="requirement-importance">{({ REQUIRED: 'Required', PREFERRED: 'Preferred', UNSPECIFIED: 'Importance not specified' })[requirement.importance]}</span></div>
        <h2>{requirement.text}</h2>
        <p>{englishText(assessment.rationale) ?? 'This interpretation is not available in English. Review the original evidence and requirement together.'}</p>
        <div className="evidence-grid"><EvidenceList title="From the job description" spans={requirement.jd_evidence} source={snapshot.jd} /><EvidenceList title="From your CV" spans={assessment.cv_evidence} source={snapshot.cv} /></div>
        {suggestions.length > 0 && <div className="suggestions"><h3>What you can do next</h3>{suggestions.map((suggestion, index) => <div key={index}>
          <p>{englishText(suggestion.text) ?? 'This suggestion is not available in English. Review the original evidence above.'}</p>
          {suggestion.question && <p className="confirmation-question">{englishText(suggestion.question) ?? 'This confirmation question is not available in English.'}</p>}
        </div>)}</div>}
      </article>;
    })}
    <aside className="limitations"><h2>Keep the context in view</h2><ul>{result.limitations.map((text, index) => <li key={index}>{englishText(text) ?? 'Interpretations may be incomplete. Check the original documents.'}</li>)}</ul>
      <p><strong>Work eligibility: not assessed.</strong> This comparison does not evaluate visas, sponsorship, or permission to work.</p>
      {result.excluded_eligibility_evidence.length > 0 && <details><summary>Job description passages excluded from career-fit assessment</summary><EvidenceList title="Work eligibility references · not assessed" spans={result.excluded_eligibility_evidence} source={snapshot.jd} /></details>}
      <p className="small muted">Quotations use the submitted text, unchanged. Positions count Unicode code points, not browser UTF-16 units.</p>
    </aside>
  </section>;
}
