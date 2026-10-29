# MIMIC-III v1.4 schema profile

> **Shared snapshot - do not edit by hand.** Regenerated only by the dataset maintainer with `python scripts/prepare_mimic3.py publish`; everyone else treats this file as read-only. Counts from 1 to 10 are shown as `<11`.

Data fingerprint `55cb7586f72a` (rows per table: admissions 58,976, callout 34,499, caregivers 7,567, cptevents 573,146, d_cpt 134, d_icd_diagnoses 14,567, d_icd_procedures 3,882, d_items 12,487, d_labitems 753, datetimeevents 4,485,937, diagnoses_icd 651,047, drgcodes 125,557, icustays 61,532, inputevents_cv 17,527,935, microbiologyevents 631,726, patients 46,520, prescriptions 4,156,450, procedureevents_mv 258,066, procedures_icd 240,095, services 73,343, transfers 261,897).

What each table and column of the loaded MIMIC-III data contains: written descriptions from the MIMIC-III documentation combined with facts measured on this copy of the data. The query system uses this to find the right tables, columns and links for a question. Rule names (e.g. `group.padded_text`) are the `id`s of the rules in `mimic3_query_conventions.json`.

**Identifiers.** subject_id (patient) > hadm_id (hospital admission) > icustay_id (ICU stay): each ICU stay belongs to one admission and each admission to one patient. Join on the most specific identifier both tables share.

**Column roles.** *row_number*: Row number within the table; not an identifier, never join on it; *identifier*: Identifies one record of this table (its key); *reference*: Points to a record in another table (see 'references'); *code*: A code from a coding system (ICD-9, CPT, DRG, NDC, ...), stored as text; *local_identifier*: An identifier with no table of its own in this dataset (e.g. ward, order); *time*: Date or date-time (shifted into the future per patient; intervals are real); *flag*: Yes/no indicator (usually 0/1); *category*: One of a small set of values (listed under 'values'); *number*: A measured or counted quantity; *text*: Free or semi-free text; match with patterns (ILIKE), not exact values; *always_null*: Always empty in this dataset; do not filter or group on it.

## admissions

One row per hospital admission: admission and discharge times, admission type and location, insurance, demographics, admitting diagnosis text, and in-hospital death.

Kind: core. Rows: 58,976. Key: hadm_id.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 54,323 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | identifier | 0 | 57,608 |  | Hospital admission identifier (unique per row) |
| admittime | TIMESTAMP | time | 0 | 67,002 |  | Admission time (shifted) |
| dischtime | TIMESTAMP | time | 0 | 62,767 |  | Discharge time (shifted) |
| deathtime | TIMESTAMP | time | 90.074 | 7,972 |  | Time of in-hospital death; null if the patient did not die in hospital |
| admission_type | VARCHAR | category | 0 | 4 |  | One of 'ELECTIVE', 'URGENT', 'EMERGENCY', 'NEWBORN' |
| admission_location | VARCHAR | category | 0 | 9 |  | Where the patient was admitted from, e.g. 'EMERGENCY ROOM ADMIT', 'PHYS REFERRAL/NORMAL DELI', 'TRANSFER FROM HOSP/EXTRAM', 'CLINIC REFERRAL/PREMATURE' |
| discharge_location | VARCHAR | category | 0 | 17 |  | Where the patient went after discharge, e.g. 'HOME', 'HOME HEALTH CARE', 'SNF', 'REHAB/DISTINCT PART HOSP', 'DEAD/EXPIRED' |
| insurance | VARCHAR | category | 0 | 5 |  | One of 'Medicare', 'Private', 'Medicaid', 'Government', 'Self Pay' |
| language | VARCHAR | text | 42.953 | 73 |  | Preferred language, 4-letter uppercase abbreviations such as 'ENGL', 'SPAN'; often null |
| religion | VARCHAR | category | 0.777 | 21 |  | Religion, uppercase free text, e.g. 'CATHOLIC', 'NOT SPECIFIED' |
| marital_status | VARCHAR | category | 17.173 | 7 |  | Uppercase, e.g. 'MARRIED', 'SINGLE', 'WIDOWED', 'DIVORCED', 'SEPARATED' |
| ethnicity | VARCHAR | category | 0 | 39 |  | Uppercase free text with subgroups, e.g. 'WHITE', 'BLACK/AFRICAN AMERICAN', 'HISPANIC OR LATINO', 'ASIAN - CHINESE', 'UNKNOWN/NOT SPECIFIED'; use prefix patterns such as 'ASIAN%' for groups |
| edregtime | TIMESTAMP | time | 47.645 | 34,820 |  | Time registered in the emergency department |
| edouttime | TIMESTAMP | time | 47.645 | 25,249 |  | Time left the emergency department |
| diagnosis | VARCHAR | text | 0.042 | 17,142 |  | Free-text preliminary admitting diagnosis (uppercase), not coded; use diagnoses_icd for coded diagnoses |
| hospital_expire_flag | SMALLINT | flag | 0 | 2 |  | 1 if the patient died during this admission, else 0 |
| has_chartevents_data | SMALLINT | flag | 0 | 2 |  | 1 if the admission has ICU charted data |

