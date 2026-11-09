"""Deterministic fixture demonstration; this does not measure LLM accuracy."""
from contextlib import contextmanager
from copy import deepcopy

from pneumarx.contracts.intent import IntentSpec, Unanswerable
from pneumarx_pipeline.main import Pipeline
from pneumarx_query_execution.fixtures import synthetic_database
from pneumarx_query_execution.executor import load_spec, reference_planner


class FixturePreparer:
    def __init__(self, spec):
        self.spec = deepcopy(spec)

    def prepare(self, question, dataset, **kwargs):
        if question != self.spec['question']:
            return Unanswerable(question=question, dataset_name=dataset,
                                reason='Offline fixture supports only the example question; use live mode for other questions.')
        full = deepcopy(self.spec)
        for concept in full['concepts']:
            concept['confidence'] = 1.0
        full['reasoning_confidence_score'] = 1.0
        return IntentSpec.model_validate(full)


@contextmanager
def demo_runtime():
    spec = load_spec()
    db = synthetic_database(spec)
    try:
        # Fixture planner is explicitly selected; never a fallback for live calls.
        yield Pipeline(FixturePreparer(spec), db, lambda _: reference_planner(spec))
    finally:
        db.close()
