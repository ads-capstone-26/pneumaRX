"""Assemble components; intent-understanding owns and closes the shared local resources."""
from contextlib import contextmanager

from pneumarx_intent_understanding.session import preparation_session
from pneumarx_query_execution.planner import make_planner
from pneumarx_pipeline.main import Pipeline


@contextmanager
def live_runtime(db_path, *, env_file=None, model=None, allow_private_llm=False, reviewer=None,
                 table_retrieval="bm25", table_top_k=5, review_mode="hybrid", dataset_name="mimic_iii", dataset_config=None):
    with preparation_session(db_path, env_file=env_file, model=model,
                             allow_private_llm=allow_private_llm,
                             table_retrieval=table_retrieval, table_top_k=table_top_k, dataset_name=dataset_name, dataset_config=dataset_config) as (preparer, llm):
        planner = make_planner(llm)
        if reviewer is None and review_mode != 'pending':
            from pneumarx_result_validation.workflow import LightweightReviewer
            reviewer = LightweightReviewer(llm, mode=review_mode)
        yield Pipeline(preparer, preparer.db_api.db, planner, reviewer=reviewer, dataset=dataset_name,
                       repair=lambda spec, plan, error: planner(spec, plan, error)), llm
