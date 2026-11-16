import type { Evidence } from '../../analysisTypes';
import { matchingEvidence } from '../../analysisText';

type EvidenceListProps = { title: string; spans: Evidence[]; source: string };

export function EvidenceList({ title, spans, source }: EvidenceListProps) {
  return (
    <div className="min-w-0 rounded-[3px] border border-[#e0e2d8] bg-[#f3f3ed] px-[22px] py-[18px]">
      <h3 className="mt-0 text-[13px]">{title}</h3>
      {spans.length ? spans.map((span, index) => (
        <figure key={`${span.start}-${span.end}-${index}`}>
          {matchingEvidence(source, span) ? (
            <>
              <blockquote>{span.quote}</blockquote>
              <figcaption>Characters {span.start}–{span.end} · end exclusive</figcaption>
            </>
          ) : (
            <p className="text-[#833c32]">
              This quotation could not be verified against the submitted document.
            </p>
          )}
        </figure>
      )) : <p className="text-muted">No supporting passage identified.</p>}
    </div>
  );
}