- **admittime** rules: group.negative_duration
- **dischtime** rules: group.negative_duration
- **deathtime** rules: temporal.admissions.deathtime_outside_stay
- **admission_type** values: `'EMERGENCY'`, `'NEWBORN'`, `'ELECTIVE'`, `'URGENT'`
- **admission_type** rules: dist.admissions.admission_type
- **admission_location** values: `'EMERGENCY ROOM ADMIT'`, `'PHYS REFERRAL/NORMAL DELI'`, `'CLINIC REFERRAL/PREMATURE'`, `'TRANSFER FROM HOSP/EXTRAM'`, `'TRANSFER FROM SKILLED NUR'`, `'** INFO NOT AVAILABLE **'`, `'HMO REFERRAL/SICK'`, `'TRANSFER FROM OTHER HEALT'` ...
- **discharge_location** values: `'HOME'`, `'HOME HEALTH CARE'`, `'SNF'`, `'REHAB/DISTINCT PART HOSP'`, `'DEAD/EXPIRED'`, `'LONG TERM CARE HOSPITAL'`, `'SHORT TERM HOSPITAL'`, `'DISC-TRAN CANCER/CHLDRN H'`, `'DISCH-TRAN TO PSYCH HOSP'`, `'HOSPICE-HOME'`, `'LEFT AGAINST MEDICAL ADVI'`, `'HOSPICE-MEDICAL FACILITY'`, `'HOME WITH HOME IV PROVIDR'`, `'OTHER FACILITY'`, `'ICF'` ...
- **insurance** values: `'Medicare'`, `'Private'`, `'Medicaid'`, `'Government'`, `'Self Pay'`
- **religion** values: `'CATHOLIC'`, `'NOT SPECIFIED'`, `'UNOBTAINABLE'`, `'PROTESTANT QUAKER'`, `'JEWISH'`, `'OTHER'`, `'EPISCOPALIAN'`, `'GREEK ORTHODOX'`, `'CHRISTIAN SCIENTIST'`, `'BUDDHIST'`, `'MUSLIM'`, `'JEHOVAH'S WITNESS'`, `'UNITARIAN-UNIVERSALIST'`, `'HINDU'`, `'ROMANIAN EAST. ORTH'` ...
- **marital_status** values: `'MARRIED'`, `'SINGLE'`, `'WIDOWED'`, `'DIVORCED'`, `'SEPARATED'`, `'UNKNOWN (DEFAULT)'`, `'LIFE PARTNER'`
- **ethnicity** values: `'WHITE'`, `'BLACK/AFRICAN AMERICAN'`, `'UNKNOWN/NOT SPECIFIED'`, `'HISPANIC OR LATINO'`, `'OTHER'`, `'ASIAN'`, `'UNABLE TO OBTAIN'`, `'PATIENT DECLINED TO ANSWER'`, `'ASIAN - CHINESE'`, `'HISPANIC/LATINO - PUERTO RICAN'`, `'BLACK/CAPE VERDEAN'`, `'WHITE - RUSSIAN'`, `'MULTI RACE ETHNICITY'`, `'BLACK/HAITIAN'`, `'ASIAN - ASIAN INDIAN'` ...
- **edregtime** rules: group.negative_duration
- **edouttime** rules: group.negative_duration
- **diagnosis** rules: group.padded_text
- **hospital_expire_flag** values: `'0'`, `'1'`
- **hospital_expire_flag** rules: temporal.admissions.deathtime_outside_stay
- **has_chartevents_data** values: `'1'`, `'0'`

## callout

ICU discharge planning: requests to move a patient out of the ICU ('call outs') and their outcomes.

Kind: event. Rows: 34,499. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 31,974 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 21,382 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 27,864 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| submit_wardid | INTEGER | local_identifier | <11 rows missing | 10 |  | Ward that submitted the request |
| submit_careunit | VARCHAR | category | 85.153 | 5 |  | ICU that submitted the request |
| curr_wardid | INTEGER | local_identifier | <11 rows missing | 32 |  | Current ward |
| curr_careunit | VARCHAR | category | <11 rows missing | 5 |  | Current ICU type |
| callout_wardid | INTEGER | local_identifier | 0 | 34 |  | Ward requested (1 = first available) |
| callout_service | VARCHAR | category | 0 | 22 |  | Service the patient is called out to |
| request_tele | SMALLINT | flag | 0 | 2 |  | 1 if telemetry requested |
| request_resp | SMALLINT | flag | 0 | 2 |  | 1 if respiratory care requested |
| request_cdiff | SMALLINT | flag | 0 | 2 |  | 1 if C. difficile precautions requested |
| request_mrsa | SMALLINT | flag | 0 | 2 |  | 1 if MRSA precautions requested |
| request_vre | SMALLINT | flag | 0 | 2 |  | 1 if VRE precautions requested |
| callout_status | VARCHAR | category | 0 | 1 |  | Request status, e.g. 'Inactive' |
| callout_outcome | VARCHAR | category | 0 | 2 |  | 'Discharged' or 'Cancelled' |
| discharge_wardid | INTEGER | local_identifier | 13.137 | 26 |  | Ward the patient was discharged to |
| acknowledge_status | VARCHAR | category | 0 | 4 |  | Acknowledgement status |
| createtime | TIMESTAMP | time | 0 | 42,343 |  | Request created |
| updatetime | TIMESTAMP | time | 0 | 41,322 |  | Request updated |
| acknowledgetime | TIMESTAMP | time | 5.194 | 36,767 |  | Request acknowledged |
| outcometime | TIMESTAMP | time | 0 | 40,257 |  | Outcome time |
| firstreservationtime | TIMESTAMP | time | 55.767 | 16,640 |  | First bed reservation |
| currentreservationtime | TIMESTAMP | time | 96.626 | 1,337 |  | Current bed reservation |

- **submit_careunit** values: `'MICU'`, `'SICU'`, `'CSRU'`, `'CCU'`, `'TSICU'`
- **curr_careunit** values: `'MICU'`, `'SICU'`, `'CSRU'`, `'TSICU'`, `'CCU'`
- **callout_service** values: `'MED'`, `'CSURG'`, `'CCU'`, `'SURG'`, `'NSURG'`, `'TRAUM'`, `'NMED'`, `'OMED'`, `'TSURG'`, `'CMED'`, `'VSURG'`, `'ORTHO'`, `'GYN'`, `'GU'`, `'PSURG'` ...
- **request_tele** values: `'1'`, `'0'`
- **request_resp** values: `'0'`, `'1'`
- **request_cdiff** values: `'0'`, `'1'`
- **request_mrsa** values: `'0'`, `'1'`
- **request_vre** values: `'0'`, `'1'`
- **callout_status** values: `'Inactive'`
- **callout_outcome** values: `'Discharged'`, `'Cancelled'`
- **acknowledge_status** values: `'Acknowledged'`, `'Unacknowledged'`, `'Revised'`, `'Reactivated'`
- **createtime** rules: group.outside_admission

## caregivers

Caregivers who documented data (cgid), with their role; no clinical content.

Kind: dictionary. Rows: 7,567. Key: cgid.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 6,841 |  | Row number within this table; not an identifier, never use it for joins |
| cgid | INTEGER | identifier | 0 | 6,837 |  | Caregiver identifier (joins cgid in the ICU event tables) |
| label | VARCHAR | text | 0.608 | 261 |  | Role abbreviation, e.g. 'RN', 'MD' |
| description | VARCHAR | category | 31.875 | 15 |  | Role description, e.g. 'RN', 'Resident/Fellow/PA/NP' |

- **description** values: `'Read Only'`, `'Resident/Fellow/PA/NP'`, `'RN'`, `'Attending'`, `'Rehabilitation'`, `'PCT/NA'`, `'Respiratory'`, `'Pharmacist'`, `'Dietitian'`, `'Social Worker'`, `'UCO'`, `'Case Manager'`, `'Administrator'`, `'Pastoral Care'`, `'Research Assistant'` ...

## cptevents

