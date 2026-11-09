"""Profile for the existing six-table, fully synthetic capstone hospital dataset.

No MIMIC rules, patient samples, reference answers, or task-specific gold SQL.
The time anchor follows the supplied check.ipynb, rather than the wall clock.
"""
from dataclasses import replace
import re

from .mimic_profile import MimicProfile, CodeSystem
from .code_lookup import CodeLookup, CodeCandidates

TABLE_DOCS = {
    'patients': ('Patient demographics, one row per patient.', {
        'patient_id': 'Unique patient identifier', 'age': 'Age in years, already stored; do not derive it from dates',
        'gender': 'Gender', 'created_at': 'Record creation date, not birth date',
        'primary_care_physician_id': 'Primary care physician identifier'}),
    'admissions': ('Hospital encounters, multiple admissions per patient.', {
        'admission_id': 'Unique admission identifier', 'patient_id': 'Patient identifier',
        'admission_date': 'Admission date', 'discharge_date': 'Discharge date; NULL for an ongoing admission',
        'ward': 'Hospital ward', 'admission_type': 'Admission type',
        'attending_physician_id': 'Attending physician identifier'}),
    'diagnoses': ('Diagnoses linking patients and optionally admissions to ICD-10 codes.', {
        'diagnosis_id': 'Unique diagnosis record identifier', 'patient_id': 'Patient identifier',
        'admission_id': 'Admission identifier; can be NULL', 'icd10_code': 'ICD-10 code as text WITH its dot',
        'description': 'Description of this ICD-10 diagnosis', 'primary_flag': '1 marks a primary diagnosis',
        'diagnosed_date': 'Date diagnosis was recorded'}),
    'medications': ('Medication prescriptions. A patient can have multiple records for the same drug.', {
        'medication_id': 'Unique prescription record identifier', 'patient_id': 'Patient identifier',
        'drug_name': 'Drug name as text', 'start_date': 'Prescription start date',
        'end_date': 'Prescription end date; NULL means no recorded end',
        'dosage': 'Prescribed dosage', 'frequency': 'Dose frequency',
        'prescribing_physician_id': 'Prescribing physician identifier'}),
    'lab_results': ('Longitudinal laboratory measurements; multiple tests per patient.', {
        'lab_id': 'Unique laboratory record identifier', 'patient_id': 'Patient identifier',
        'test_name': 'Laboratory test name, such as eGFR', 'result_value': 'Measured numeric value',
        'unit': 'Measurement unit', 'test_date': 'Measurement date',
        'reference_range': 'Recorded reference range', 'abnormal_flag': '1 marks an abnormal result'}),
    'physicians': ('Physician reference directory.', {
        'physician_id': 'Unique physician identifier', 'name': 'Physician name',
        'specialty': 'Clinical specialty', 'department': 'Department', 'npi': 'Provider identifier'}),
}

HOSPITAL = MimicProfile(
    name='Capstone synthetic hospital EHR', private=False, catalog=True,
    code_systems={
        'diagnosis': CodeSystem('diagnosis', ('diagnoses',), ('icd10_code',), None, (),
                               'description', (), 'ICD-10 diagnosis, code and description in diagnoses'),
        'medication': CodeSystem('medication', ('medications',), ('drug_name',), None, (),
                                'drug_name', (), 'Drug name stored directly in medications'),
        'lab': CodeSystem('lab', ('lab_results',), ('test_name',), None, (),
                         'test_name', (), 'Laboratory test name stored directly in lab_results'),
    },
    key_columns=('admission_id', 'patient_id'), table_docs=TABLE_DOCS,
    domain_notes='''This is the synthetic hospital EHR, not MIMIC. Use its actual identifiers,
ICD-10 codes with dots, direct drug/test names and date columns. There are no MIMIC
ICD-9 dictionaries or subject_id/hadm_id columns. Laboratory result_value is the
measurement; lab_id identifies a record, not a test type. Join diagnosis to an
encounter by admission_id when the request is encounter-specific. Do not interpret
created_at as date of birth. A missing laboratory test must not be invented.
Resolve genuine ambiguity explicitly in the IntentSpec; do not treat the user's
clinical rationale as an independently verified medical guideline.''',
    knowledge_source='Existing hospital CSV schema/metadata and check.ipynb time-anchor convention',
)


