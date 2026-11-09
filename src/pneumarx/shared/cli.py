"""Shared argument and output helpers; each app owns its own parser and execution."""
import json
from pathlib import Path
from .paths import DEFAULT_DB
from .io import write_json


def add_model_arguments(parser):
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--allow-private-llm', action='store_true')



def positive_int(value):
    import argparse
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def add_table_retrieval_arguments(parser):
    parser.add_argument('--table-retrieval', choices=['bm25', 'all'], default='bm25',
                        help='Schema candidates before LLM grounding (default: bm25)')
    parser.add_argument('--table-top-k', type=positive_int, default=5,
                        help='BM25 candidate count (default: 5; ignored in all mode)')


def finish(component, output, result, *, write=True):
    if write:
        write_json(output, result)
    summary = {'component': component, 'status': result.get('status', 'finished'), 'output': str(output)}
    print(json.dumps(summary, ensure_ascii=False))
    if result.get('status') == 'not_implemented':
        return 3
    return 0 if result.get('status') in {'success', 'ready', 'passed', 'completed', 'executed_unvalidated'} else 2


def failure(exc):
    print(json.dumps({'status': 'setup_failure', 'error_type': type(exc).__name__, 'reason': str(exc)}, ensure_ascii=False))
    return 1
