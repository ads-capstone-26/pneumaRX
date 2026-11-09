"""Main orchestration; component implementations are injectable for tests."""
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter

from pneumarx.contracts.intent import AdjustmentRequest, IntentSpec
from pneumarx.contracts.results import ReviewInput, ReviewResult
from pneumarx_query_execution.executor import run_figure3
from pneumarx_result_validation.main import PendingReviewer

def run_workflow(question, preparer, db, planner, *, dataset='mimic_iii',
                 interactive=True, repair=None):
    """Real typed handoff; one upstream adjustment, separate SQL repair budget.

    repair(spec, plan, error) receives the latest Figure 2 output, never the old
    contract after an adjustment. Non-ready Figure 2 results stop before SQL.
    """
    history = []
    retrieval_history = []
    adjustment = None
    execution_history = []
    for used in range(2):
        try:
            result = preparer.prepare(question, dataset, interactive=interactive,
                                      use_memory=False, adjustment_request=adjustment)
        except Exception as exc:
            return {'status': 'figure2_failure', 'reason': type(exc).__name__,
                    'question': question, 'figure2_history': history, 'retrieval_history': retrieval_history,
                    'upstream_adjustments_used': used}
        context = getattr(preparer, "last_context", None)
        retrieval_history.append(deepcopy(getattr(context, "retrieval", {})))
        full = result.model_dump(mode='json')
        history.append(full)
        if not isinstance(result, IntentSpec):
            return {'status': result.status, 'question': question,
                    'figure2_result': full, 'figure2_history': history, 'retrieval_history': retrieval_history,
                    'upstream_adjustments_used': used}
        spec = result.to_figure3_view(max_sample_rows=0)
        repair_plan = (lambda plan, error: repair(spec, plan, error)) if repair else None
        outcome = run_figure3(spec, db, planner, repair_plan)
        execution_history.append(deepcopy(outcome))
        outcome.update(execution_history=deepcopy(execution_history), question=question, intent_spec=full, figure3_input=spec,
                       figure2_history=deepcopy(history), retrieval_history=deepcopy(retrieval_history), upstream_adjustments_used=used)
        if outcome['status'] != 'needs_information_adjustment':
            return outcome
        if used == 1:
            outcome['status'] = 'execution_failure'
            outcome['failure_kind'] = 'upstream_adjustment_limit'
            outcome['requested_action'] = 'stop: upstream adjustment limit reached'
            return outcome
        adjustment = AdjustmentRequest(reason=outcome['reason'])


class Pipeline:
    def __init__(self, preparer, db, planner, *, repair=None, reviewer=None, dataset="mimic_iii"):
        self.preparer, self.db, self.planner = preparer, db, planner
        self.repair = repair
        self.dataset = dataset
        self.reviewer = reviewer if reviewer is not None else PendingReviewer()

    def run(self, question: str, *, interactive=True):
        # Each new benchmark question is independent; reuse occurs only inside
        # the bounded upstream-adjustment loop for this question.
        if hasattr(self.preparer, 'last_context'):
            self.preparer.last_context = None
        started = perf_counter()
        outcome = run_workflow(question, self.preparer, self.db, self.planner,
                               interactive=interactive, repair=self.repair, dataset=self.dataset)
        outcome.update(version='0.1', answer_validated=False,
                       created_at_utc=datetime.now(timezone.utc).isoformat())
        outcome['configuration'] = {'interactive': interactive, 'memory_enabled': False,
                                    'max_upstream_adjustments': 1,
                                    'max_sql_repairs_per_execution': 1}
        outcome['execution_status'] = outcome['status']
        if outcome['status'] == 'success':
            try:
                review_input = ReviewInput(question=question, intent_spec=outcome['intent_spec'],
                                           query_plan=outcome['query_plan'],
                                           execution_result=outcome['execution_result'])
                review = ReviewResult.model_validate(self.reviewer.review(review_input))
                outcome['review'] = review.model_dump(mode='json')
                from pneumarx_result_validation.workflow import presentation
                outcome['presentation'] = presentation(review, outcome['execution_result'])
                outcome['validation_scope'] = review.scope
                outcome['status'] = {
                    'not_implemented': 'executed_unvalidated',
                    'passed': 'completed',
                    'error_detected': 'validation_error',
                    'insufficient_evidence': 'insufficient_evidence',
                }[review.status]
                outcome['answer_validated'] = review.status == 'passed'
            except Exception as exc:
                outcome['presentation'] = {'disposition': 'withheld', 'result': None,
                                           'explanation': 'Result review failed; no validated answer is available.'}
                outcome.update(status='validation_failure',
                               reason=f'Reviewer failed: {type(exc).__name__}')
        outcome['elapsed_seconds'] = round(perf_counter() - started, 3)
        return outcome


def main(argv=None):
    import argparse
    from pathlib import Path
    from pneumarx.shared.cli import add_table_retrieval_arguments, add_model_arguments, finish, failure

    parser = argparse.ArgumentParser(description='Coordinate intent-understanding → query-execution → result-validation.')
    add_model_arguments(parser)
    parser.add_argument('--dataset', default='mimic_iii')
    parser.add_argument('--dataset-config', type=Path)
    add_table_retrieval_arguments(parser)
    parser.add_argument('--reviewer', choices=['sanity', 'llm', 'hybrid', 'pending'], default=None,
                        help='Live default: hybrid; offline default: pending')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--question')
    choice.add_argument('--demo', action='store_true', help='Use the deterministic synthetic fixture')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--non-interactive', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.demo:
            if args.reviewer in {'llm', 'hybrid'}:
                raise ValueError('Offline fixtures do not call models; use --reviewer sanity or pending')
            from pneumarx_pipeline.demo import demo_runtime
            from pneumarx_query_execution.executor import load_spec
            with demo_runtime() as pipeline:
                if args.reviewer == 'sanity':
                    from pneumarx_result_validation.workflow import LightweightReviewer
                    pipeline.reviewer = LightweightReviewer(mode='sanity')
                outcome = pipeline.run(load_spec()['question'])
            outcome['mode'] = 'synthetic_offline_fixture'
        else:
            from pneumarx_pipeline.runtime import live_runtime
            with live_runtime(args.db, env_file=args.env_file, model=args.model, dataset_name=args.dataset, dataset_config=args.dataset_config,
                              allow_private_llm=args.allow_private_llm,
                              table_retrieval=args.table_retrieval, table_top_k=args.table_top_k,
                              review_mode=args.reviewer or 'hybrid') as (pipeline, llm):
                outcome = pipeline.run(args.question, interactive=not args.non_interactive)
                outcome.update(model=llm.config.LLM_PATH,
                               usage={'input_tokens': llm.total_input_tokens,
                                      'output_tokens': llm.total_output_tokens})
        return finish('pipeline', args.output, outcome)
    except Exception as exc:
        return failure(exc)


if __name__ == '__main__':
    raise SystemExit(main())
