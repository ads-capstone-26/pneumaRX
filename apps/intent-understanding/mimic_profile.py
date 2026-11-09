"""
Domain knowledge about MIMIC-III v1.4 used by Figure 2: identifier semantics,
join keys, event-table -> dictionary links, data conventions, and table and
column descriptions paraphrased from the public documentation
(https://mimic.mit.edu/docs/iii/tables/), not from the data.

Datasets named mimic_iii* (or mimic3*) get this profile; MIMIC-III is
credentialed, so the profile is "private".

When Figure 1's shared files are present (docs/mimic3/, written by
apps/data-processing/main.py publish), they take precedence: table and column
descriptions and column roles come from mimic3_schema_profile.json, and the query
conventions from mimic3_query_conventions.json. Only descriptive text and rule text
are used; the measured counts, percentages and category value frequencies in those
files never reach a prompt. The built-in descriptions below are the fallback.

A private profile keeps patient-level data out of LLM prompts: no sample rows
and no usage counts (see IntentPreparer and CodeLookup).
"""
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from pneumarx.contracts.intent import JoinPath


@dataclass(frozen=True)
class CodeSystem:
    """How a kind of clinical concept is coded."""

    name: str  # e.g. "diagnosis", "lab", "icu_item", "medication", "organism"
    event_tables: tuple[str, ...]  # tables whose rows reference the code (primary first)
    event_code_columns: tuple[str, ...]  # code column(s) in the event tables
    dictionary: str | None  # dictionary table, or None for free text
    dictionary_code_columns: tuple[str, ...]
    label_column: str  # human-readable name (in the dictionary, or the event table)
    umls_sources: tuple[str, ...]  # UMLS vocabularies that describe the same codes
    description: str = ""  # shown to the S2 interpreter


@dataclass(frozen=True)
class MimicProfile:
    name: str
    code_systems: dict[str, CodeSystem]
    key_columns: tuple[str, ...]  # most specific first
    domain_notes: str
    private: bool = False  # credentialed data: no patient-level values in prompts
    catalog: bool = False  # small fixed schema: every table is a candidate (no index needed)
    table_docs: dict[str, tuple[str, dict[str, str]]] = field(default_factory=dict)
    # Figure 1 query conventions: {"id", "rule", "tables"} (tables the rule applies to)
    conventions: tuple[dict, ...] = ()
    knowledge_source: str = "built-in documentation"
    # Tables that add nothing when only these key columns are used and another
    # required table carries them, e.g. patients used just for subject_id
    key_only_tables: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def code_columns(self) -> set[str]:
        return {column for system in self.code_systems.values() for column in system.event_code_columns}

    def key_join_paths(self, columns_by_table: dict[str, set[str]], tables: list[str]) -> list[JoinPath]:
        """Joins between the given tables on the most specific shared key, plus dictionary links."""
        paths: list[JoinPath] = []
        for i, left in enumerate(tables):
            for right in tables[i + 1:]:
                shared = [key for key in self.key_columns if key in columns_by_table.get(left, set())
                          and key in columns_by_table.get(right, set())]
                if shared:
                    paths.append(JoinPath(left_table=left, left_column=shared[0],
                                          right_table=right, right_column=shared[0], score=1.0))
        for system in self.code_systems.values():
            if system.dictionary is None or system.dictionary not in tables:
                continue
            for event_table in system.event_tables:
                if event_table in tables:
                    for event_column, dict_column in zip(system.event_code_columns, system.dictionary_code_columns):
                        paths.append(JoinPath(left_table=event_table, left_column=event_column,
                                              right_table=system.dictionary, right_column=dict_column, score=1.0))
        return paths

    def conventions_for(self, tables: list[str] | set[str]) -> list[dict[str, str]]:
        """Conventions that apply to any of the given tables, as {"id", "rule"}."""
        wanted = set(tables)
        return [{"id": c["id"], "rule": c["rule"]} for c in self.conventions if c["tables"] & wanted]

    def conventions_notes(self, tables: set[str]) -> str:
        rules = self.conventions_for(tables)
        if not rules:
            return ""
        return ("# Query conventions for this copy of the data (from Figure 1's data quality checks)\n"
                + "\n".join(f"- [{r['id']}] {r['rule']}" for r in rules))

    def unavailable_notes(self, available_tables: set[str]) -> str:
        """Lists code systems whose event tables are not loaded, so S4 can declare them unanswerable."""
        lines = []
        for system in self.code_systems.values():
            if not set(system.event_tables) & available_tables:
                lines.append(f"- {system.name}: {', '.join(system.event_tables)} not loaded")
        if not lines:
            return ""
        return ("# Not available in this dataset\n" + "\n".join(lines) +
                "\nRequests that need these data cannot be answered from this dataset (a dictionary table alone has no patient data).")


