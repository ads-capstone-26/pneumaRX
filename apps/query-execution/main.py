"""query-execution: validate the contract, plan SQL and execute with bounded repair."""
import argparse
from pathlib import Path

from pneumarx.contracts.intent import IntentSpec
from pneumarx.shared.cli import add_model_arguments, finish, failure
from pneumarx.shared.io import read_json
from pneumarx_query_execution.executor import load_spec, run_figure3, reference_planner


def run(spec, db, planner, repair=None):
    """Execute a full typed IntentSpec or its compact planner view."""
    view = spec.to_figure3_view(max_sample_rows=0) if isinstance(spec, IntentSpec) else spec
    return run_figure3(view, db, planner, repair)


def execute_request(args):
    full = read_json(args.input)
    if args.offline:
        from pneumarx_query_execution.fixtures import synthetic_database
        if full != load_spec():
            raise ValueError('Offline mode supports only examples/intent_spec.json')
        db = synthetic_database(full)
        try:
            outcome = run(full, db, reference_planner)
        finally:
            db.close()
    else:
        spec = IntentSpec.model_validate(full)
        if not args.allow_private_llm:
            raise PermissionError('Live MIMIC runs require --allow-private-llm')
        from pneumarx.shared.database import connect_database
        from pneumarx.shared.config import Config
        from pneumarx.shared.llm import configured_llm
        from pneumarx_query_execution.planner import make_planner
        db, llm = connect_database(args.db), None
        try:
            llm = configured_llm(Config(args.env_file, args.model))
            planner = make_planner(llm)
            view = spec.to_figure3_view(max_sample_rows=0)
            outcome = run(spec, db, planner,
                          repair=lambda plan, error: planner(view, plan, error))
            outcome.update(model=llm.config.LLM_PATH,
                           usage={'input_tokens': llm.total_input_tokens,
                                  'output_tokens': llm.total_output_tokens})
        finally:
            if llm:
                llm.client.close()
            db.close()
    outcome.update(question=full['question'], intent_spec=full, answer_validated=False)
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_model_arguments(parser)
    parser.add_argument('--input', type=Path, required=True, help='Ready IntentSpec JSON')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline', action='store_true', help='Exact synthetic fixture only')
    args = parser.parse_args(argv)
    try:
        return finish('query-execution', args.output, execute_request(args))
    except Exception as exc:
        return failure(exc)


if __name__ == '__main__':
    raise SystemExit(main())
