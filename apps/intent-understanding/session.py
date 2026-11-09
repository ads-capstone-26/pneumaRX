"""Own the local DB, terminology client and model for intent-understanding."""
from contextlib import contextmanager
import logging
from pathlib import Path

from pneumarx.shared.config import Config
from pneumarx.shared.database import DBAPI, connect_database
from pneumarx.shared.llm import LanguageModelAPI, configured_llm


@contextmanager
def preparation_session(db_path, *, env_file=None, model=None, allow_private_llm=False,
                        table_retrieval="bm25", table_top_k=5, dataset_name="mimic_iii", dataset_config=None):
    if not allow_private_llm:
        raise PermissionError('Live model runs require --allow-private-llm for your approved endpoint.')
    from pneumarx_intent_understanding.main import IntentPreparer
    from pneumarx.contracts.dataset import DatasetDefinition
    definition = DatasetDefinition.load(dataset_config) if dataset_config else None
    if definition is not None and definition.dataset != dataset_name:
        raise ValueError("Dataset configuration does not match --dataset")
    config = Config(env_file, model)
    db = connect_database(db_path, dataset_name=dataset_name)
    llm = preparer = None
    try:
        llm = configured_llm(config)
        preparer = IntentPreparer('local', 'pipeline', config, logging.getLogger('pneumarx'),
                                  DBAPI(db, Path(db_path).resolve()), LanguageModelAPI(llm),
                                  allow_private_llm=True, sample_size=0,
                                  table_retrieval=table_retrieval, table_top_k=table_top_k, dataset_definition=definition)
        yield preparer, llm
    finally:
        if preparer is not None:
            preparer.umls.close()
        if llm is not None:
            llm.client.close()
        db.close()
