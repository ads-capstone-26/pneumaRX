"""Figure 2 JSON -> QueryPlan -> DuckDB -> ExecutionResult.

Offline reference planner supports the supplied contract only. Pass another
planner callable to run_figure3 to integrate a model or a different planner.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import duckdb

from pneumarx.shared.paths import PROJECT_ROOT
SPEC_PATH = PROJECT_ROOT / 'examples/intent_spec.json'
REFERENCE_HASH = '7d90834a7f98af2924feac1930a1422371e9ba9056ba4863ce4779708933e9be'


class InformationRequired(ValueError):
    pass


class UnsupportedIntent(ValueError):
    pass


class ParameterBindingError(ValueError):
    """Structured parameter mismatch, independent of DuckDB error wording."""
    pass


def load_spec(path=SPEC_PATH):
    return json.loads(Path(path).read_text())


def identifier(value):
    if not isinstance(value, str) or not value.isidentifier():
        raise InformationRequired(f'Invalid identifier: {value!r}')
    return '"' + value + '"'


def expand_table_metadata(tables):
    """Read legacy compact tables without borrowing another table's semantics.

    New IntentSpec views list every table separately. Historical views may place
    names/paths under same_layout_tables; expand them before validation/planning.
    Only structural columns are inherited, never descriptions or sample rows.
    """
    expanded = []
    names = set()
    for raw in tables:
        table = deepcopy(raw)
        members = table.pop('same_layout_tables', [])
        if not isinstance(members, list):
            raise InformationRequired('Invalid same_layout_tables metadata')
        entries = [table]
        for member in members:
            if not isinstance(member, dict) or 'same_layout_tables' in member:
                raise InformationRequired('Invalid same-layout member metadata')
            if not isinstance(member.get('name'), str) or not isinstance(member.get('path'), str):
                raise InformationRequired('Same-layout members require a name and physical path')
            entries.append({
                **deepcopy(member),
                'columns': deepcopy(member['columns']) if 'columns' in member else [
                    {'name': c['name'], 'type': c['type']} for c in table['columns']],
                'description': member.get('description', ''),
                'sample_rows': deepcopy(member.get('sample_rows', [])),
            })
        for entry in entries:
            if entry['name'] in names:
                raise InformationRequired('Duplicate table metadata')
            names.add(entry['name'])
            expanded.append(entry)
    return expanded


def validate_spec(spec, db):
    for field in ('question', 'tables', 'required_tables', 'schema_mapping',
                  'output_spec', 'concepts'):
        if not spec.get(field):
            raise InformationRequired(f'Missing {field}')
    for field in ('join_paths', 'assumptions'):
        if field not in spec:
            raise InformationRequired(f'Missing {field}')
    if spec['output_spec'].get('answer_type') not in {'number', 'string', 'boolean', 'list', 'table'}:
        raise UnsupportedIntent('Unsupported output answer_type')
    tables = {t['name']: t for t in expand_table_metadata(spec['tables'])}
    for name in spec['required_tables']:
        if name not in tables or name not in spec['schema_mapping']:
            raise InformationRequired(f'Missing metadata/mapping for {name}')
        table = tables[name]
        path = identifier(spec['dataset_name']) + '.' + identifier(name)
        if table['path'] != path and table['path'] != spec['dataset_name'] + '.' + identifier(name):
            raise InformationRequired(f'Unsupported physical path for {name}')
        actual = dict((r[0], r[1]) for r in db.execute('DESCRIBE ' + path).fetchall())
        declared = {c['name']: c['type'] for c in table['columns']}
        if any(actual.get(k) != v for k, v in declared.items()):
            raise InformationRequired(f'Physical schema differs for {name}')
        if not set(spec['schema_mapping'][name].values()) <= set(declared):
            raise InformationRequired(f'Mapped columns missing for {name}')
    for join in spec['join_paths']:
        for side in ('left', 'right'):
            table = tables.get(join[side + '_table'])
            if table is None or join[side + '_column'] not in {c['name'] for c in table['columns']}:
                raise InformationRequired('Invalid join path')


def reference_planner(spec):
    # Exact contract guard: never silently apply this reference SQL to a new intent.
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    if digest != REFERENCE_HASH:
        raise UnsupportedIntent('Offline reference supports only the supplied HF contract; use a model planner for other inputs.')
    concepts = {c.get('column'): c for c in spec['concepts'] if 'column' in c}
    return {
        'planner': 'offline_reference', 'dialect': 'duckdb',
        'steps': ['Select admissions with any matching HF diagnosis',
                  'Count distinct admissions and in-hospital deaths',
                  'Return 100 * deaths / admissions; NULL for an empty cohort'],
        'sql': '''WITH cohort AS (
  SELECT a.hadm_id, a.hospital_expire_flag
  FROM mimic_iii.admissions a
  WHERE EXISTS (SELECT 1 FROM mimic_iii.diagnoses_icd d
                WHERE d.hadm_id = a.hadm_id AND d.icd9_code LIKE ?)
)
SELECT 100.0 * COUNT(DISTINCT CASE WHEN hospital_expire_flag = ? THEN hadm_id END)
       / NULLIF(COUNT(DISTINCT hadm_id), 0) AS answer
FROM cohort''',
        'parameters': [concepts['icd9_code']['filter_values'][0],
                       concepts['hospital_expire_flag']['filter_values'][0]],
    }


def json_value(value):
    from datetime import date, datetime, time
    from decimal import Decimal
    from uuid import UUID
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    return value


def execute_plan(db, plan, repair=None, max_repairs=1, *, answer_type='number', preview_limit=100):
    if max_repairs < 0:
        raise ValueError('max_repairs must be non-negative')
    plan = deepcopy(plan)
    attempts = []
    for index in range(max_repairs + 1):
        try:
            if not isinstance(plan, dict):
                raise ValueError('Expected a QueryPlan object')
            if plan.get('dialect') != 'duckdb' or not isinstance(plan.get('parameters'), list):
                raise ValueError('Expected DuckDB plan with parameter list')
            statements = db.extract_statements(plan['sql'])
            if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
                raise ValueError('Plan must contain one SELECT statement')
            expected_parameters = len(statements[0].named_parameters)
            if len(plan['parameters']) != expected_parameters:
                raise ParameterBindingError(f'Expected {expected_parameters} parameters; received {len(plan["parameters"])}')
            cursor = db.execute(plan['sql'], plan['parameters'])
            schema = [{'name': c[0], 'type': str(c[1])} for c in cursor.description]
            names = [c['name'] for c in schema]
            if len(set(names)) != len(names):
                raise ValueError('Result columns require unique aliases')
            rows = cursor.fetchall()
            scalar = answer_type in {'number', 'string', 'boolean'}
            value = None
            if scalar:
                if len(schema) != 1 or len(rows) != 1:
                    raise ValueError('Expected one scalar result')
                value = rows[0][0]
                from decimal import Decimal
                valid = {'number': isinstance(value, (int, float, Decimal)) and not isinstance(value, bool),
                         'string': isinstance(value, str), 'boolean': isinstance(value, bool)}
                if value is not None and not valid[answer_type]:
                    raise ValueError('Result does not match requested answer_type')
                if answer_type == 'number' and value is not None:
                    value = float(value)
            elif answer_type == 'list' and len(schema) != 1:
                raise ValueError('List output requires one column')
            records = [dict(zip(names, [json_value(v) for v in row])) for row in rows]
            result = {'schema': schema, 'row_count': len(rows), 'storage': 'inline',
                      'result_reference': '#/execution_result/rows', 'rows': records,
                      'preview': records[:preview_limit]}
            if scalar:
                result['answer'] = json_value(value)
            attempts.append({'attempt': index + 1, 'status': 'success'})
            return {'status': 'success', 'query_plan': plan, 'attempts': attempts,
                    'execution_result': result}
        except (duckdb.Error, ValueError, KeyError, TypeError) as exc:
            attempts.append({'attempt': index + 1, 'error_type': type(exc).__name__, 'error': str(exc)})
            repairable = isinstance(exc, (duckdb.ParserException, duckdb.BinderException,
                                          duckdb.CatalogException, ParameterBindingError))
            if repairable and repair and index < max_repairs:
                try:
                    plan = repair(deepcopy(plan), str(exc))
                    if not isinstance(plan, dict):
                        raise ValueError('Repair must return a plan object')
                    continue
                except InformationRequired as repair_exc:
                    return {'status': 'needs_information_adjustment', 'reason': str(repair_exc),
                            'query_plan': plan, 'attempts': attempts,
                            'requested_action': 'Return an updated Figure 2 IntentSpec'}
                except Exception as repair_exc:
                    return {'status': 'execution_failure', 'reason': 'Repair failed: ' + type(repair_exc).__name__, 'attempts': attempts}
            return {'status': 'execution_failure', 'reason': str(exc), 'attempts': attempts}


def run_figure3(spec, db, planner=reference_planner, repair=None):
    try:
        spec = deepcopy(spec)
        if spec.get('tables'):
            spec['tables'] = expand_table_metadata(spec['tables'])
        validate_spec(spec, db)
        plan = planner(deepcopy(spec))
    except InformationRequired as exc:
        return {'status': 'needs_information_adjustment', 'reason': str(exc), 'requested_action': 'Return an updated Figure 2 IntentSpec'}
    except UnsupportedIntent as exc:
        return {'status': 'unsupported_intent', 'reason': str(exc)}
    except duckdb.Error as exc:
        return {'status': 'execution_failure', 'reason': str(exc)}
    except Exception as exc:
        return {'status': 'planning_failure', 'reason': type(exc).__name__}
    outcome = execute_plan(db, plan, repair, answer_type=spec['output_spec']['answer_type'])
    if outcome['status'] == 'success':
        outcome['execution_result']['unit'] = spec['output_spec'].get('unit')
        outcome['assumptions'] = deepcopy(spec['assumptions'])
        outcome['query_conventions'] = deepcopy(spec.get('query_conventions', []))
    return outcome


def run_with_upstream(spec, db, planner, repair=None, adjust=None):
    """Optional Figure 2 callback; at most one upstream adjustment per request.

    adjust(spec, issue) -> updated IntentSpec. repair(spec, plan, error) -> plan.
    SQL repair budgets are separate from the upstream adjustment budget.
    """
    current = deepcopy(spec)
    for used in range(2):
        repair_plan = (lambda plan, error: repair(current, plan, error)) if repair else None
        outcome = run_figure3(current, db, planner, repair_plan)
        outcome['upstream_adjustments_used'] = used
        if outcome['status'] != 'needs_information_adjustment' or adjust is None:
            return outcome
        if used == 1:
            outcome['status'] = 'execution_failure'
            outcome['failure_kind'] = 'upstream_adjustment_limit'
            outcome['requested_action'] = 'stop: upstream adjustment limit reached'
            return outcome
        try:
            current = adjust(deepcopy(current), deepcopy(outcome))
            if not isinstance(current, dict):
                raise ValueError('Figure 2 must return an IntentSpec object')
        except Exception as exc:
            return {'status': 'upstream_failure', 'reason': type(exc).__name__,
                    'upstream_adjustments_used': 1}
