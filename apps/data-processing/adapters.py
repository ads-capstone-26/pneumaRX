"""Translate existing MIMIC metadata into the portable dataset contract."""
from pathlib import Path

from pneumarx.contracts.dataset import DatasetDefinition
from pneumarx.shared.io import read_json, write_json
from pneumarx_data.mimic3_schema import TABLES
from pneumarx_data.mimic3_docs import MIMIC_III_TABLE_DOCS
from pneumarx_data.quality_checks import PRIMARY_KEYS, GENERIC_FKS, SPECIFIC_FKS


def mimic_definition(knowledge_dir=None):
    keys = dict(PRIMARY_KEYS)
    tables = {}
    for spec in TABLES.values():
        name = spec.table_name
        description, columns = MIMIC_III_TABLE_DOCS.get(name, ('', {}))
        tables[name] = {'description': description, 'required': name in {'patients', 'admissions'},
                        'primary_key': list(keys.get(name, ())),
                        'columns': {col.lower(): {'type': dtype, 'description': columns.get(col.lower(), '')}
                                    for col, dtype in spec.columns}}
    links = set()
    for name, table in tables.items():
        for column, (parent, parent_column) in GENERIC_FKS.items():
            if column in table['columns'] and name != parent:
                links.add((name, column, parent, parent_column))
    links.update(SPECIFIC_FKS)
    relationships = [dict(zip(('table','column','parent_table','parent_column'), link))
                     for link in sorted(links) if link[0] in tables and link[2] in tables
                     and link[1] in tables[link[0]]['columns'] and link[3] in tables[link[2]]['columns']]
    conventions = []
    if knowledge_dir:
        for rule in read_json(Path(knowledge_dir)/'mimic3_query_conventions.json')['conventions']:
            targets = sorted({t.split('.')[0] for t in rule.get('applies_to', [])} & set(tables))
            if targets:
                conventions.append({'id': rule['id'], 'rule': rule['rule'], 'tables': targets})
    terminology = {}
    for name, table, code, dictionary, label in [
        ('diagnosis','diagnoses_icd','icd9_code','d_icd_diagnoses','long_title'),
        ('procedure','procedures_icd','icd9_code','d_icd_procedures','long_title'),
        ('lab','labevents','itemid','d_labitems','label'),
        ('medication','prescriptions','drug',None,'drug')]:
        terminology[name] = {'event_table': table, 'code_column': code, 'label_column': label,
                             'dictionary': dictionary, 'dictionary_code_column': code if dictionary else None,
                             'description': name + ' codes/names recorded in ' + table}
    return DatasetDefinition.model_validate({'dataset':'mimic_iii','name':'MIMIC-III', 'private':True,
        'domain_notes':'MIMIC-III dates are shifted per patient. Do not infer a global current time. '
                       'ICD-9 codes are strings without decimal points. Prescriptions do not establish ingestion.',
        'tables':tables,'relationships':relationships,'conventions':conventions,'terminology':terminology,
        'capabilities':{'lab_results':{'description':'Patient laboratory measurements','tables':['labevents']},
                        'vital_signs':{'description':'Recorded ICU observations','tables':['chartevents']},
                        'actual_ingestion':{'description':'Actual medication ingestion is not recorded','supported':False}}})


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Export existing MIMIC metadata to a portable configuration.')
    parser.add_argument('--knowledge-dir', type=Path, help='Optional existing MIMIC query-convention snapshot')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    write_json(args.output, mimic_definition(args.knowledge_dir).model_dump())


if __name__ == '__main__':
    main()
