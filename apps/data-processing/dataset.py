"""Configuration-driven CSV loading and read-only DuckDB profiling. No model calls."""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from pneumarx.contracts.dataset import DatasetDefinition
from pneumarx.shared.io import write_json
from pneumarx_data.inventory import read_header


def q(name):
    return '"' + name.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def inventory(source, config):
    source = Path(source)
    if not source.is_dir():
        raise ValueError('Source directory does not exist')
    files = {}
    for path in source.iterdir():
        lower = path.name.lower()
        suffix = '.csv.gz' if lower.endswith('.csv.gz') else '.csv' if lower.endswith('.csv') else None
        if suffix:
            files.setdefault(lower[:-len(suffix)], []).append(path)
    checks = []
    for name, spec in config.tables.items():
        matches = files.get(name, [])
        status, path = 'absent', None
        if len(matches) > 1:
            raise ValueError(f'Ambiguous source files for {name}')
        if matches:
            path = matches[0]
            header = [s.strip().lower() for s in read_header(path)]
            if len(set(header)) != len(header) or set(header) != set(spec.columns):
                raise ValueError(f'CSV header does not match configuration: {name}')
            status = 'ready'
        elif spec.required:
            raise ValueError(f'Missing required CSV: {name}')
        checks.append({'table': name, 'status': status, 'path': str(path) if path else None})
    return {'dataset': config.dataset, 'checks': checks,
            'unconfigured_files': sorted(set(files) - set(config.tables))}


def load(source, target, config, tables=None, memory_limit=None, threads=None):
    """Strict parsing and transaction rollback preserve the old DB on any load error."""
    found = inventory(source, config)
    selected = tables if tables is not None else [c['table'] for c in found['checks'] if c['status'] == 'ready']
    ready = {c['table']: c['path'] for c in found['checks'] if c['status'] == 'ready'}
    if not selected or any(t not in ready for t in selected):
        raise ValueError('No loadable tables or invalid table selection')
    target = Path(target)
    if target.stem != config.dataset:
        raise ValueError('Database filename must match configured dataset name')
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.prepare-', dir=target.parent) as temp:
        build = Path(temp) / target.name if tables is None else target
        con = duckdb.connect(str(build))
        results = []
        try:
            if memory_limit:
                con.execute('SET memory_limit = ' + literal(memory_limit))
            if threads:
                con.execute(f'SET threads = {int(threads)}')
            con.execute('BEGIN')
            for name in selected:
                header = [s.strip().lower() for s in read_header(Path(ready[name]))]
                columns = '{' + ', '.join(literal(c) + ': ' + literal(config.tables[name].columns[c].type) for c in header) + '}'
                con.execute(f'CREATE OR REPLACE TABLE {q(name)} AS SELECT * FROM read_csv('
                            f'{literal(ready[name])}, header=true, auto_detect=false, '
                            f"delim=',', quote='\"', escape='\"', columns={columns}, ignore_errors=false)")
                count = con.execute(f'SELECT COUNT(*) FROM {q(name)}').fetchone()[0]
                results.append({'table': name, 'rows_loaded': count, 'status': 'ok'})
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            # DuckDB parse messages contain source values; do not expose them in reports.
            raise ValueError('CSV loading failed; check configured types and source formatting. No existing tables were replaced.') from None
        finally:
            con.close()
        if tables is None:
            if Path(str(target) + '.wal').exists():
                raise ValueError('Target has an active WAL; close its writer before rebuilding')
            os.replace(build, target)
    return {'dataset': config.dataset, 'tables': results}


