import { ClaimChip } from '@/components/ClaimChip';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { formatDateTime } from '@/lib/format';
import type { AssistantAnswer } from '@/types/api';

export interface AnswerPanelProps {
  answer: AssistantAnswer;
}

const VALIDATION_LABEL: Record<string, string | undefined> = {
  ok: 'All citations verified',
  downgraded: 'Some claims were downgraded after validation',
  abstained: 'The assistant abstained',
  unverified: 'Citations could not be fully verified',
};

/**
 * FR-6.2 / FR-6.4: the answer, the claim list and — when the model abstained —
 * an explicit "evidence insufficient" state listing what is missing. A blank box
 * is never an acceptable rendering.
 */
export function AnswerPanel({ answer }: AnswerPanelProps): JSX.Element {
  if (answer.abstained) {
    return (
      <Card
        title="Evidence insufficient"
        description="We could not answer this from the official material we hold."
      >
        <div
          role="status"
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-900"
        >
          <p className="font-semibold">We stopped rather than guess.</p>
          {answer.abstention_reason ? <p className="mt-1">{answer.abstention_reason}</p> : null}
        </div>

        {answer.missing_information.length > 0 ? (
          <div className="mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              What would resolve this
            </h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
              {answer.missing_information.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-700">
            No specific missing fact was identified. Try contacting the scholarship office, or ask about
            a different part of the programme.
          </p>
        )}

        {answer.follow_up_questions.length > 0 ? (
          <div className="mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Try asking</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
              {answer.follow_up_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {answer.evidence.length > 0 ? (
          <p className="mt-4 text-xs text-slate-600">
            {answer.evidence.length} excerpt{answer.evidence.length === 1 ? '' : 's'} were retrieved and
            reviewed before the assistant abstained.
          </p>
        ) : null}
      </Card>
    );
  }

  return (
    <Card title="Answer" description="Generated from retrieved official excerpts only.">
      {answer.validation_result ? (
        <p className="mb-3">
          <Badge
            tone={
              answer.validation_result.verdict === 'ok'
                ? 'emerald'
                : answer.validation_result.verdict === 'unverified'
                  ? 'amber'
                  : 'neutral'
            }
          >
            {VALIDATION_LABEL[answer.validation_result.verdict] ?? answer.validation_result.verdict}
          </Badge>
        </p>
      ) : null}

      <div className="whitespace-pre-line text-sm leading-relaxed text-slate-800">{answer.answer}</div>

      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Claims in this answer
        </h3>
        {answer.claims.length === 0 ? (
          <p className="mt-1 text-sm text-slate-600">
            The answer did not break into individual claims, so nothing can be cited.
          </p>
        ) : (
          <ol className="mt-2 space-y-2">
            {answer.claims.map((claim, index) => (
              <li key={`${index}-${claim.text}`} className="rounded-md border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="min-w-0 flex-1 text-sm text-slate-800">{claim.text}</p>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <ClaimChip
                      state={claim.claim_state ?? (claim.confidence === 'confirmed' ? 'confirmed' : 'needs_verification')}
                      size="sm"
                    />
                  </div>
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  Confidence: {claim.confidence === 'confirmed' ? 'confirmed' : 'uncertain'} · cited
                  evidence:{' '}
                  {claim.evidence_ids.length > 0 ? claim.evidence_ids.join(', ') : 'none'}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>

      {answer.follow_up_questions.length > 0 ? (
        <div className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Follow-up questions</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
            {answer.follow_up_questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-5 text-xs text-slate-500">
        {answer.created_at ? `Answered ${formatDateTime(answer.created_at)}` : 'Audited when a model is configured'}
        {answer.validation_result && !answer.validation_result.referential_ok
          ? ' · at least one citation could not be resolved and was downgraded'
          : ''}
      </p>
    </Card>
  );
}

export default AnswerPanel;