Current Procedural Terminology (CPT) codes billed for ICU and respiratory services; billing-oriented, mostly professional services.

Kind: event. Rows: 573,146. Key: none (row_id is only a row number). Rules for the whole table: quirk.cptevents.without_icu_stay.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 663,561 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 27,917 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 45,742 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| costcenter | VARCHAR | category | 0 | 2 |  | 'ICU' or 'Resp' (respiratory) |
| chartdate | TIMESTAMP | time | 82.283 | 29,466 |  | Date of the service (often null) |
| cpt_cd | VARCHAR | code | 0 | 2,374 |  | CPT code as text, e.g. '99291' (critical care, first hour) |
| cpt_number | INTEGER | code | 0.003 | 2,128 |  | Numeric part of the CPT code |
| cpt_suffix | VARCHAR | category | 99.996 | 1 |  | Letter suffix of the CPT code |
| ticket_id_seq | INTEGER | number | 17.717 | 990 |  | Order of codes on the billing ticket |
| sectionheader | VARCHAR | category | 0.004 | 6 |  | CPT section, e.g. 'Evaluation and management' |
| subsectionheader | VARCHAR | category | 0.004 | 51 |  | CPT subsection |
| description | VARCHAR | category | 82.283 | 4 |  | Code description (often null) |

- **costcenter** values: `'ICU'`, `'Resp'`
- **cpt_suffix** values: `'T'`
- **sectionheader** values: `'Evaluation and management'`, `'Medicine'`, `'Surgery'`, `'Radiology'`, `'Anesthesia'`, `'Pathology and laboratory'`, `'Emerging technology'`
- **subsectionheader** values: `'Hospital inpatient services'`, `'Critical care services'`, `'Pulmonary'`, `'Consultations'`, `'Cardiovascular system'`, `'Respiratory system'`, `'Dialysis'`, `'Musculoskeletal system'`, `'Digestive system'`, `'Nervous system'`, `'Follow-up inpatient consultations (deleted codes)'`, `'Diagnostic ultrasound'`, `'Integumentary system'`, `'Prolonged services'`, `'Cardiovascular'` ...
- **description** values: `'VENT MGMT;SUBSQ DAYS(INVASIVE)'`, `'VENT MGMT, 1ST DAY (INVASIVE)'`, `'VENT MGMT;SUBSQ DAYS(NIV)'`, `'VENT MGMT,1ST DAY (NIV)'`

## d_cpt

High-level CPT code ranges (sections and subsections), not individual codes; match cptevents.cpt_number to a range.

Kind: dictionary. Rows: 134. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 131 |  | Row number within this table; not an identifier, never use it for joins |
| category | SMALLINT | category | 0 | 3 |  | Category number |
| sectionrange | VARCHAR | category | 0 | 10 |  | Range of codes in the section |
| sectionheader | VARCHAR | category | 0 | 7 |  | Section name |
| subsectionrange | VARCHAR | text | 0 | 132 |  | Range of codes in the subsection |
| subsectionheader | VARCHAR | text | 0 | 144 |  | Subsection name |
| codesuffix | VARCHAR | category | 91.791 | 2 |  | Code suffix |
| mincodeinsubsection | INTEGER | number | 0 | 137 |  | Lowest code number in the subsection |
| maxcodeinsubsection | INTEGER | number | 0 | 133 |  | Highest code number in the subsection |

- **category** values: `'1'` ...
- **sectionrange** values: `'90281-99099; 99151-99199; 99500-99607'`, `'99201-99499'`, `'00100-01999; 99100-99150'`, `'10000-69990'`, `'80000-89398'` ...
- **sectionheader** values: `'Medicine'`, `'Evaluation and management'`, `'Anesthesia'`, `'Surgery'`, `'Pathology and laboratory'` ...

## d_icd_diagnoses

Dictionary of ICD-9-CM diagnosis codes: code to short and long title.

Kind: dictionary. Rows: 14,567. Key: icd9_code.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 12,451 |  | Row number within this table; not an identifier, never use it for joins |
| icd9_code | VARCHAR | identifier | 0 | 16,120 |  | ICD-9-CM diagnosis code without the dot (joins diagnoses_icd.icd9_code) |
| short_title | VARCHAR | text | 0 | 16,360 |  | Abbreviated title |
| long_title | VARCHAR | text | 0 | 11,067 |  | Full title, e.g. 'Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled' |

- **icd9_code** rules: group.icd9_format

## d_icd_procedures

Dictionary of ICD-9-CM procedure codes: code to short and long title.

Kind: dictionary. Rows: 3,882. Key: icd9_code.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 4,410 |  | Row number within this table; not an identifier, never use it for joins |
| icd9_code | VARCHAR | identifier | 0 | 4,565 |  | ICD-9-CM procedure code without the dot (joins procedures_icd.icd9_code) |
| short_title | VARCHAR | text | 0 | 3,936 |  | Abbreviated title |
| long_title | VARCHAR | text | 0 | 3,854 |  | Full title |

- **icd9_code** rules: group.icd9_format

## d_items

Dictionary of non-lab items: ITEMID to label, category, unit, source system, and the event table that uses it (CHARTEVENTS, INPUTEVENTS_CV/MV, OUTPUTEVENTS, PROCEDUREEVENTS_MV, DATETIMEEVENTS, MICROBIOLOGYEVENTS).

Kind: dictionary. Rows: 12,487. Key: itemid.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 11,959 |  | Row number within this table; not an identifier, never use it for joins |
| itemid | INTEGER | identifier | 0 | 10,932 |  | Item identifier (joins the itemid of the table in linksto) |
| label | VARCHAR | text | <11 rows missing | 11,599 |  | Item name, e.g. 'Heart Rate', 'Invasive Ventilation' |
| abbreviation | VARCHAR | text | 76.039 | 3,272 |  | Short name (MetaVision items only) |
| dbsource | VARCHAR | category | 0 | 3 |  | 'carevue' or 'metavision': the same concept has different itemids in each system |
| linksto | VARCHAR | category | 0 | 7 |  | Lowercase name of the event table that uses this itemid, e.g. 'chartevents', 'procedureevents_mv' |
| category | VARCHAR | text | 51.558 | 92 |  | Item category |
| unitname | VARCHAR | category | 90.118 | 54 |  | Unit of measurement |
| param_type | VARCHAR | category | 76.039 | 7 |  | Value type (MetaVision) |
| conceptid | INTEGER | always_null | 100 | 0 |  | Unused (always null) |