# ----------------------------------------------------------------------
# MIMIC-III v1.4
# ----------------------------------------------------------------------
_ROW_ID = "Row number within this table; not an identifier, never use it for joins"
_SUBJECT = "Patient identifier (PATIENTS)"
_HADM = "Hospital admission identifier (ADMISSIONS)"
_ICUSTAY = "ICU stay identifier (ICUSTAYS)"
_CGID = "Caregiver identifier (CAREGIVERS)"

MIMIC_III_TABLE_DOCS: dict[str, tuple[str, dict[str, str]]] = {
    "patients": (
        "One row per patient: gender, date of birth, and dates of death.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT,
         "gender": "'M' or 'F'",
         "dob": "Date of birth (shifted). Patients older than 89 at their first admission have DOB shifted so that their age appears as about 300 years",
         "dod": "Date of death from any source (hospital or social security records); null if not known to have died",
         "dod_hosp": "Date of death recorded in the hospital database",
         "dod_ssn": "Date of death from the social security database",
         "expire_flag": "1 if the patient has died (dod is not null), else 0"},
    ),
    "admissions": (
        "One row per hospital admission: admission and discharge times, admission type and location, insurance, demographics, admitting diagnosis text, and in-hospital death.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": "Hospital admission identifier (unique per row)",
         "admittime": "Admission time (shifted)", "dischtime": "Discharge time (shifted)",
         "deathtime": "Time of in-hospital death; null if the patient did not die in hospital",
         "admission_type": "One of 'ELECTIVE', 'URGENT', 'EMERGENCY', 'NEWBORN'",
         "admission_location": "Where the patient was admitted from, e.g. 'EMERGENCY ROOM ADMIT', 'PHYS REFERRAL/NORMAL DELI', 'TRANSFER FROM HOSP/EXTRAM', 'CLINIC REFERRAL/PREMATURE'",
         "discharge_location": "Where the patient went after discharge, e.g. 'HOME', 'HOME HEALTH CARE', 'SNF', 'REHAB/DISTINCT PART HOSP', 'DEAD/EXPIRED'",
         "insurance": "One of 'Medicare', 'Private', 'Medicaid', 'Government', 'Self Pay'",
         "language": "Preferred language, 4-letter uppercase abbreviations such as 'ENGL', 'SPAN'; often null",
         "religion": "Religion, uppercase free text, e.g. 'CATHOLIC', 'NOT SPECIFIED'",
         "marital_status": "Uppercase, e.g. 'MARRIED', 'SINGLE', 'WIDOWED', 'DIVORCED', 'SEPARATED'",
         "ethnicity": "Uppercase free text with subgroups, e.g. 'WHITE', 'BLACK/AFRICAN AMERICAN', 'HISPANIC OR LATINO', 'ASIAN - CHINESE', 'UNKNOWN/NOT SPECIFIED'; use prefix patterns such as 'ASIAN%' for groups",
         "edregtime": "Time registered in the emergency department", "edouttime": "Time left the emergency department",
         "diagnosis": "Free-text preliminary admitting diagnosis (uppercase), not coded; use diagnoses_icd for coded diagnoses",
         "hospital_expire_flag": "1 if the patient died during this admission, else 0",
         "has_chartevents_data": "1 if the admission has ICU charted data"},
    ),
    "icustays": (
        "One row per ICU stay: care units, ICU in/out times, length of stay, and source system.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": "ICU stay identifier (unique per row)",
         "dbsource": "ICU documentation system: 'carevue' (2001-2008), 'metavision' (2008-2012), or 'both'",
         "first_careunit": "First ICU type: 'MICU' (medical), 'SICU' (surgical), 'CCU' (coronary care), 'CSRU' (cardiac surgery recovery), 'TSICU' (trauma surgical), 'NICU' (neonatal)",
         "last_careunit": "Last ICU type (same values as first_careunit)",
         "first_wardid": "First ward (physical location) identifier", "last_wardid": "Last ward identifier",
         "intime": "ICU admission time", "outtime": "ICU discharge time",
         "los": "ICU length of stay in fractional days"},
    ),
    "diagnoses_icd": (
        "Hospital-assigned ICD-9 diagnosis codes for each admission, assigned at discharge for billing, ordered by priority.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "seq_num": "Priority of the diagnosis within the admission; 1 = primary diagnosis",
         "icd9_code": "ICD-9-CM diagnosis code stored as text WITHOUT the dot: 250.00 is '25000', 401.9 is '4019', V45.81 is 'V4581'"},
    ),
    "d_icd_diagnoses": (
        "Dictionary of ICD-9-CM diagnosis codes: code to short and long title.",
        {"row_id": _ROW_ID, "icd9_code": "ICD-9-CM diagnosis code without the dot (joins diagnoses_icd.icd9_code)",
         "short_title": "Abbreviated title", "long_title": "Full title, e.g. 'Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled'"},
    ),
    "procedures_icd": (
        "ICD-9 procedure codes for each admission, ordered by sequence.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "seq_num": "Order of the procedure within the admission",
         "icd9_code": "ICD-9-CM procedure code WITHOUT the dot: 36.10 is '3610', 96.71 is '9671'"},
    ),
    "d_icd_procedures": (
        "Dictionary of ICD-9-CM procedure codes: code to short and long title.",
        {"row_id": _ROW_ID, "icd9_code": "ICD-9-CM procedure code without the dot (joins procedures_icd.icd9_code)",
         "short_title": "Abbreviated title", "long_title": "Full title"},
    ),
    "d_labitems": (
        "Dictionary of laboratory tests: lab ITEMID to test name, fluid, category, and LOINC code. Dictionary only: lab results are in LABEVENTS.",
        {"row_id": _ROW_ID, "itemid": "Lab test identifier (joins labevents.itemid)",
         "label": "Test name, e.g. 'Creatinine', '% Hemoglobin A1c'", "fluid": "Specimen fluid, e.g. 'Blood', 'Urine'",
         "category": "'Chemistry', 'Hematology', or 'Blood Gas'", "loinc_code": "LOINC code, e.g. '4548-4'; may be null"},
    ),
    "d_items": (
        "Dictionary of non-lab items: ITEMID to label, category, unit, source system, and the event table that uses it (CHARTEVENTS, INPUTEVENTS_CV/MV, OUTPUTEVENTS, PROCEDUREEVENTS_MV, DATETIMEEVENTS, MICROBIOLOGYEVENTS).",
        {"row_id": _ROW_ID, "itemid": "Item identifier (joins the itemid of the table in linksto)",
         "label": "Item name, e.g. 'Heart Rate', 'Invasive Ventilation'", "abbreviation": "Short name (MetaVision items only)",
         "dbsource": "'carevue' or 'metavision': the same concept has different itemids in each system",
         "linksto": "Lowercase name of the event table that uses this itemid, e.g. 'chartevents', 'procedureevents_mv'",
         "category": "Item category", "unitname": "Unit of measurement", "param_type": "Value type (MetaVision)",
         "conceptid": "Unused (always null)"},
    ),
    "transfers": (
        "Patient movements between hospital units and beds during an admission, including ICU admission and discharge events.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "icustay_id": "ICU stay identifier when the movement is part of an ICU stay; else null",
         "dbsource": "'carevue' or 'metavision'",
         "eventtype": "'admit', 'transfer', or 'discharge'",
         "prev_careunit": "Previous ICU type (null for non-ICU wards)", "curr_careunit": "Current ICU type: 'MICU', 'SICU', 'CCU', 'CSRU', 'TSICU', 'NICU'; null for non-ICU wards",
         "prev_wardid": "Previous ward identifier", "curr_wardid": "Current ward identifier",
         "intime": "Time the patient entered the current unit", "outtime": "Time the patient left the current unit",
         "los": "Length of stay in the current unit, in hours"},
    ),
    "services": (
        "Clinical service the patient was under during an admission (e.g. medicine, surgery), with the time of each service change.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "transfertime": "Time the patient moved to the current service",
         "prev_service": "Previous service (null for the first one)",
         "curr_service": "Service code: 'MED' (medicine), 'SURG' (surgery), 'CMED' (cardiac medical), 'CSURG' (cardiac surgery), 'NSURG' (neurosurgery), 'NMED' (neurology), 'TRAUM' (trauma), 'ORTHO' (orthopedics), 'VSURG' (vascular), 'TSURG' (thoracic), 'PSURG' (plastic), 'GU' (urology), 'GYN', 'OBS', 'ENT', 'DENT', 'OMED' (oncology), 'PSYCH', 'NB' (newborn), 'NBB' (newborn baby)"},
    ),
    "procedureevents_mv": (
        "Procedures documented in the ICU (MetaVision patients only, 2008-2012), e.g. ventilation, dialysis, line insertion, imaging, with start and end times.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "starttime": "Procedure start time", "endtime": "Procedure end time",
         "itemid": "Procedure item (names in d_items, linksto = 'procedureevents_mv')",
         "value": "Amount or duration", "valueuom": "Unit of value, e.g. 'min', 'None'",
         "location": "Body location", "locationcategory": "Location category",
         "storetime": "Time the event was recorded", "cgid": _CGID,
         "orderid": "Order identifier", "linkorderid": "Links related orders",
         "ordercategoryname": "Order category", "secondaryordercategoryname": "Secondary order category",
         "ordercategorydescription": "Order type description",
         "isopenbag": "Open bag flag", "continueinnextdept": "Continued in the next department",
         "cancelreason": "Cancellation reason code", "statusdescription": "Status, e.g. 'FinishedRunning', 'Stopped'",
         "comments_editedby": "Editor role", "comments_canceledby": "Canceller role", "comments_date": "Comment time"},
    ),
    "microbiologyevents": (
        "Microbiology tests: specimens, organisms grown, and antibiotic sensitivities.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "chartdate": "Date of the test", "charttime": "Time of the test (may be null)",
         "spec_itemid": "Specimen item", "spec_type_desc": "Specimen type, uppercase, e.g. 'BLOOD CULTURE', 'URINE', 'SPUTUM'",
         "org_itemid": "Organism item", "org_name": "Organism grown, uppercase, e.g. 'STAPH AUREUS COAG +', 'ESCHERICHIA COLI'; null means no growth",
         "isolate_num": "Isolate number", "ab_itemid": "Antibiotic item",
         "ab_name": "Antibiotic tested, uppercase, e.g. 'VANCOMYCIN', 'OXACILLIN'",
         "dilution_text": "Dilution as text", "dilution_comparison": "Comparison operator for the dilution",
         "dilution_value": "Dilution value",
         "interpretation": "Sensitivity: 'S' (sensitive), 'R' (resistant), 'I' (intermediate), 'P' (pending)"},
    ),
    "drgcodes": (
        "Diagnosis Related Groups (billing) for each admission, with severity and mortality ratings for APR-DRGs.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "drg_type": "'HCFA', 'MS' (Medicare Severity), or 'APR ' (All Patient Refined; stored with a trailing space, so compare TRIM(drg_type) = 'APR')",
         "drg_code": "DRG code within its drg_type", "description": "DRG description",
         "drg_severity": "Severity of illness 1-4 (APR only; null otherwise)",
         "drg_mortality": "Risk of mortality 1-4 (APR only; null otherwise)"},
    ),
    "labevents": (
        "Laboratory measurements for patients both in the hospital and in outpatient clinics.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": "Hospital admission identifier; null for outpatient tests",
         "itemid": "Lab test (names in d_labitems)", "charttime": "Time the specimen was taken",
         "value": "Result as text", "valuenum": "Numeric result (null if not numeric)", "valueuom": "Unit of the result",
         "flag": "'abnormal' if outside the normal range, else null"},
    ),
    "prescriptions": (
        "Medication orders (not confirmed administration): drug, dose, route, and dates.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": "ICU stay identifier if ordered in the ICU",
         "startdate": "Order start date", "enddate": "Order end date",
         "drug_type": "'MAIN', 'BASE', or 'ADDITIVE'", "drug": "Drug name as ordered (free text, mixed case)",
         "drug_name_poe": "Drug name in the order entry system", "drug_name_generic": "Generic drug name",
         "formulary_drug_cd": "Hospital formulary code", "gsn": "Generic Sequence Number", "ndc": "National Drug Code",
         "prod_strength": "Product strength", "dose_val_rx": "Prescribed dose", "dose_unit_rx": "Unit of the dose",
         "form_val_disp": "Amount dispensed", "form_unit_disp": "Unit dispensed", "route": "Route, e.g. 'PO', 'IV'"},
    ),
    "chartevents": (
        "All charted ICU observations, e.g. vital signs (heart rate, blood pressure), ventilator settings, scores. The largest table.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "itemid": "Charted item (names in d_items; CareVue and MetaVision use different itemids)",
         "charttime": "Time of the observation", "storetime": "Time it was recorded", "cgid": _CGID,
         "value": "Value as text", "valuenum": "Numeric value", "valueuom": "Unit",
         "warning": "Warning flag (MetaVision)", "error": "1 if the value was marked as an error (MetaVision)",
         "resultstatus": "Result status (CareVue)", "stopped": "Stopped flag (CareVue)"},
    ),
    "inputevents_cv": (
        "ICU fluid and medication inputs documented in the CareVue system (2001-2008).",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "charttime": "Time of the input", "itemid": "Input item (names in d_items)",
         "amount": "Amount given", "amountuom": "Unit of amount", "rate": "Rate", "rateuom": "Unit of rate",
         "storetime": "Time recorded", "cgid": _CGID, "orderid": "Order identifier", "linkorderid": "Links related orders",
         "stopped": "Stopped status", "newbottle": "New bottle flag", "originalamount": "Original amount",
         "originalamountuom": "Original amount unit", "originalroute": "Original route", "originalrate": "Original rate",
         "originalrateuom": "Original rate unit", "originalsite": "Original site"},
    ),
    "inputevents_mv": (
        "ICU fluid and medication inputs documented in the MetaVision system (2008-2012), with start and end times.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "starttime": "Start time", "endtime": "End time", "itemid": "Input item (names in d_items)",
         "amount": "Amount given", "amountuom": "Unit of amount", "rate": "Rate", "rateuom": "Unit of rate",
         "storetime": "Time recorded", "cgid": _CGID, "orderid": "Order identifier", "linkorderid": "Links related orders",
         "ordercategoryname": "Order category", "secondaryordercategoryname": "Secondary order category",
         "ordercomponenttypedescription": "Role of the component in the order", "ordercategorydescription": "Order type",
         "patientweight": "Patient weight in kg", "totalamount": "Total amount in the bag", "totalamountuom": "Unit of total amount",
         "isopenbag": "Open bag flag", "continueinnextdept": "Continued in the next department",
         "cancelreason": "Cancellation reason", "statusdescription": "Status, e.g. 'FinishedRunning'",
         "comments_editedby": "Editor role", "comments_canceledby": "Canceller role", "comments_date": "Comment time",
         "originalamount": "Original amount", "originalrate": "Original rate"},
    ),
    "outputevents": (
        "ICU outputs such as urine, drains, and stool, from both CareVue and MetaVision.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "charttime": "Time of the output", "itemid": "Output item (names in d_items)",
         "value": "Amount", "valueuom": "Unit, usually 'ml'", "storetime": "Time recorded", "cgid": _CGID,
         "stopped": "Stopped status", "newbottle": "New bottle flag", "iserror": "1 if marked as an error"},
    ),
    "datetimeevents": (
        "ICU observations whose value is a date or time (e.g. date of last dialysis, line insertion time), not a measurement.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM, "icustay_id": _ICUSTAY,
         "itemid": "Item (names in d_items, linksto = 'datetimeevents')", "charttime": "Time of charting",
         "storetime": "Time recorded", "cgid": _CGID, "value": "The recorded date/time",
         "valueuom": "Unit (usually 'Date' or 'Date and Time')", "warning": "Warning flag", "error": "Error flag",
         "resultstatus": "Result status", "stopped": "Stopped status"},
    ),
    "cptevents": (
        "Current Procedural Terminology (CPT) codes billed for ICU and respiratory services; billing-oriented, mostly professional services.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "costcenter": "'ICU' or 'Resp' (respiratory)", "chartdate": "Date of the service (often null)",
         "cpt_cd": "CPT code as text, e.g. '99291' (critical care, first hour)", "cpt_number": "Numeric part of the CPT code",
         "cpt_suffix": "Letter suffix of the CPT code", "ticket_id_seq": "Order of codes on the billing ticket",
         "sectionheader": "CPT section, e.g. 'Evaluation and management'", "subsectionheader": "CPT subsection",
         "description": "Code description (often null)"},
    ),
    "d_cpt": (
        "High-level CPT code ranges (sections and subsections), not individual codes; match cptevents.cpt_number to a range.",
        {"row_id": _ROW_ID, "category": "Category number", "sectionrange": "Range of codes in the section",
         "sectionheader": "Section name", "subsectionrange": "Range of codes in the subsection",
         "subsectionheader": "Subsection name", "codesuffix": "Code suffix",
         "mincodeinsubsection": "Lowest code number in the subsection", "maxcodeinsubsection": "Highest code number in the subsection"},
    ),
    "callout": (
        "ICU discharge planning: requests to move a patient out of the ICU ('call outs') and their outcomes.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "submit_wardid": "Ward that submitted the request", "submit_careunit": "ICU that submitted the request",
         "curr_wardid": "Current ward", "curr_careunit": "Current ICU type", "callout_wardid": "Ward requested (1 = first available)",
         "callout_service": "Service the patient is called out to", "request_tele": "1 if telemetry requested",
         "request_resp": "1 if respiratory care requested", "request_cdiff": "1 if C. difficile precautions requested",
         "request_mrsa": "1 if MRSA precautions requested", "request_vre": "1 if VRE precautions requested",
         "callout_status": "Request status, e.g. 'Inactive'", "callout_outcome": "'Discharged' or 'Cancelled'",
         "discharge_wardid": "Ward the patient was discharged to", "acknowledge_status": "Acknowledgement status",
         "createtime": "Request created", "updatetime": "Request updated", "acknowledgetime": "Request acknowledged",
         "outcometime": "Outcome time", "firstreservationtime": "First bed reservation", "currentreservationtime": "Current bed reservation"},
    ),
    "caregivers": (
        "Caregivers who documented data (cgid), with their role; no clinical content.",
        {"row_id": _ROW_ID, "cgid": "Caregiver identifier (joins cgid in the ICU event tables)",
         "label": "Role abbreviation, e.g. 'RN', 'MD'", "description": "Role description, e.g. 'RN', 'Resident/Fellow/PA/NP'"},
    ),
    "noteevents": (
        "Free-text clinical notes: discharge summaries, nursing and physician notes, radiology and ECG reports.",
        {"row_id": _ROW_ID, "subject_id": _SUBJECT, "hadm_id": _HADM,
         "chartdate": "Date of the note", "charttime": "Time of the note (often null)", "storetime": "Time recorded",
         "category": "Note type, e.g. 'Discharge summary', 'Nursing', 'Radiology', 'ECG'",
         "description": "Note subtype", "cgid": _CGID, "iserror": "1 if marked as an error",
         "text": "Full note text (free text; not suitable for exact matching)"},
    ),
}

