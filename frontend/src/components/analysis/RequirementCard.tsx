import type { Assessment, Requirement, SubmittedSnapshot, Suggestion } from '../../analysisTypes';
import { englishText } from '../../analysisText';
import { EvidenceList } from './EvidenceList';

type RequirementCardProps = {
  requirement: Requirement;
  assessment: Assessment;
  suggestions: Suggestion[];
  snapshot: SubmittedSnapshot;
};

const importanceLabels = {
  REQUIRED: 'Required',
  PREFERRED: 'Preferred',
  UNSPECIFIED: 'Importance not specified',
};

export function RequirementCard({
  requirement, assessment, suggestions, snapshot,
}: RequirementCardProps) {
  return (
    <article className="border-t border-line py-8">
      <div className="flex items-center gap-3.5">
        <span className={`rounded-[3px] px-[9px] py-[5px] text-[10px] font-semibold tracking-[.07em] ${assessment.status === 'MATCHED' ? 'bg-[#e7eee3] text-[#2c5742]' : 'bg-[#eee9de] text-[#67563b]'}`}>
          {assessment.status}
        </span>
        <span className="text-xs text-[#6a7168]">{importanceLabels[requirement.importance]}</span>
      </div>
      <h2 className="font-editorial text-2xl font-normal">{requirement.text}</h2>
      <p>
        {englishText(assessment.rationale)
          ?? 'This interpretation is not available in English. Review the original evidence and requirement together.'}
      </p>
      <div className="my-[22px] grid grid-cols-2 gap-5 max-mobile:grid-cols-1">
        <EvidenceList title="From the job description" spans={requirement.jd_evidence} source={snapshot.jd} />
        <EvidenceList title="From your CV" spans={assessment.cv_evidence} source={snapshot.cv} />
      </div>
      {suggestions.length > 0 && (
        <div className="text-sm [&_p]:max-w-[850px]">
          <h3 className="mb-2 text-sm">What you can do next</h3>
          {suggestions.map((suggestion, index) => (
            <div key={index}>
              <p>
                {englishText(suggestion.text)
                  ?? 'This suggestion is not available in English. Review the original evidence above.'}
              </p>
              {suggestion.question && (
                <p className="border-l-2 border-[#b3a181] pl-[15px]">
                  {englishText(suggestion.question)
                    ?? 'This confirmation question is not available in English.'}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