- **label** rules: group.padded_text
- **abbreviation** rules: group.padded_text
- **dbsource** values: `'carevue'`, `'metavision'`, `'hospital'`
- **linksto** values: `'chartevents'`, `'inputevents_cv'`, `'outputevents'`, `'microbiologyevents'`, `'inputevents_mv'`, `'datetimeevents'`, `'procedureevents_mv'`
- **unitname** values: `'None'`, `'mL'`, `'mmHg'`, `'mg'`, `'dose'`, `'cm'`, `'%'`, `'L/min'`, `'cmH2O'`, `'bpm'` ...
- **param_type** values: `'Text'`, `'Numeric'`, `'Solution'`, `'Checkbox'`, `'Date time'`, `'Process'`, `'Numeric with tag'`
- **conceptid** rules: group.all_null

## d_labitems

Dictionary of laboratory tests: lab ITEMID to test name, fluid, category, and LOINC code. Dictionary only: lab results are in LABEVENTS.

Kind: dictionary. Rows: 753. Key: itemid.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 879 |  | Row number within this table; not an identifier, never use it for joins |
| itemid | INTEGER | identifier | 0 | 1,104 |  | Lab test identifier (joins labevents.itemid) |
| label | VARCHAR | text | 0 | 717 |  | Test name, e.g. 'Creatinine', '% Hemoglobin A1c' |
| fluid | VARCHAR | category | 0 | 17 |  | Specimen fluid, e.g. 'Blood', 'Urine' |
| category | VARCHAR | category | 0 | 6 |  | 'Chemistry', 'Hematology', or 'Blood Gas' |
| loinc_code | VARCHAR | code | 22.311 | 641 |  | LOINC code, e.g. '4548-4'; may be null |

- **fluid** values: `'Blood'`, `'Urine'`, `'Other Body Fluid'`, `'Bone Marrow'`, `'Ascites'`, `'Pleural'`, `'Cerebrospinal Fluid (CSF)'`, `'Joint Fluid'`, `'BLOOD'` ...
- **category** values: `'Hematology'`, `'Chemistry'`, `'Blood Gas'`, `'CHEMISTRY'`, `'HEMATOLOGY'` ...

## datetimeevents

ICU observations whose value is a date or time (e.g. date of last dialysis, line insertion time), not a measurement.

Kind: event. Rows: 4,485,937. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 4,025,468 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 27,950 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0.04 | 30,867 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | reference | 0.093 | 44,320 | icustays.icustay_id | ICU stay identifier (ICUSTAYS) |
| itemid | INTEGER | reference | 0 | 194 | d_items.itemid | Item (names in d_items, linksto = 'datetimeevents') |
| charttime | TIMESTAMP | time | 0 | 981,597 |  | Time of charting |
| storetime | TIMESTAMP | time | 0 | 1,408,096 |  | Time recorded |
| cgid | INTEGER | reference | 0 | 1,753 | caregivers.cgid | Caregiver identifier (CAREGIVERS) |
| value | TIMESTAMP | time | 1.161 | 196,080 |  | The recorded date/time |
| valueuom | VARCHAR | category | 0 | 2 |  | Unit (usually 'Date' or 'Date and Time') |
| warning | SMALLINT | flag | 40.103 | 2 |  | Warning flag |
| error | SMALLINT | flag | 40.103 | 2 |  | Error flag |
| resultstatus | VARCHAR | always_null | 100 | 0 |  | Result status |
| stopped | VARCHAR | category | 59.897 | 2 |  | Stopped status |

- **hadm_id** rules: group.icustay_hadm_mismatch
- **icustay_id** rules: group.icustay_hadm_mismatch
- **charttime** rules: group.outside_admission
- **valueuom** values: `'Date'`, `'Date and Time'`
- **warning** values: `'0'`, `'1'`
- **error** values: `'0'`, `'1'`
- **error** rules: quirk.datetimeevents.error_rows
- **resultstatus** rules: group.all_null
- **stopped** values: `'NotStopd'`, `'D/C'd'`

## diagnoses_icd

Hospital-assigned ICD-9 diagnosis codes for each admission, assigned at discharge for billing, ordered by priority.

Kind: event. Rows: 651,047. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 693,257 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 57,608 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| seq_num | INTEGER | number | 0.007 | 39 |  | Priority of the diagnosis within the admission; 1 = primary diagnosis |
| icd9_code | VARCHAR | code | 0.007 | 6,177 | d_icd_diagnoses.icd9_code | ICD-9-CM diagnosis code stored as text WITHOUT the dot: 250.00 is '25000', 401.9 is '4019', V45.81 is 'V4581' |

- **hadm_id** rules: group.repeated_within_admission
- **icd9_code** rules: group.repeated_within_admission, group.dictionary_gap, group.icd9_format

## drgcodes

Diagnosis Related Groups (billing) for each admission, with severity and mortality ratings for APR-DRGs.

Kind: event. Rows: 125,557. Key: none (row_id is only a row number). Rules for the whole table: group.exact_duplicates.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 116,332 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 57,608 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| drg_type | VARCHAR | category | 0 | 3 |  | 'HCFA', 'MS' (Medicare Severity), or 'APR ' (All Patient Refined; stored with a trailing space, so compare TRIM(drg_type) = 'APR') |
| drg_code | VARCHAR | code | 0 | 1,804 |  | DRG code within its drg_type |
| description | VARCHAR | text | 0.05 | 1,452 |  | DRG description |
| drg_severity | SMALLINT | category | 46.929 | 5 |  | Severity of illness 1-4 (APR only; null otherwise) |
| drg_mortality | SMALLINT | category | 46.929 | 5 |  | Risk of mortality 1-4 (APR only; null otherwise) |

- **hadm_id** rules: group.repeated_within_admission
- **drg_type** values: `'APR '`, `'HCFA'`, `'MS'`
- **drg_type** rules: group.repeated_within_admission, dist.drgcodes.drg_type, group.padded_text
- **drg_severity** values: `'3'`, `'4'`, `'2'`, `'1'` ...
- **drg_mortality** values: `'4'`, `'3'`, `'2'`, `'1'` ...

## icustays

One row per ICU stay: care units, ICU in/out times, length of stay, and source system.