MIMIC_III = MimicProfile(
    name="MIMIC-III",
    code_systems={system.name: system for system in (
        CodeSystem("diagnosis", ("diagnoses_icd",), ("icd9_code",), "d_icd_diagnoses", ("icd9_code",),
                   "long_title", ("ICD9CM",), "a disease or condition"),
        CodeSystem("procedure", ("procedures_icd",), ("icd9_code",), "d_icd_procedures", ("icd9_code",),
                   "long_title", ("ICD9CM",), "a surgery or hospital procedure"),
        CodeSystem("lab", ("labevents",), ("itemid",), "d_labitems", ("itemid",), "label", ("LNC",), "a lab test"),
        CodeSystem("icu_item", ("chartevents", "inputevents_mv", "inputevents_cv", "outputevents",
                                "procedureevents_mv", "datetimeevents"),
                   ("itemid",), "d_items", ("itemid",), "label", (),
                   "an ICU vital sign, charted item, fluid input/output, or ICU procedure such as ventilation"),
        CodeSystem("medication", ("prescriptions",), ("drug",), None, (), "drug", ("RXNORM",),
                   "a drug ordered for the patient (prescriptions)"),
        CodeSystem("organism", ("microbiologyevents",), ("org_name",), None, (), "org_name", (), "a microorganism grown in a culture"),
        CodeSystem("specimen", ("microbiologyevents",), ("spec_type_desc",), None, (), "spec_type_desc", (), "a microbiology specimen or culture type (e.g. blood culture, MRSA screen)"),
        CodeSystem("antibiotic", ("microbiologyevents",), ("ab_name",), None, (), "ab_name", (), "an antibiotic tested against a cultured organism (a lab sensitivity test, not a drug given to the patient)"),
    )},
    key_columns=("icustay_id", "hadm_id", "subject_id", "cgid"),
    private=True,
    catalog=True,
    key_only_tables={"patients": ("subject_id",)},
    table_docs=MIMIC_III_TABLE_DOCS,
    domain_notes="""
# MIMIC-III conventions (apply them when grounding)
- Identifiers: subject_id = one patient; hadm_id = one hospital admission; icustay_id = one ICU stay. Each icustay_id belongs to one hadm_id, each hadm_id to one subject_id. Join on the most specific shared identifier. row_id is a per-table row number: never join on it.
- Counting: "how many patients" counts DISTINCT subject_id; "how many admissions" counts DISTINCT hadm_id; "how many ICU stays" counts DISTINCT icustay_id. A concept like "admission records" is the table's rows: ground it to the table's key column.
- Diagnoses and procedures use ICD-9-CM only, in the icd9_code column (there is no icd_version), stored as text WITHOUT dots: 250.00 is '25000', 401.9 is '4019', V45.81 is 'V4581', procedure 96.71 is '9671'. A code family is a prefix pattern, e.g. '250%' (diabetes mellitus), '410%' (acute myocardial infarction), '428%' (heart failure).
- diagnoses_icd.seq_num = 1 is the primary diagnosis. admissions.diagnosis is free text, not coded.
- diagnoses_icd and procedures_icd have no time column. Date a diagnosis or procedure by its admission (admissions.admittime, or dischtime) and record this approximation in "assumptions": questions about when a diagnosis or procedure happened, time since it, or time windows between events in different admissions are answerable at admission level. Only the order of two diagnoses or procedures within the same admission cannot be determined (e.g. "B after A during the same hospital visit"); a request that needs it is unanswerable even though both codes exist, with "diagnosis/procedure time" in "missing_concepts".
- Microbiology tests, cultures, and specimens (including screens such as MRSA screen) are in microbiologyevents (spec_type_desc, org_name, ab_name), not in labevents.
- The dictionaries map abbreviated short titles to full long titles (d_icd_diagnoses, d_icd_procedures): a question asking what an abbreviated diagnosis or procedure name stands for, or what a code means, is answered from them.
- Every event table has subject_id (and hadm_id): count or filter patients there. Include patients only when patient attributes are needed (gender, dob, dod, expire_flag).
- Use only codes listed under code candidates: they come from the dictionaries and occur in this dataset. Once codes are chosen, the dictionary table is not required unless the answer must output the code names.
- Age is not stored: age at admission = years between patients.dob and admissions.admittime. Patients older than 89 have shifted DOBs and appear about 300 years old; record in "assumptions" how they are handled (e.g. treat age >= 300 as "over 89").
- All dates are shifted into the future (years ~2100-2200) per patient: calendar years and seasons are not real, but intervals within a patient are. There is no real "now": relative times refer to the parameter current_time (see the rules). A current admission or ICU stay is one that started before current_time and has not ended by then (end time null or after current_time).
- Death: admissions.hospital_expire_flag = 1 (or deathtime not null) = died during that admission; patients.expire_flag / dod = died at any time, including after discharge.
- ICU data come from two systems: CareVue (2001-2008) and MetaVision (2008-2012), see icustays.dbsource. The same concept has different itemids in each system; procedureevents_mv covers MetaVision patients only.
- icustays.los is in days; transfers.los is in hours. Care unit values: MICU, SICU, CCU, CSRU, TSICU, NICU (NICU = neonates).
- cptevents holds billing CPT codes for ICU and respiratory services (cpt_cd); d_cpt lists only code ranges, so match cptevents.cpt_number between mincodeinsubsection and maxcodeinsubsection. Clinical procedures are better covered by procedures_icd.
- datetimeevents values are dates/times (e.g. when something happened), not measurements; callout is ICU discharge planning; caregivers (cgid) only gives the documenting caregiver's role.
- Stored text values are mostly uppercase (admission_type, ethnicity, org_name, ...); use the values in the column descriptions.
- Sample rows are withheld (credentialed data): rely on the column descriptions for formats and values.
""".strip(),
)