def inspect_database(path, config):
    """Aggregate evidence stays local. Metadata-only knowledge is returned separately."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with duckdb.connect(str(path), read_only=True) as con:
        schema = {}
        for table, column, dtype in con.execute("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='main' ORDER BY table_name,ordinal_position").fetchall():
            schema.setdefault(table, {})[column] = dtype
        config.check_layout(schema)
        tables, checks = {}, []
        for name, definition in config.tables.items():
            if name not in schema:
                continue
            total = con.execute(f'SELECT COUNT(*) FROM {q(name)}').fetchone()[0]
            columns = {}
            for column, definition_col in definition.columns.items():
                nulls, distinct = con.execute(f'SELECT COUNT(*)-COUNT({q(column)}), APPROX_COUNT_DISTINCT({q(column)}) FROM {q(name)}').fetchone()
                actual_type = schema[name][column]
                columns[column] = {**definition_col.model_dump(), 'type': actual_type,
                                   'null_rows': nulls, 'approx_distinct': distinct}
                if actual_type != definition_col.type:
                    checks.append({'id': f'type.{name}.{column}', 'status': 'flag',
                                   'expected': definition_col.type, 'actual': actual_type})
            if definition.primary_key:
                keys = ','.join(q(k) for k in definition.primary_key)
                bad_null = ' OR '.join(q(k) + ' IS NULL' for k in definition.primary_key)
                null_keys = con.execute(f'SELECT COUNT(*) FROM {q(name)} WHERE {bad_null}').fetchone()[0]
                duplicate = con.execute(f'SELECT COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM {q(name)} GROUP BY {keys} HAVING COUNT(*)>1)').fetchone()[0]
                checks.append({'id': 'key.' + name, 'status': 'flag' if null_keys or duplicate else 'pass',
                               'null_keys': null_keys, 'duplicate_rows': duplicate})
            tables[name] = {'description': definition.description, 'grain': definition.grain,
                            'primary_key': definition.primary_key, 'row_count': total, 'columns': columns}
        for link in config.relationships:
            if link.table not in tables or link.parent_table not in tables:
                checks.append({'id': f'link.{link.table}.{link.column}', 'status': 'unavailable'})
                continue
            count = con.execute(f'SELECT COUNT(*) FROM {q(link.table)} c WHERE c.{q(link.column)} IS NOT NULL AND NOT EXISTS '
                                f'(SELECT 1 FROM {q(link.parent_table)} p WHERE p.{q(link.parent_column)}=c.{q(link.column)})').fetchone()[0]
            checks.append({'id': f'link.{link.table}.{link.column}', 'status': 'flag' if count else 'pass', 'unmatched_rows': count})
    capabilities = {key: {'description': cap.description,
                         'available': cap.supported and all(t in tables for t in cap.tables),
                         'missing_tables': [t for t in cap.tables if t not in tables]}
                    for key, cap in config.capabilities.items()}
    quality = {'dataset': config.dataset, 'checks': checks}
    profile = {'dataset': config.dataset, 'tables': tables, 'capabilities': capabilities,
               'relationships': [r.model_dump() for r in config.relationships]}
    # The config contains curated metadata, no sample rows or measured distributions.
    knowledge = config.model_dump()
    return quality, profile, knowledge


def run_configured(request):
    config = DatasetDefinition.load(request.dataset_config)
    stages = ['inventory', 'load', 'quality', 'profile'] if request.stage == 'all' else [request.stage]
    if any(s not in {'inventory', 'load', 'quality', 'profile', 'publish'} for s in stages):
        raise ValueError('Unknown preparation stage')
    artifacts, attention = {}, []
    inspected = None
    for stage in stages:
        if stage in {'inventory', 'load'}:
            if request.source_dir is None:
                raise ValueError('Source directory required')
            payload = inventory(request.source_dir, config) if stage == 'inventory' else load(
                request.source_dir, request.db_path, config, request.tables, request.memory_limit, request.threads)
        else:
            inspected = inspected or inspect_database(request.db_path, config)
            quality, profile, knowledge = inspected
            attention = [c['id'] for c in quality['checks'] if c['status'] != 'pass']
            if stage == 'quality':
                payload = quality
            elif stage == 'profile':
                payload = profile
            else:
                target = request.snapshot_dir
                write_json(target / 'dataset.json', knowledge)
                # A separate manifest keeps measured evidence out of runtime configuration.
                with open(request.db_path, 'rb') as stream:
                    db_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
                write_json(target / 'manifest.json', {'database_sha256': db_hash, 'dataset': config.dataset,
                    'config_sha256': hashlib.sha256(Path(request.dataset_config).read_bytes()).hexdigest()})
                payload = {'dataset_config': str(target / 'dataset.json'), 'manifest': str(target / 'manifest.json')}
        output = request.report_dir / f'{stage}.json'
        write_json(output, payload)
        artifacts[stage] = str(output)
    return {'version': '0.2', 'component': 'data-processing', 'dataset': config.dataset,
            'status': 'needs_attention' if attention else 'success', 'database': str(request.db_path),
            'artifacts': artifacts, 'issues': attention}