Kind: core. Rows: 61,532. Key: icustay_id.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 55,827 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 57,608 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | identifier | 0 | 64,481 |  | ICU stay identifier (unique per row) |
| dbsource | VARCHAR | category | 0 | 3 |  | ICU documentation system: 'carevue' (2001-2008), 'metavision' (2008-2012), or 'both' |
| first_careunit | VARCHAR | category | 0 | 6 |  | First ICU type: 'MICU' (medical), 'SICU' (surgical), 'CCU' (coronary care), 'CSRU' (cardiac surgery recovery), 'TSICU' (trauma surgical), 'NICU' (neonatal) |
| last_careunit | VARCHAR | category | 0 | 6 |  | Last ICU type (same values as first_careunit) |
| first_wardid | SMALLINT | local_identifier | 0 | 16 |  | First ward (physical location) identifier |
| last_wardid | SMALLINT | local_identifier | 0 | 16 |  | Last ward identifier |
| intime | TIMESTAMP | time | 0 | 56,453 |  | ICU admission time |
| outtime | TIMESTAMP | time | <11 rows missing | 56,396 |  | ICU discharge time |
| los | DOUBLE | number | <11 rows missing | 62,147 |  | ICU length of stay in fractional days |

- **dbsource** values: `'carevue'`, `'metavision'`, `'both'`
- **dbsource** rules: group.dbsource_crossover, dist.icustays.dbsource
- **first_careunit** values: `'MICU'`, `'CSRU'`, `'SICU'`, `'NICU'`, `'CCU'`, `'TSICU'`
- **last_careunit** values: `'MICU'`, `'CSRU'`, `'SICU'`, `'NICU'`, `'CCU'`, `'TSICU'`
- **intime** rules: group.outside_admission

## inputevents_cv

ICU fluid and medication inputs documented in the CareVue system (2001-2008).

Kind: event. Rows: 17,527,935. Key: none (row_id is only a row number). Rules for the whole table: group.exact_duplicates, quirk.icustays.without_inputevents.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 19,438,508 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 26,110 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0.129 | 33,971 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | reference | 0.174 | 36,261 | icustays.icustay_id | ICU stay identifier (ICUSTAYS) |
| charttime | TIMESTAMP | time | 0 | 1,346,881 |  | Time of the input |
| itemid | INTEGER | reference | 0 | 2,951 | d_items.itemid | Input item (names in d_items) |
| amount | DOUBLE | number | 29.127 | 173,820 |  | Amount given |
| amountuom | VARCHAR | category | 24.718 | 9 |  | Unit of amount |
| rate | DOUBLE | number | 76.426 | 17,194 |  | Rate |
| rateuom | VARCHAR | category | 76.197 | 11 |  | Unit of rate |
| storetime | TIMESTAMP | time | 0 | 3,257,368 |  | Time recorded |
| cgid | INTEGER | reference | 2.02 | 1,221 | caregivers.cgid | Caregiver identifier (CAREGIVERS) |
| orderid | INTEGER | local_identifier | 0 | 9,031,725 |  | Order identifier |
| linkorderid | INTEGER | local_identifier | 0 | 349,404 |  | Links related orders |
| stopped | VARCHAR | category | 97.258 | 4 |  | Stopped status |
| newbottle | INTEGER | flag | 98.597 | 1 |  | New bottle flag |
| originalamount | DOUBLE | number | 43.105 | 483 |  | Original amount |
| originalamountuom | VARCHAR | category | 24.412 | 10 |  | Original amount unit |
| originalroute | VARCHAR | category | 0.609 | 13 |  | Original route |
| originalrate | DOUBLE | number | 70.295 | 6,713 |  | Original rate |
| originalrateuom | VARCHAR | category | 69.926 | 1 |  | Original rate unit |
| originalsite | VARCHAR | category | 98.987 | 23 |  | Original site |

- **hadm_id** rules: group.icustay_hadm_mismatch
- **icustay_id** rules: group.icustay_hadm_mismatch, group.dbsource_crossover
- **charttime** rules: group.outside_admission
- **amountuom** values: `'ml'`, `'mg'`, `'U'`, `'mcg'`, `'cal'`, `'mEq'`, `'mEQ'`, `'tsp'`, `'gm'`, `'cc'`, `'str'`
- **rateuom** values: `'mcgkgmin'`, `'Uhr'`, `'mghr'`, `'mcghr'`, `'mgmin'`, `'Umin'`, `'mcgkghr'`, `'mgkghr'`, `'mcgmin'`, `'gmhr'`, `'Ukghr'`, `'mEqkghr'`
- **stopped** values: `'D/C'd'`, `'Stopped'`, `'Restart'`, `'NotStopd'`
- **newbottle** values: `'1'`
- **originalamountuom** values: `'ml'`, `'mg'`, `'cc'`, `'U'`, `'str'`, `'mcg'`, `'cal'`, `'vl'`, `'mEq'`, `'mEQ'`, `'tsp'`, `'gm'`
- **originalroute** values: `'Intravenous Push'`, `'IV Drip'`, `'Intravenous'`, `'Gastric/Feeding Tube'`, `'Nasogastric'`, `'Intravenous Infusion'`, `'By Mouth'`, `'Oral'`, `'Drip'`, `'GU'`, `'IV Piggyback'`, `'Oral or Nasogastric'`
- **originalrateuom** values: `'ml/hr'`
- **originalsite** values: `'PO / NG'`, `'Right Int. Jugular'`, `'Right Arm'`, `'UVC'`, `'Left Arm'`, `'Left Subclavian'`, `'Right Subclavian'`, `'Percutaneous Cath'`, `'Left Int. Jugular'`, `'Right Hand'`, `'UAC'`, `'Right Femoral'`, `'Left Hand'`, `'Left Femoral'`, `'Umb Venous Primary'` ...

## microbiologyevents

Microbiology tests: specimens, organisms grown, and antibiotic sensitivities.

Kind: event. Rows: 631,726. Key: none (row_id is only a row number). Rules for the whole table: group.exact_duplicates.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 693,257 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 36,841 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 46,002 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| chartdate | TIMESTAMP | time | 0 | 31,871 |  | Date of the test |
| charttime | TIMESTAMP | time | 6.612 | 283,403 |  | Time of the test (may be null) |
| spec_itemid | INTEGER | reference | 0.013 | 102 | d_items.itemid | Specimen item |
| spec_type_desc | VARCHAR | text | 0 | 88 |  | Specimen type, uppercase, e.g. 'BLOOD CULTURE', 'URINE', 'SPUTUM' |
| org_itemid | INTEGER | reference | 48.256 | 337 | d_items.itemid | Organism item |
| org_name | VARCHAR | text | 48.076 | 442 |  | Organism grown, uppercase, e.g. 'STAPH AUREUS COAG +', 'ESCHERICHIA COLI'; null means no growth |
| isolate_num | SMALLINT | category | 48.076 | 6 |  | Isolate number |
| ab_itemid | INTEGER | reference | 56.336 | 27 | d_items.itemid | Antibiotic item |
| ab_name | VARCHAR | category | 56.336 | 29 |  | Antibiotic tested, uppercase, e.g. 'VANCOMYCIN', 'OXACILLIN' |
| dilution_text | VARCHAR | category | 57.679 | 42 |  | Dilution as text |
| dilution_comparison | VARCHAR | category | 57.707 | 3 |  | Comparison operator for the dilution |
| dilution_value | DOUBLE | number | 57.707 | 18 |  | Dilution value |
| interpretation | VARCHAR | category | 56.336 | 3 |  | Sensitivity: 'S' (sensitive), 'R' (resistant), 'I' (intermediate), 'P' (pending) |

