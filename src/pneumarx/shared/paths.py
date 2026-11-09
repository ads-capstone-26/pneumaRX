import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get('PNEUMARX_ROOT', Path(__file__).resolve().parents[3])).resolve()
DEFAULT_DB = PROJECT_ROOT / 'data/mimic_iii/mimic_iii.db'
DEFAULT_RESULTS = PROJECT_ROOT / 'runs'
