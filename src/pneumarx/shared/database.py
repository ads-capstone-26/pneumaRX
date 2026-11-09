"""Local DuckDB adapter shared by grounding and execution. No server required."""
from pathlib import Path

import duckdb

from pneumarx.contracts.intent import ColumnInfo, TableInfo
from pneumarx.contracts.dataset import identifier


class DBAPI:
    def __init__(self, connection, database_path: Path | None = None):
        self.db = connection
        self.database_path = database_path

    def link_dataset_tables(self, user_id, chat_id, dataset_name):
        identifier(dataset_name)

    def execute_query(self, user_id, chat_id, sql, params=None):
        return self.db.execute(sql, params or []).fetchdf()

    def catalog(self, dataset_name):
        self.link_dataset_tables('', '', dataset_name)
        rows = self.db.execute('''SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = ? OR table_catalog = ?
            ORDER BY table_name, ordinal_position''', [dataset_name, dataset_name]).fetchall()
        tables = {}
        for name, column, dtype in rows:
            tables.setdefault(name, []).append(ColumnInfo(name=column, type=dtype))
        return [TableInfo(name=name, path=f'{dataset_name}."{name}"', columns=cols,
                          sample_rows=[]) for name, cols in tables.items()]


def connect_database(path, dataset_name="mimic_iii"):
    identifier(dataset_name)
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Database not found: {path}. Run data-processing load first.')
    db = duckdb.connect(str(path), read_only=True, config={'enable_external_access': 'false'})
    if db.execute('SELECT current_database()').fetchone()[0] != dataset_name:
        db.close()
        raise ValueError(f'Expected database catalog {dataset_name}; select the matching --dataset and database file.')
    return db
