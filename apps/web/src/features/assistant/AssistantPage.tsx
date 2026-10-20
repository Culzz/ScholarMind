import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAsk } from '@/hooks/useAsk';
import { useScholarship } from '@/hooks/useScholarship';

import { AnswerPanel } from './AnswerPanel';
import { EvidencePanel } from './EvidencePanel';

const EXAMPLE_QUESTIONS = [
  'What is the deadline for this cycle and what does the official page say?',
  'Which documents do I need for the application?',
  'Is tuition fully covered, and which parts are conditional?',
  'What nationality is eligible for this scholarship?',
];

export function AssistantPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const scholarshipId = searchParams.get('scholarship');
  const scholarshipQuery = useScholarship(scholarshipId ?? undefined);
  const ask = useAsk();

  const [question, setQuestion] = useState('');

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    ask.mutate({
      question: trimmed,
      scholarship_id: scholarshipId ?? undefined,
    });
  };

  const answer = ask.data ?? null;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Assistant</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Answers are generated only from retrieved official excerpts. Every claim is cited, the
          snapshot time is shown, and the assistant says so when the evidence is not enough.
        </p>
      </header>

      <Card
        title="Ask a question"
        description={
          scholarshipQuery.data
            ? `Context: ${scholarshipQuery.data.scholarship.name}`
            : 'Ask about any scholarship in the corpus.'
        }
      >
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label htmlFor="question" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
              Your question
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={4}
              placeholder="What is the deadline for the 2027 cycle and which official source states it?"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" loading={ask.isPending} disabled={question.trim().length === 0}>
              Ask
            </Button>
            {scholarshipId ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setQuestion('')}
              >
                Clear question
              </Button>
            ) : null}
          </div>
        </form>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Examples</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => setQuestion(example)}
                  className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      {ask.isError ? (
        <ErrorState
          title="The assistant could not answer"
          message={ask.error instanceof Error ? ask.error.message : undefined}
          onRetry={() => void ask.reset()}
        />
      ) : null}

      <div aria-live="polite" className="space-y-4">
        {ask.isPending ? (
          <div className="space-y-3" role="status">
            <span className="sr-only">Searching the evidence…</span>
            <Skeleton className="h-40 w-full rounded-lg" />
            <Skeleton className="h-32 w-full rounded-lg" />
          </div>
        ) : null}

        {!ask.isPending && !answer && !ask.isError ? (
          <EmptyState
            title="No question asked yet"
            description="Ask about a deadline, a document list, a funding component or an eligibility rule and we will answer it with citations."
          />
        ) : null}

        {answer ? (
          <>
            <AnswerPanel answer={answer} />
            <EvidencePanel
              evidence={answer.evidence ?? []}
              conflicts={answer.conflicts ?? []}
              freshnessWarnings={answer.freshness_warnings ?? []}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}

export default AssistantPage;