# ----------------------------------------------------------------------
# Figure 1 shared knowledge (docs/mimic3/)
# ----------------------------------------------------------------------
from pneumarx.shared.paths import PROJECT_ROOT
KNOWLEDGE_DIR = PROJECT_ROOT / "docs" / "mimic3"


def load_figure1_knowledge(
    directory: Path = KNOWLEDGE_DIR,
) -> tuple[dict[str, tuple[str, dict[str, str]]], tuple[dict, ...]]:
    """
    (table_docs, conventions) from Figure 1's schema profile and query conventions.
    Keeps descriptions, column roles, references, and rule text only; drops every
    measured statistic. Returns empty values when the files are absent.
    """
    profile_path = directory / "mimic3_schema_profile.json"
    conventions_path = directory / "mimic3_query_conventions.json"
    table_docs: dict[str, tuple[str, dict[str, str]]] = {}
    if profile_path.exists():
        for table, spec in json.loads(profile_path.read_text())["tables"].items():
            columns = {}
            for column, col in spec.get("columns", {}).items():
                text = col.get("description", "")
                extras = [f"role: {col['role']}"] if col.get("role") else []
                if col.get("references"):
                    refs = col["references"] if isinstance(col["references"], list) else [col["references"]]
                    extras.append("references " + ", ".join(map(str, refs)))
                columns[column] = text + (f" ({'; '.join(extras)})" if extras else "")
            table_docs[table] = (spec.get("description", ""), columns)
    conventions: list[dict] = []
    if conventions_path.exists():
        for c in json.loads(conventions_path.read_text())["conventions"]:
            tables = {target.split(".")[0] for target in c.get("applies_to", [])}
            conventions.append({"id": c["id"], "rule": c["rule"], "tables": tables})
    return table_docs, tuple(conventions)


def _with_figure1_knowledge(profile: MimicProfile) -> MimicProfile:
    table_docs, conventions = load_figure1_knowledge()
    if not table_docs and not conventions:
        return profile
    merged = dict(profile.table_docs)
    for table, (description, columns) in table_docs.items():
        own_description, own_columns = merged.get(table, ("", {}))
        merged[table] = (description or own_description, {**own_columns, **columns})
    return replace(profile, table_docs=merged, conventions=conventions,
                   knowledge_source="Figure 1 schema profile and query conventions (docs/mimic3)")


MIMIC_III = _with_figure1_knowledge(MIMIC_III)


def get_profile(dataset_name: str) -> MimicProfile | None:
    name = dataset_name.lower()
    if name == "hospital":
        from .hospital_profile import HOSPITAL
        return HOSPITAL
    if name.startswith("mimic_iii") or name.startswith("mimic3"):
        return MIMIC_III
    return None


def is_mimic(dataset_name: str) -> bool:
    return dataset_name.lower().startswith(("mimic_iii", "mimic3"))