- **chartdate** rules: group.outside_admission, quirk.microbiologyevents.date_only
- **charttime** rules: quirk.microbiologyevents.date_only
- **org_name** rules: quirk.microbiologyevents.no_organism, group.padded_text
- **isolate_num** values: `'1'`, `'2'`, `'3'`, `'4'`, `'5'` ...
- **ab_name** values: `'GENTAMICIN'`, `'LEVOFLOXACIN'`, `'CEFTAZIDIME'`, `'TOBRAMYCIN'`, `'TRIMETHOPRIM/SULFA'`, `'CEFEPIME'`, `'MEROPENEM'`, `'VANCOMYCIN'`, `'OXACILLIN'`, `'CIPROFLOXACIN'`, `'PIPERACILLIN/TAZO'`, `'ERYTHROMYCIN'`, `'CEFTRIAXONE'`, `'AMPICILLIN'`, `'TETRACYCLINE'` ...
- **dilution_text** values: `'<=1'`, `'<=0.25'`, `'=>8'`, `'<=0.5'`, `'<=4'`, `'=>4'`, `'2'`, `'4'`, `'=>16'`, `'=>32'`, `'8'`, `'=>0.5'`, `'=>64'`, `'<=2'`, `'16'` ...
- **dilution_comparison** values: `'<='`, `'=>'`, `'='`
- **interpretation** values: `'S'`, `'R'`, `'I'` ...

## patients

One row per patient: gender, date of birth, and dates of death.

Kind: core. Rows: 46,520. Key: subject_id.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 42,058 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | identifier | 0 | 40,543 |  | Patient identifier (PATIENTS) |
| gender | VARCHAR | category | 0 | 2 |  | 'M' or 'F' |
| dob | TIMESTAMP | time | 0 | 41,606 |  | Date of birth (shifted). Patients older than 89 at their first admission have DOB shifted so that their age appears as about 300 years |
| dod | TIMESTAMP | time | 66.124 | 11,569 |  | Date of death from any source (hospital or social security records); null if not known to have died |
| dod_hosp | TIMESTAMP | time | 78.56 | 7,925 |  | Date of death recorded in the hospital database |
| dod_ssn | TIMESTAMP | time | 71.242 | 11,225 |  | Date of death from the social security database |
| expire_flag | INTEGER | flag | 0 | 2 |  | 1 if the patient has died (dod is not null), else 0 |

- **gender** values: `'M'`, `'F'`
- **dob** rules: temporal.patients.age_over_89_shifted
- **expire_flag** values: `'0'`, `'1'`

## prescriptions

Medication orders (not confirmed administration): drug, dose, route, and dates.

Kind: event. Rows: 4,156,450. Key: none (row_id is only a row number). Rules for the whole table: group.exact_duplicates.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 3,886,673 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 36,398 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 47,915 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | reference | 34.83 | 58,981 | icustays.icustay_id | ICU stay identifier if ordered in the ICU |
| startdate | TIMESTAMP | time | 0.077 | 34,409 |  | Order start date |
| enddate | TIMESTAMP | time | 0.13 | 33,737 |  | Order end date |
| drug_type | VARCHAR | category | 0 | 3 |  | 'MAIN', 'BASE', or 'ADDITIVE' |
| drug | VARCHAR | text | 0 | 4,406 |  | Drug name as ordered (free text, mixed case) |
| drug_name_poe | VARCHAR | text | 40.04 | 3,977 |  | Drug name in the order entry system |
| drug_name_generic | VARCHAR | text | 40.01 | 2,842 |  | Generic drug name |
| formulary_drug_cd | VARCHAR | code | 0.047 | 3,047 |  | Hospital formulary code |
| gsn | VARCHAR | code | 12.202 | 3,092 |  | Generic Sequence Number |
| ndc | VARCHAR | code | 0.107 | 3,964 |  | National Drug Code |
| prod_strength | VARCHAR | text | 0.033 | 4,170 |  | Product strength |
| dose_val_rx | VARCHAR | text | 0.032 | 2,712 |  | Prescribed dose |
| dose_unit_rx | VARCHAR | text | 0.032 | 122 |  | Unit of the dose |
| form_val_disp | VARCHAR | text | 0.033 | 3,372 |  | Amount dispensed |
| form_unit_disp | VARCHAR | text | 0.034 | 100 |  | Unit dispensed |
| route | VARCHAR | text | 0.028 | 79 |  | Route, e.g. 'PO', 'IV' |

- **hadm_id** rules: group.icustay_hadm_mismatch
- **icustay_id** rules: group.icustay_hadm_mismatch
- **startdate** rules: group.negative_duration, group.outside_admission
- **enddate** rules: group.negative_duration
- **drug_type** values: `'MAIN'`, `'BASE'`, `'ADDITIVE'`
- **drug** rules: quirk.prescriptions.ndc_unusable, group.padded_text
- **drug_name_poe** rules: group.padded_text
- **drug_name_generic** rules: group.padded_text
- **gsn** rules: group.padded_text
- **ndc** rules: quirk.prescriptions.ndc_unusable
- **prod_strength** rules: group.padded_text
- **dose_val_rx** rules: group.padded_text
- **form_val_disp** rules: group.padded_text

## procedureevents_mv

Procedures documented in the ICU (MetaVision patients only, 2008-2012), e.g. ventilation, dialysis, line insertion, imaging, with start and end times.

