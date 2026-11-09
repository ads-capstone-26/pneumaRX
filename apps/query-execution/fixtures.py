import duckdb
from pneumarx_query_execution.executor import identifier

def synthetic_database(spec):
    """All records are fictional. Build complete schemas from the supplied JSON."""
    db = duckdb.connect(':memory:', config={'enable_external_access': 'false'})
    db.execute('CREATE SCHEMA mimic_iii')
    allowed = {'INTEGER', 'BIGINT', 'SMALLINT', 'DOUBLE', 'VARCHAR', 'TIMESTAMP'}
    for table in spec['tables']:
        columns = []
        for col in table['columns']:
            if col['type'] not in allowed:
                raise ValueError('Unsupported fixture type')
            columns.append(identifier(col['name']) + ' ' + col['type'])
        db.execute('CREATE TABLE mimic_iii.' + identifier(table['name']) + ' (' + ', '.join(columns) + ')')
    # 101, 102, 103, 104 qualify; only 101 died. 101 and 102 are the same patient.
    db.executemany('INSERT INTO mimic_iii.admissions (hadm_id, subject_id, hospital_expire_flag, admission_type) VALUES (?, ?, ?, ?)',
                   [(101, 1, 1, 'EMERGENCY'), (102, 1, 0, 'ELECTIVE'),
                    (103, 2, 0, 'NEWBORN'), (104, 3, 0, 'EMERGENCY'),
                    (105, 4, 1, 'EMERGENCY'), (106, 5, 1, 'EMERGENCY')])
    db.executemany('INSERT INTO mimic_iii.diagnoses_icd (hadm_id, icd9_code, seq_num) VALUES (?, ?, ?)',
                   [(101, '4280', 1), (101, '4280', 2), (101, '4281', 3),
                    (102, '4289', 2), (103, '42820', 1), (104, '428', 3),
                    (105, '25000', 1), (999, '4280', 1), (None, '4280', 1)])
    # A negative duration remains eligible for counts, as the supplied conventions require.
    db.execute("UPDATE mimic_iii.admissions SET admittime='2100-01-02', dischtime='2100-01-01' WHERE hadm_id=104")
    return db