def bind_reference_date(profile, db):
    anchor = db.execute('''SELECT GREATEST(
        (SELECT MAX(admission_date) FROM hospital.admissions),
        (SELECT MAX(start_date) FROM hospital.medications),
        (SELECT MAX(diagnosed_date) FROM hospital.diagnoses),
        (SELECT MAX(test_date) FROM hospital.lab_results))''').fetchone()[0]
    if anchor is None:
        raise ValueError('Hospital dataset has no reference date')
    rule = {'id': 'hospital_reference_date', 'tables': set(TABLE_DOCS),
            'rule': f'For this frozen dataset, current_time/today is {anchor.isoformat()}, '
                    'the maximum of admission_date, medication start_date, diagnosed_date and test_date. '
                    'Use this fixed reference rather than CURRENT_DATE. State any additional assumptions.'}
    return replace(profile, conventions=(rule,))


class HospitalCodeLookup(CodeLookup):
    """Ground to actual ICD-10 labels and direct drug/lab names, without ICD-9 dictionaries."""
    def lookup(self, dataset_name, profile, concepts, available_tables, question=''):
        candidates = []
        for concept in concepts:
            system = profile.code_systems.get(str(concept.get('code_system') or ''))
            term = str(concept.get('term') or '').strip()
            if system is None or not term:
                continue
            table, column = system.event_tables[0], system.event_code_columns[0]
            item = CodeCandidates(term=term, code_system=system.name, event_table=table,
                                  code_columns=system.event_code_columns, meaning=system.description)
            if table not in available_tables:
                item.available = False
                candidates.append(item)
                continue
            terms = list(dict.fromkeys([term] + [str(t) for t in concept.get('lookup_terms', []) if t]))
            label = system.label_column
            # The interpreter may expand an abbreviation that this small dataset
            # stores verbatim (e.g. eGFR). Preserve real names explicitly present
            # in the original question; never infer a patient result or a gold code.
            vocabulary = self._execute(f'SELECT DISTINCT "{column}" AS code, "{label}" AS label '
                                       f'FROM {dataset_name}."{table}"', [])
            for row in vocabulary:
                for name in {str(row['code'] or ''), str(row['label'] or '')}:
                    if name and re.search(r'(?<![a-z0-9])' + re.escape(name) + r'(?![a-z0-9])', question, re.I):
                        terms.append(name)
            terms = list(dict.fromkeys(terms))
            patterns = [f'%{t}%' for t in terms]
            clause = ' OR '.join([f'"{column}" ILIKE ? OR "{label}" ILIKE ?'] * len(patterns))
            params = [p for pattern in patterns for p in (pattern, pattern)]
            rows = self._execute(f'SELECT DISTINCT "{column}" AS code, "{label}" AS label '
                                 f'FROM {dataset_name}."{table}" WHERE {clause} ORDER BY 1 LIMIT 40', params)
            # Descriptions can put qualifiers in a different order from the
            # question ("stage 3 chronic kidney disease" vs "... disease, stage 3").
            # Offer lexical label matches for grounding; the LLM still chooses
            # the actual codes and must honor qualifiers. No clinical codes are
            # hard-coded or inferred from reference answers.
            stop = {'with','without','that','this','most','recent','have','current','currently',
                    'stage','worse','above','below','value','values','diagnosis','diagnoses'}
            words = lambda text: {w for w in re.findall(r'[a-z]+', text.lower()) if len(w)>=4 and w not in stop}
            query_words = words(' '.join(terms))
            lexical = [(len(query_words & words(str(row['label']))), row) for row in vocabulary]
            known = {row['code'] for row in rows}
            for overlap, row in sorted(lexical,key=lambda pair:(-pair[0],str(pair[1]['code']))):
                if overlap >= 2 and row['code'] not in known:
                    rows.append(row); known.add(row['code'])
            item.matches, item.search_terms = rows[:40], terms
            item.truncated = len(rows) >= 40
            candidates.append(item)
        return candidates