Kind: event. Rows: 258,066. Key: none (row_id is only a row number). Rules for the whole table: quirk.icustays.without_procedureevents.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 221,234 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 16,739 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 22,152 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | reference | 0.034 | 22,842 | icustays.icustay_id | ICU stay identifier (ICUSTAYS) |
| starttime | TIMESTAMP | time | 0 | 183,584 |  | Procedure start time |
| endtime | TIMESTAMP | time | 0 | 171,796 |  | Procedure end time |
| itemid | INTEGER | reference | 0 | 141 | d_items.itemid | Procedure item (names in d_items, linksto = 'procedureevents_mv') |
| value | DOUBLE | number | 0 | 14,369 |  | Amount or duration |
| valueuom | VARCHAR | category | 0 | 4 |  | Unit of value, e.g. 'min', 'None' |
| location | VARCHAR | text | 79.613 | 111 |  | Body location |
| locationcategory | VARCHAR | category | 79.613 | 7 |  | Location category |
| storetime | TIMESTAMP | time | 0 | 191,861 |  | Time the event was recorded |
| cgid | INTEGER | reference | 0 | 964 | caregivers.cgid | Caregiver identifier (CAREGIVERS) |
| orderid | INTEGER | local_identifier | 0 | 288,927 |  | Order identifier |
| linkorderid | INTEGER | local_identifier | 0 | 288,927 |  | Links related orders |
| ordercategoryname | VARCHAR | category | 0 | 11 |  | Order category |
| secondaryordercategoryname | VARCHAR | always_null | 100 | 0 |  | Secondary order category |
| ordercategorydescription | VARCHAR | category | 0 | 2 |  | Order type description |
| isopenbag | SMALLINT | flag | 0 | 2 |  | Open bag flag |
| continueinnextdept | SMALLINT | flag | 0 | 2 |  | Continued in the next department |
| cancelreason | SMALLINT | category | 0 | 3 |  | Cancellation reason code |
| statusdescription | VARCHAR | category | 0 | 3 |  | Status, e.g. 'FinishedRunning', 'Stopped' |
| comments_editedby | VARCHAR | category | 99.189 | 6 |  | Editor role |
| comments_canceledby | VARCHAR | category | 97.796 | 18 |  | Canceller role |
| comments_date | TIMESTAMP | time | 96.984 | 5,973 |  | Comment time |

- **icustay_id** rules: group.dbsource_crossover
- **starttime** rules: group.negative_duration, group.outside_admission
- **endtime** rules: group.negative_duration
- **valueuom** values: `'None'`, `'min'`, `'day'`, `'hour'`
- **location** rules: group.padded_text
- **locationcategory** values: `'Peripheral'`, `'Invasive Venous'`, `'Invasive Arterial'`, `'Peripheral - old'`, `'Dialysis'`, `'ICP Line'`, `'Peritoneal Dialysis'`, `'Intraosseous'`
- **ordercategoryname** values: `'Procedures'`, `'Peripheral Lines'`, `'Imaging'`, `'Invasive Lines'`, `'Intubation/Extubation'`, `'Ventilation'`, `'Significant Events'`, `'Communication'`, `'Continuous Procedures'`, `'Dialysis'`, `'Peritoneal Dialysis'`, `'CRRT Filter Change'`
- **secondaryordercategoryname** rules: group.all_null
- **ordercategorydescription** values: `'Electrolytes'`, `'Task'`
- **isopenbag** values: `'0'`, `'1'`
- **continueinnextdept** values: `'0'`, `'1'`
- **cancelreason** values: `'0'`, `'1'`, `'2'`
- **statusdescription** values: `'FinishedRunning'`, `'Rewritten'`, `'Stopped'`, `'Paused'`
- **statusdescription** rules: quirk.procedureevents_mv.rewritten
- **comments_editedby** values: `'RN'`, `'RRT'` ...
- **comments_canceledby** values: `'RN'`, `'RRT'`, `'MD'`, `'Unknown'`, `'CRTT'`, `'RT'` ...

## procedures_icd

ICD-9 procedure codes for each admission, ordered by sequence.

Kind: event. Rows: 240,095. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 213,666 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 39,614 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 42,982 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| seq_num | INTEGER | number | 0 | 41 |  | Order of the procedure within the admission |
| icd9_code | VARCHAR | code | 0 | 2,229 | d_icd_procedures.icd9_code | ICD-9-CM procedure code WITHOUT the dot: 36.10 is '3610', 96.71 is '9671' |

- **hadm_id** rules: group.repeated_within_admission
- **icd9_code** rules: group.repeated_within_admission, group.dictionary_gap, group.icd9_format

## services

Clinical service the patient was under during an admission (e.g. medicine, surgery), with the time of each service change.

Kind: event. Rows: 73,343. Key: none (row_id is only a row number).

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 63,228 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 57,608 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| transfertime | TIMESTAMP | time | 0 | 68,326 |  | Time the patient moved to the current service |
| prev_service | VARCHAR | category | 80.001 | 18 |  | Previous service (null for the first one) |
| curr_service | VARCHAR | category | 0 | 21 |  | Service code: 'MED' (medicine), 'SURG' (surgery), 'CMED' (cardiac medical), 'CSURG' (cardiac surgery), 'NSURG' (neurosurgery), 'NMED' (neurology), 'TRAUM' (trauma), 'ORTHO' (orthopedics), 'VSURG' (vascular), 'TSURG' (thoracic), 'PSURG' (plastic), 'GU' (urology), 'GYN', 'OBS', 'ENT', 'DENT', 'OMED' (oncology), 'PSYCH', 'NB' (newborn), 'NBB' (newborn baby) |

- **transfertime** rules: group.outside_admission
- **prev_service** values: `'MED'`, `'CMED'`, `'OMED'`, `'SURG'`, `'NSURG'`, `'TRAUM'`, `'NMED'`, `'ORTHO'`, `'CSURG'`, `'VSURG'`, `'TSURG'`, `'GU'`, `'GYN'`, `'ENT'`, `'PSURG'` ...
- **curr_service** values: `'MED'`, `'CMED'`, `'CSURG'`, `'NB'`, `'SURG'`, `'NSURG'`, `'TRAUM'`, `'NMED'`, `'OMED'`, `'VSURG'`, `'TSURG'`, `'ORTHO'`, `'GU'`, `'NBB'`, `'GYN'` ...

## transfers

Patient movements between hospital units and beds during an admission, including ICU admission and discharge events.

Kind: event. Rows: 261,897. Key: none (row_id is only a row number). Rules for the whole table: group.exact_duplicates.

| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |
|---|---|---|---:|---:|---|---|
| row_id | INTEGER | row_number | 0 | 223,275 |  | Row number within this table; not an identifier, never use it for joins |
| subject_id | INTEGER | reference | 0 | 40,543 | patients.subject_id | Patient identifier (PATIENTS) |
| hadm_id | INTEGER | reference | 0 | 57,608 | admissions.hadm_id | Hospital admission identifier (ADMISSIONS) |
| icustay_id | INTEGER | reference | 66.506 | 64,481 | icustays.icustay_id | ICU stay identifier when the movement is part of an ICU stay; else null |
| dbsource | VARCHAR | category | 0.092 | 3 |  | 'carevue' or 'metavision' |
| eventtype | VARCHAR | category | 0.009 | 3 |  | 'admit', 'transfer', or 'discharge' |
| prev_careunit | VARCHAR | category | 63.341 | 7 |  | Previous ICU type (null for non-ICU wards) |
| curr_careunit | VARCHAR | category | 63.338 | 7 |  | Current ICU type: 'MICU', 'SICU', 'CCU', 'CSRU', 'TSICU', 'NICU'; null for non-ICU wards |
| prev_wardid | SMALLINT | local_identifier | 22.502 | 53 |  | Previous ward identifier |
| curr_wardid | SMALLINT | local_identifier | 22.506 | 53 |  | Current ward identifier |
| intime | TIMESTAMP | time | 0.009 | 261,758 |  | Time the patient entered the current unit |
| outtime | TIMESTAMP | time | 22.519 | 209,166 |  | Time the patient left the current unit |
| los | DOUBLE | number | 22.519 | 36,909 |  | Length of stay in the current unit, in hours |

- **dbsource** values: `'carevue'`, `'metavision'`, `'both'`
- **eventtype** values: `'transfer'`, `'discharge'`, `'admit'`
- **prev_careunit** values: `'MICU'`, `'NICU'`, `'CSRU'`, `'SICU'`, `'CCU'`, `'NWARD'`, `'TSICU'`
- **curr_careunit** values: `'MICU'`, `'NICU'`, `'CSRU'`, `'SICU'`, `'CCU'`, `'NWARD'`, `'TSICU'`
- **intime** rules: group.outside_admission

## Links between tables

Documented links (joins), with how many rows were checked and how many found no match.

| From | To | Kind | Rows checked | Unmatched | Unmatched % | Rows without the key |
|---|---|---|---:|---:|---:|---:|
| admissions.subject_id | patients.subject_id | key | 58,976 | 0 | 0 | 0 |
| callout.hadm_id | admissions.hadm_id | key | 34,499 | 0 | 0 | 0 |
| callout.subject_id | patients.subject_id | key | 34,499 | 0 | 0 | 0 |
| cptevents.hadm_id | admissions.hadm_id | key | 573,146 | 0 | 0 | 0 |
| cptevents.subject_id | patients.subject_id | key | 573,146 | 0 | 0 | 0 |
| datetimeevents.cgid | caregivers.cgid | key | 4,485,937 | 0 | 0 | 0 |
| datetimeevents.hadm_id | admissions.hadm_id | key | 4,484,165 | 0 | 0 | 1,772 |
| datetimeevents.icustay_id | icustays.icustay_id | key | 4,481,781 | 0 | 0 | 4,156 |
| datetimeevents.itemid | d_items.itemid | dictionary | 4,485,937 | 0 | 0 | 0 |
| datetimeevents.subject_id | patients.subject_id | key | 4,485,937 | 0 | 0 | 0 |
| diagnoses_icd.hadm_id | admissions.hadm_id | key | 651,047 | 0 | 0 | 0 |
| diagnoses_icd.icd9_code | d_icd_diagnoses.icd9_code | dictionary | 651,000 | 16,291 | 2.502 | 47 |
| diagnoses_icd.subject_id | patients.subject_id | key | 651,047 | 0 | 0 | 0 |
| drgcodes.hadm_id | admissions.hadm_id | key | 125,557 | 0 | 0 | 0 |
| drgcodes.subject_id | patients.subject_id | key | 125,557 | 0 | 0 | 0 |
| icustays.hadm_id | admissions.hadm_id | key | 61,532 | 0 | 0 | 0 |
| icustays.subject_id | patients.subject_id | key | 61,532 | 0 | 0 | 0 |
| inputevents_cv.cgid | caregivers.cgid | key | 17,173,928 | 0 | 0 | 354,007 |
| inputevents_cv.hadm_id | admissions.hadm_id | key | 17,505,266 | 0 | 0 | 22,669 |
| inputevents_cv.icustay_id | icustays.icustay_id | key | 17,497,482 | 0 | 0 | 30,453 |
| inputevents_cv.itemid | d_items.itemid | dictionary | 17,527,935 | 0 | 0 | 0 |
| inputevents_cv.subject_id | patients.subject_id | key | 17,527,935 | 0 | 0 | 0 |
| microbiologyevents.ab_itemid | d_items.itemid | dictionary | 275,834 | 0 | 0 | 355,892 |
| microbiologyevents.hadm_id | admissions.hadm_id | key | 631,726 | 0 | 0 | 0 |
| microbiologyevents.org_itemid | d_items.itemid | dictionary | 326,881 | 0 | 0 | 304,845 |
| microbiologyevents.spec_itemid | d_items.itemid | dictionary | 631,647 | 0 | 0 | 79 |
| microbiologyevents.subject_id | patients.subject_id | key | 631,726 | 0 | 0 | 0 |
| prescriptions.hadm_id | admissions.hadm_id | key | 4,156,450 | 0 | 0 | 0 |
| prescriptions.icustay_id | icustays.icustay_id | key | 2,708,742 | 0 | 0 | 1,447,708 |
| prescriptions.subject_id | patients.subject_id | key | 4,156,450 | 0 | 0 | 0 |
| procedureevents_mv.cgid | caregivers.cgid | key | 258,066 | 0 | 0 | 0 |
| procedureevents_mv.hadm_id | admissions.hadm_id | key | 258,066 | 0 | 0 | 0 |
| procedureevents_mv.icustay_id | icustays.icustay_id | key | 257,978 | 0 | 0 | 88 |
| procedureevents_mv.itemid | d_items.itemid | dictionary | 258,066 | 0 | 0 | 0 |
| procedureevents_mv.subject_id | patients.subject_id | key | 258,066 | 0 | 0 | 0 |
| procedures_icd.hadm_id | admissions.hadm_id | key | 240,095 | 0 | 0 | 0 |
| procedures_icd.icd9_code | d_icd_procedures.icd9_code | dictionary | 240,095 | 2,147 | 0.894 | 0 |
| procedures_icd.subject_id | patients.subject_id | key | 240,095 | 0 | 0 | 0 |
| services.hadm_id | admissions.hadm_id | key | 73,343 | 0 | 0 | 0 |
| services.subject_id | patients.subject_id | key | 73,343 | 0 | 0 | 0 |
| transfers.hadm_id | admissions.hadm_id | key | 261,897 | 0 | 0 | 0 |
| transfers.icustay_id | icustays.icustay_id | key | 87,721 | 0 | 0 | 174,176 |
| transfers.subject_id | patients.subject_id | key | 261,897 | 0 | 0 | 0 |
