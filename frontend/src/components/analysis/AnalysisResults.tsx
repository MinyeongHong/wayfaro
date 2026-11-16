import { useEffect, useRef } from 'react';
import type { MatchResult, SubmittedSnapshot } from '../../analysisTypes';
import { englishText } from '../../analysisText';
import { EvidenceList } from './EvidenceList';
import { RequirementCard } from './RequirementCard';

export function AnalysisResults({ result, snapshot }: { result: MatchResult; snapshot: SubmittedSnapshot }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);

  return (
    <section aria-labelledby="analysis-result-title">
      <p className="eyebrow">YOUR COMPARISON</p>
      <h1
        id="analysis-result-title"
        className="mb-[22px] max-w-[650px] text-[38px] max-mobile:text-[30px]"
        tabIndex={-1}
        ref={heading}
      >
        The evidence, requirement by requirement.
      </h1>
      <div className="my-[26px] flex flex-wrap gap-7 text-sm max-mobile:gap-3 [&_strong]:mr-1.5 [&_strong]:text-2xl [&_strong]:font-medium">
        <span><strong>{result.matched_count}</strong> with matching evidence</span>
        <span><strong>{result.unverified_count}</strong> not verified</span>
      </div>
      <p className="notice">
        UNVERIFIED means the documents do not establish a match. It does not mean you lack
        the skill. CV gaps and skill gaps are not confirmed in this analysis.
      </p>
      {!result.requirements.length && (
        <p className="rounded-[5px] border border-line bg-surface p-6 max-mobile:p-[18px]">
          No career requirements were identified. Review the job description before drawing conclusions.
        </p>
      )}
      {result.requirements.map(requirement => (
        <RequirementCard
          key={requirement.id}
          requirement={requirement}
          assessment={result.assessments.find(item => item.requirement_id === requirement.id)!}
          suggestions={result.cv_suggestions.filter(item => item.requirement_id === requirement.id)}
          snapshot={snapshot}
        />
      ))}
      <aside className="border-t border-line py-7 text-sm">
        <h2 className="text-[21px]">Keep the context in view</h2>
        <ul>
          {result.limitations.map((text, index) => (
            <li className="my-2" key={index}>
              {englishText(text) ?? 'Interpretations may be incomplete. Check the original documents.'}
            </li>
          ))}
        </ul>
        <p>
          <strong>Work eligibility: not assessed.</strong>{' '}
          This comparison does not evaluate visas, sponsorship, or permission to work.
        </p>
        {result.excluded_eligibility_evidence.length > 0 && (
          <details className="my-5">
            <summary>Job description passages excluded from career-fit assessment</summary>
            <EvidenceList
              title="Work eligibility references · not assessed"
              spans={result.excluded_eligibility_evidence}
              source={snapshot.jd}
            />
          </details>
        )}
        <p className="text-[13px] text-muted">
          Quotations use the submitted text, unchanged. Positions count Unicode code points,
          not browser UTF-16 units.
        </p>
      </aside>
    </section>
  );
}
