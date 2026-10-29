# MIMIC-III v1.4 data quality report

> **Shared snapshot - do not edit by hand.** Regenerated only by the dataset maintainer with `python scripts/prepare_mimic3.py publish`; everyone else treats this file as read-only. Counts from 1 to 10 are shown as `<11`.

Data fingerprint `55cb7586f72a` (rows per table: admissions 58,976, callout 34,499, caregivers 7,567, cptevents 573,146, d_cpt 134, d_icd_diagnoses 14,567, d_icd_procedures 3,882, d_items 12,487, d_labitems 753, datetimeevents 4,485,937, diagnoses_icd 651,047, drgcodes 125,557, icustays 61,532, inputevents_cv 17,527,935, microbiologyevents 631,726, patients 46,520, prescriptions 4,156,450, procedureevents_mv 258,066, procedures_icd 240,095, services 73,343, transfers 261,897).

MIMIC-III v1.4 is a de-identified database of patients admitted to intensive care units at Beth Israel Deaconess Medical Center, Boston (2001-2012). This report checks the copy loaded for this project for data problems that can make a database query give a wrong answer.

The data were **not modified**. Instead, each problem found is turned into a **query convention**: a plain-language rule for writing queries (SQL) that avoid the problem, listed in the last section and in `mimic3_query_conventions.json`. The report contains aggregate counts only, never information about individual patients. Produced by `python scripts/prepare_mimic3.py publish`.

Checks: 154 (pass 95, flagged 9, informational 50, errors 0). **pass**: expected zero and found zero. **flag**: expected zero, found some. **info**: a measured count with no single correct value.

## Keys and duplicates

Is each identifier unique where it should be, and are there repeated rows?

| Check | Status | Flagged | Total | % | Details |
|---|---|---:|---:|---:|---|
| admissions.row_id is unique | pass | 0 | 58,976 | 0 |  |
| callout.row_id is unique | pass | 0 | 34,499 | 0 |  |
| caregivers.row_id is unique | pass | 0 | 7,567 | 0 |  |
| cptevents.row_id is unique | pass | 0 | 573,146 | 0 |  |
| d_cpt.row_id is unique | pass | 0 | 134 | 0 |  |
| d_icd_diagnoses.row_id is unique | pass | 0 | 14,567 | 0 |  |
| d_icd_procedures.row_id is unique | pass | 0 | 3,882 | 0 |  |
| d_items.row_id is unique | pass | 0 | 12,487 | 0 |  |
| d_labitems.row_id is unique | pass | 0 | 753 | 0 |  |
| datetimeevents.row_id is unique | pass | 0 | 4,485,937 | 0 |  |
| diagnoses_icd.row_id is unique | pass | 0 | 651,047 | 0 |  |
| drgcodes.row_id is unique | pass | 0 | 125,557 | 0 |  |
| icustays.row_id is unique | pass | 0 | 61,532 | 0 |  |
| inputevents_cv.row_id is unique | pass | 0 | 17,527,935 | 0 |  |
| microbiologyevents.row_id is unique | pass | 0 | 631,726 | 0 |  |
| patients.row_id is unique | pass | 0 | 46,520 | 0 |  |
| prescriptions.row_id is unique | pass | 0 | 4,156,450 | 0 |  |
| procedureevents_mv.row_id is unique | pass | 0 | 258,066 | 0 |  |
| procedures_icd.row_id is unique | pass | 0 | 240,095 | 0 |  |
| services.row_id is unique | pass | 0 | 73,343 | 0 |  |
| transfers.row_id is unique | pass | 0 | 261,897 | 0 |  |
| patients.subject_id is unique (primary key) | pass | 0 | 46,520 | 0 | null_keys=0 |
| admissions.hadm_id is unique (primary key) | pass | 0 | 58,976 | 0 | null_keys=0 |
| icustays.icustay_id is unique (primary key) | pass | 0 | 61,532 | 0 | null_keys=0 |
| caregivers.cgid is unique (primary key) | pass | 0 | 7,567 | 0 | null_keys=0 |
| d_items.itemid is unique (primary key) | pass | 0 | 12,487 | 0 | null_keys=0 |
| d_labitems.itemid is unique (primary key) | pass | 0 | 753 | 0 | null_keys=0 |
| d_icd_diagnoses.icd9_code is unique (primary key) | pass | 0 | 14,567 | 0 | null_keys=0 |
| d_icd_procedures.icd9_code is unique (primary key) | pass | 0 | 3,882 | 0 | null_keys=0 |
| Two diagnoses share a priority within one admission (diagnoses_icd: hadm_id,seq_num) | info | 0 | 651,047 | 0 |  |
| Same ICD-9 diagnosis coded twice in one admission (diagnoses_icd: hadm_id,icd9_code) | info | 60 | 651,047 | 0.009 |  |
| Two procedures share a priority within one admission (procedures_icd: hadm_id,seq_num) | info | 0 | 240,095 | 0 |  |
| Same ICD-9 procedure coded twice in one admission (procedures_icd: hadm_id,icd9_code) | info | 11,416 | 240,095 | 4.755 |  |
| More than one DRG of the same type per admission (drgcodes: hadm_id,drg_type) | info | 27,272 | 125,557 | 21.721 |  |
| admissions: rows identical to another row except row_id | info | 0 | 58,976 | 0 |  |
| callout: rows identical to another row except row_id | info | 0 | 34,499 | 0 |  |
| cptevents: rows identical to another row except row_id | info | 0 | 573,146 | 0 |  |
| datetimeevents: rows identical to another row except row_id | info | 0 | 4,485,937 | 0 |  |
| diagnoses_icd: rows identical to another row except row_id | info | 0 | 651,047 | 0 |  |
| drgcodes: rows identical to another row except row_id | info | 25,233 | 125,557 | 20.097 |  |
| icustays: rows identical to another row except row_id | info | 0 | 61,532 | 0 |  |
| inputevents_cv: rows identical to another row except row_id | info | 9,418 | 17,527,935 | 0.054 |  |
| microbiologyevents: rows identical to another row except row_id | info | 18,414 | 631,726 | 2.915 |  |
| patients: rows identical to another row except row_id | info | 0 | 46,520 | 0 |  |
| prescriptions: rows identical to another row except row_id | info | 236,244 | 4,156,450 | 5.684 |  |
| procedureevents_mv: rows identical to another row except row_id | info | 0 | 258,066 | 0 |  |
| procedures_icd: rows identical to another row except row_id | info | 0 | 240,095 | 0 |  |
| services: rows identical to another row except row_id | info | 0 | 73,343 | 0 |  |
| transfers: rows identical to another row except row_id | info | 40 | 261,897 | 0.015 |  |

## Referential integrity

Does every key in an event table exist in its parent or dictionary table?

| Check | Status | Flagged | Total | % | Details |
|---|---|---:|---:|---:|---|
| admissions.subject_id values found in patients.subject_id | pass | 0 | 58,976 | 0 | null_keys=0, distinct_unmatched=0 |
| callout.subject_id values found in patients.subject_id | pass | 0 | 34,499 | 0 | null_keys=0, distinct_unmatched=0 |
| callout.hadm_id values found in admissions.hadm_id | pass | 0 | 34,499 | 0 | null_keys=0, distinct_unmatched=0 |
| cptevents.subject_id values found in patients.subject_id | pass | 0 | 573,146 | 0 | null_keys=0, distinct_unmatched=0 |
| cptevents.hadm_id values found in admissions.hadm_id | pass | 0 | 573,146 | 0 | null_keys=0, distinct_unmatched=0 |
| datetimeevents.subject_id values found in patients.subject_id | pass | 0 | 4,485,937 | 0 | null_keys=0, distinct_unmatched=0 |
| datetimeevents.hadm_id values found in admissions.hadm_id | pass | 0 | 4,484,165 | 0 | null_keys=1,772, distinct_unmatched=0 |
| datetimeevents.icustay_id values found in icustays.icustay_id | pass | 0 | 4,481,781 | 0 | null_keys=4,156, distinct_unmatched=0 |
| datetimeevents.cgid values found in caregivers.cgid | pass | 0 | 4,485,937 | 0 | null_keys=0, distinct_unmatched=0 |
| diagnoses_icd.subject_id values found in patients.subject_id | pass | 0 | 651,047 | 0 | null_keys=0, distinct_unmatched=0 |
| diagnoses_icd.hadm_id values found in admissions.hadm_id | pass | 0 | 651,047 | 0 | null_keys=0, distinct_unmatched=0 |
| drgcodes.subject_id values found in patients.subject_id | pass | 0 | 125,557 | 0 | null_keys=0, distinct_unmatched=0 |
| drgcodes.hadm_id values found in admissions.hadm_id | pass | 0 | 125,557 | 0 | null_keys=0, distinct_unmatched=0 |
| icustays.subject_id values found in patients.subject_id | pass | 0 | 61,532 | 0 | null_keys=0, distinct_unmatched=0 |
| icustays.hadm_id values found in admissions.hadm_id | pass | 0 | 61,532 | 0 | null_keys=0, distinct_unmatched=0 |
| inputevents_cv.subject_id values found in patients.subject_id | pass | 0 | 17,527,935 | 0 | null_keys=0, distinct_unmatched=0 |
| inputevents_cv.hadm_id values found in admissions.hadm_id | pass | 0 | 17,505,266 | 0 | null_keys=22,669, distinct_unmatched=0 |
| inputevents_cv.icustay_id values found in icustays.icustay_id | pass | 0 | 17,497,482 | 0 | null_keys=30,453, distinct_unmatched=0 |
| inputevents_cv.cgid values found in caregivers.cgid | pass | 0 | 17,173,928 | 0 | null_keys=354,007, distinct_unmatched=0 |
| microbiologyevents.subject_id values found in patients.subject_id | pass | 0 | 631,726 | 0 | null_keys=0, distinct_unmatched=0 |
| microbiologyevents.hadm_id values found in admissions.hadm_id | pass | 0 | 631,726 | 0 | null_keys=0, distinct_unmatched=0 |
| prescriptions.subject_id values found in patients.subject_id | pass | 0 | 4,156,450 | 0 | null_keys=0, distinct_unmatched=0 |
| prescriptions.hadm_id values found in admissions.hadm_id | pass | 0 | 4,156,450 | 0 | null_keys=0, distinct_unmatched=0 |
| prescriptions.icustay_id values found in icustays.icustay_id | pass | 0 | 2,708,742 | 0 | null_keys=1,447,708, distinct_unmatched=0 |
| procedureevents_mv.subject_id values found in patients.subject_id | pass | 0 | 258,066 | 0 | null_keys=0, distinct_unmatched=0 |
| procedureevents_mv.hadm_id values found in admissions.hadm_id | pass | 0 | 258,066 | 0 | null_keys=0, distinct_unmatched=0 |
| procedureevents_mv.icustay_id values found in icustays.icustay_id | pass | 0 | 257,978 | 0 | null_keys=88, distinct_unmatched=0 |
| procedureevents_mv.cgid values found in caregivers.cgid | pass | 0 | 258,066 | 0 | null_keys=0, distinct_unmatched=0 |
| procedures_icd.subject_id values found in patients.subject_id | pass | 0 | 240,095 | 0 | null_keys=0, distinct_unmatched=0 |
| procedures_icd.hadm_id values found in admissions.hadm_id | pass | 0 | 240,095 | 0 | null_keys=0, distinct_unmatched=0 |
| services.subject_id values found in patients.subject_id | pass | 0 | 73,343 | 0 | null_keys=0, distinct_unmatched=0 |
| services.hadm_id values found in admissions.hadm_id | pass | 0 | 73,343 | 0 | null_keys=0, distinct_unmatched=0 |
| transfers.subject_id values found in patients.subject_id | pass | 0 | 261,897 | 0 | null_keys=0, distinct_unmatched=0 |
| transfers.hadm_id values found in admissions.hadm_id | pass | 0 | 261,897 | 0 | null_keys=0, distinct_unmatched=0 |
| transfers.icustay_id values found in icustays.icustay_id | pass | 0 | 87,721 | 0 | null_keys=174,176, distinct_unmatched=0 |
| datetimeevents.itemid values found in d_items.itemid | info | 0 | 4,485,937 | 0 | null_keys=0, distinct_unmatched=0 |
| inputevents_cv.itemid values found in d_items.itemid | info | 0 | 17,527,935 | 0 | null_keys=0, distinct_unmatched=0 |
| procedureevents_mv.itemid values found in d_items.itemid | info | 0 | 258,066 | 0 | null_keys=0, distinct_unmatched=0 |
| microbiologyevents.spec_itemid values found in d_items.itemid | info | 0 | 631,647 | 0 | null_keys=79, distinct_unmatched=0 |
| microbiologyevents.org_itemid values found in d_items.itemid | info | 0 | 326,881 | 0 | null_keys=304,845, distinct_unmatched=0 |
| microbiologyevents.ab_itemid values found in d_items.itemid | info | 0 | 275,834 | 0 | null_keys=355,892, distinct_unmatched=0 |
| diagnoses_icd.icd9_code values found in d_icd_diagnoses.icd9_code | info | 16,291 | 651,000 | 2.502 | null_keys=47, distinct_unmatched=143 |
| procedures_icd.icd9_code values found in d_icd_procedures.icd9_code | info | 2,147 | 240,095 | 0.894 | null_keys=0, distinct_unmatched=16 |
| callout: subject_id agrees with admissions for the same hadm_id | pass | 0 | 34,499 | 0 |  |
| cptevents: subject_id agrees with admissions for the same hadm_id | pass | 0 | 573,146 | 0 |  |
| datetimeevents: subject_id agrees with admissions for the same hadm_id | pass | 0 | 4,484,165 | 0 |  |
| datetimeevents: hadm_id agrees with icustays for the same icustay_id | flag | 408 | 4,481,781 | 0.009 | event_hadm_null=342 |
| diagnoses_icd: subject_id agrees with admissions for the same hadm_id | pass | 0 | 651,047 | 0 |  |
| drgcodes: subject_id agrees with admissions for the same hadm_id | pass | 0 | 125,557 | 0 |  |
| icustays: subject_id agrees with admissions for the same hadm_id | pass | 0 | 61,532 | 0 |  |
| inputevents_cv: subject_id agrees with admissions for the same hadm_id | pass | 0 | 17,505,266 | 0 |  |
| inputevents_cv: hadm_id agrees with icustays for the same icustay_id | flag | 4,314 | 17,497,482 | 0.025 | event_hadm_null=6,270 |
| microbiologyevents: subject_id agrees with admissions for the same hadm_id | pass | 0 | 631,726 | 0 |  |
| prescriptions: subject_id agrees with admissions for the same hadm_id | pass | 0 | 4,156,450 | 0 |  |
| prescriptions: hadm_id agrees with icustays for the same icustay_id | flag | 607 | 2,708,742 | 0.022 | event_hadm_null=0 |
| procedureevents_mv: subject_id agrees with admissions for the same hadm_id | pass | 0 | 258,066 | 0 |  |
| procedureevents_mv: hadm_id agrees with icustays for the same icustay_id | pass | 0 | 257,978 | 0 | event_hadm_null=0 |
| procedures_icd: subject_id agrees with admissions for the same hadm_id | pass | 0 | 240,095 | 0 |  |
| services: subject_id agrees with admissions for the same hadm_id | pass | 0 | 73,343 | 0 |  |
| transfers: subject_id agrees with admissions for the same hadm_id | pass | 0 | 261,897 | 0 |  |
| transfers: hadm_id agrees with icustays for the same icustay_id | pass | 0 | 87,721 | 0 | event_hadm_null=0 |
| datetimeevents items are labeled LINKSTO='datetimeevents' in d_items | pass | 0 | 4,485,937 | 0 |  |
| inputevents_cv items are labeled LINKSTO='inputevents_cv' in d_items | pass | 0 | 17,527,935 | 0 |  |
| procedureevents_mv items are labeled LINKSTO='procedureevents_mv' in d_items | pass | 0 | 258,066 | 0 |  |

## Temporal consistency

Do end times follow start times, and do events fall inside their admission?

| Check | Status | Flagged | Total | % | Details |
|---|---|---:|---:|---:|---|
| admissions: dischtime earlier than admittime | flag | 98 | 58,976 | 0.166 | within_24h=98, died_in_hospital=80 |
| admissions: edouttime earlier than edregtime | flag | 17 | 30,877 | 0.055 | within_24h=16, died_in_hospital=<11 |
| icustays: outtime earlier than intime | pass | 0 | 61,522 | 0 | within_24h=0 |
| transfers: outtime earlier than intime | pass | 0 | 202,921 | 0 | within_24h=0 |
| prescriptions: enddate earlier than startdate | flag | 15,922 | 4,150,832 | 0.384 | within_24h=11,154 |
| procedureevents_mv: endtime earlier than starttime | flag | 62 | 258,066 | 0.024 | within_24h=62 |
| callout: outcometime earlier than createtime | pass | 0 | 34,499 | 0 | within_24h=0 |
| patients: dod earlier than dob | pass | 0 | 15,759 | 0 | within_24h=0 |
| callout.createtime outside its admission [admittime, dischtime] | info | 36 | 34,499 | 0.104 | beyond_24h=0 |
| cptevents.chartdate outside its admission [admittime, dischtime] (by date) | info | 0 | 101,545 | 0 | beyond_24h=0 |
| datetimeevents.charttime outside its admission [admittime, dischtime] | info | 11,046 | 4,484,165 | 0.246 | beyond_24h=377 |
| inputevents_cv.charttime outside its admission [admittime, dischtime] | info | 43,596 | 17,505,266 | 0.249 | beyond_24h=0 |
| microbiologyevents.chartdate outside its admission [admittime, dischtime] (by date) | info | 1,655 | 631,726 | 0.262 | beyond_24h=604 |
| prescriptions.startdate outside its admission [admittime, dischtime] (by date) | info | 4,897 | 4,153,268 | 0.118 | beyond_24h=2,378 |
| procedureevents_mv.starttime outside its admission [admittime, dischtime] | info | 1,049 | 258,066 | 0.406 | beyond_24h=52 |
| services.transfertime outside its admission [admittime, dischtime] | info | 6,898 | 73,343 | 9.405 | beyond_24h=53 |
| transfers.intime outside its admission [admittime, dischtime] | info | 57,849 | 261,873 | 22.09 | beyond_24h=432 |
| admissions.deathtime outside [admittime, dischtime] | info | 126 | 5,854 | 2.152 | beyond_24h=13 |
| hospital_expire_flag disagrees with deathtime being recorded | pass | 0 | 58,976 | 0 | flag_without_time=0, time_without_flag=0 |
| discharge_location 'DEAD/EXPIRED' disagrees with hospital_expire_flag | pass | 0 | 58,976 | 0 |  |
| patients.expire_flag disagrees with dod being recorded | pass | 0 | 46,520 | 0 |  |
| icustays.los differs from (outtime - intime) by more than 0.01 day | pass | 0 | 61,522 | 0 | null_outtime=<11 |
| ICU intime outside its hospital admission [admittime, dischtime] | info | 585 | 61,532 | 0.951 | beyond_24h=<11 |
| Patients aged >= 89 at first admission (DOB shifted: computed age about 300) | info | 1,991 | 46,520 | 4.28 | shifted_about_300=1,991, under_1_year=7,874 |

## MIMIC-III conventions and coverage

Documented MIMIC-III behaviours and gaps in this copy of the data.

| Check | Status | Flagged | Total | % | Details |
|---|---|---:|---:|---:|---|
| diagnoses_icd.icd9_code stored without a decimal point | pass | 0 | 651,000 | 0 |  |
| procedures_icd.icd9_code stored without a decimal point | pass | 0 | 240,095 | 0 |  |
| d_icd_diagnoses.icd9_code stored without a decimal point | pass | 0 | 14,567 | 0 |  |
| d_icd_procedures.icd9_code stored without a decimal point | pass | 0 | 3,882 | 0 |  |
| patients.gender is 'M' or 'F' | pass | 0 | 46,520 | 0 |  |
| ICU stays with no INPUTEVENTS_CV rows (MetaVision stays need INPUTEVENTS_MV, not loaded) | info | 27,733 | 61,532 | 45.071 | metavision_without=23,611, carevue_without=4,081 |
| INPUTEVENTS_CV rows on MetaVision-only ICU stays | flag | 1,709 | 17,497,482 | 0.01 | stays_affected=<11 |
| PROCEDUREEVENTS_MV rows on CareVue-only ICU stays | flag | 381 | 257,978 | 0.148 | stays_affected=23 |
| ICU stays with no PROCEDUREEVENTS_MV rows (table covers MetaVision stays only) | info | 38,131 | 61,532 | 61.969 | carevue_without=37,753 |
| CPTEVENTS rows whose admission has no ICU stay | info | 2,499 | 573,146 | 0.436 |  |
| PRESCRIPTIONS rows with no usable NDC (null, '' or '0') | info | 591,049 | 4,156,450 | 14.22 |  |
| DATETIMEEVENTS rows marked error = 1 | info | 595 | 4,485,937 | 0.013 |  |
| PROCEDUREEVENTS_MV rows with statusdescription 'Rewritten' (superseded entries) | info | 8,590 | 258,066 | 3.329 |  |
| MICROBIOLOGYEVENTS rows with chartdate but no charttime | info | 41,772 | 631,726 | 6.612 |  |
| MICROBIOLOGYEVENTS rows with no organism (org_name null: no growth / specimen only) | info | 303,710 | 631,726 | 48.076 |  |
| Admissions with no DIAGNOSES_ICD rows | info | 0 | 58,976 | 0 |  |
| D_ITEMS rows with no LINKSTO table | info | 0 | 12,487 | 0 |  |

## Missing values

Share of null values, for columns with any.

| Table | Column | % null |
|---|---|---:|
| admissions | deathtime | 90.074 |
| admissions | edregtime | 47.645 |
| admissions | edouttime | 47.645 |
| admissions | language | 42.953 |
| admissions | marital_status | 17.173 |
| admissions | religion | 0.777 |
| admissions | diagnosis | 0.042 |
| callout | currentreservationtime | 96.626 |
| callout | submit_careunit | 85.153 |
| callout | firstreservationtime | 55.767 |
| callout | discharge_wardid | 13.137 |
| callout | acknowledgetime | 5.194 |
| callout | submit_wardid | <11 rows |
| callout | curr_wardid | <11 rows |
| callout | curr_careunit | <11 rows |
| caregivers | description | 31.875 |
| caregivers | label | 0.608 |
| cptevents | cpt_suffix | 99.996 |
| cptevents | chartdate | 82.283 |
| cptevents | description | 82.283 |
| cptevents | ticket_id_seq | 17.717 |
| cptevents | sectionheader | 0.004 |
| cptevents | subsectionheader | 0.004 |
| cptevents | cpt_number | 0.003 |
| d_cpt | codesuffix | 91.791 |
| d_items | conceptid | 100 |
| d_items | unitname | 90.118 |
| d_items | abbreviation | 76.039 |
| d_items | param_type | 76.039 |
| d_items | category | 51.558 |
| d_items | label | <11 rows |
| d_labitems | loinc_code | 22.311 |
| datetimeevents | resultstatus | 100 |
| datetimeevents | stopped | 59.897 |
| datetimeevents | warning | 40.103 |
| datetimeevents | error | 40.103 |
| datetimeevents | value | 1.161 |
| datetimeevents | icustay_id | 0.093 |
| datetimeevents | hadm_id | 0.04 |
| diagnoses_icd | seq_num | 0.007 |
| diagnoses_icd | icd9_code | 0.007 |
| drgcodes | drg_severity | 46.929 |
| drgcodes | drg_mortality | 46.929 |
| drgcodes | description | 0.05 |
| icustays | outtime | <11 rows |
| icustays | los | <11 rows |
| inputevents_cv | originalsite | 98.987 |
| inputevents_cv | newbottle | 98.597 |
| inputevents_cv | stopped | 97.258 |
| inputevents_cv | rate | 76.426 |
| inputevents_cv | rateuom | 76.197 |
| inputevents_cv | originalrate | 70.295 |
| inputevents_cv | originalrateuom | 69.926 |
| inputevents_cv | originalamount | 43.105 |
| inputevents_cv | amount | 29.127 |
| inputevents_cv | amountuom | 24.718 |
| inputevents_cv | originalamountuom | 24.412 |
| inputevents_cv | cgid | 2.02 |
| inputevents_cv | originalroute | 0.609 |
| inputevents_cv | icustay_id | 0.174 |
| inputevents_cv | hadm_id | 0.129 |
| microbiologyevents | dilution_comparison | 57.707 |
| microbiologyevents | dilution_value | 57.707 |
| microbiologyevents | dilution_text | 57.679 |
| microbiologyevents | ab_itemid | 56.336 |
| microbiologyevents | ab_name | 56.336 |
| microbiologyevents | interpretation | 56.336 |
| microbiologyevents | org_itemid | 48.256 |
| microbiologyevents | org_name | 48.076 |
| microbiologyevents | isolate_num | 48.076 |
| microbiologyevents | charttime | 6.612 |
| microbiologyevents | spec_itemid | 0.013 |
| patients | dod_hosp | 78.56 |
| patients | dod_ssn | 71.242 |
| patients | dod | 66.124 |
| prescriptions | drug_name_poe | 40.04 |
| prescriptions | drug_name_generic | 40.01 |
| prescriptions | icustay_id | 34.83 |
| prescriptions | gsn | 12.202 |
| prescriptions | enddate | 0.13 |
| prescriptions | ndc | 0.107 |
| prescriptions | startdate | 0.077 |
| prescriptions | formulary_drug_cd | 0.047 |
| prescriptions | form_unit_disp | 0.034 |
| prescriptions | prod_strength | 0.033 |
| prescriptions | form_val_disp | 0.033 |
| prescriptions | dose_val_rx | 0.032 |
| prescriptions | dose_unit_rx | 0.032 |
| prescriptions | route | 0.028 |
| procedureevents_mv | secondaryordercategoryname | 100 |
| procedureevents_mv | comments_editedby | 99.189 |
| procedureevents_mv | comments_canceledby | 97.796 |
| procedureevents_mv | comments_date | 96.984 |
| procedureevents_mv | location | 79.613 |
| procedureevents_mv | locationcategory | 79.613 |
| procedureevents_mv | icustay_id | 0.034 |
| services | prev_service | 80.001 |
| transfers | icustay_id | 66.506 |
| transfers | prev_careunit | 63.341 |
| transfers | curr_careunit | 63.338 |
| transfers | outtime | 22.519 |
| transfers | los | 22.519 |
| transfers | curr_wardid | 22.506 |
| transfers | prev_wardid | 22.502 |
| transfers | dbsource | 0.092 |
| transfers | eventtype | 0.009 |
| transfers | intime | 0.009 |

## Padded text values

Text values with leading or trailing spaces (an exact match on them fails).

| Table | Column | Values with spaces |
|---|---|---:|
| admissions | diagnosis | 460 |
| d_items | label | <11 |
| d_items | abbreviation | <11 |
| drgcodes | drg_type | 66,634 |
| microbiologyevents | org_name | 108 |
| prescriptions | drug | 19,577 |
| prescriptions | drug_name_poe | 16,651 |
| prescriptions | drug_name_generic | 16,105 |
| prescriptions | gsn | 1,125 |
| prescriptions | prod_strength | 2,783 |
| prescriptions | dose_val_rx | 60 |
| prescriptions | form_val_disp | <11 |
| procedureevents_mv | location | 369 |

## Value distributions of coded columns

Values are quoted so that padding is visible.

- **icustays.dbsource**: `'carevue'` (37,776), `'metavision'` (23,620), `'both'` (136)
- **icustays.first_careunit**: `'MICU'` (21,088), `'CSRU'` (9,312), `'SICU'` (8,891), `'NICU'` (8,100), `'CCU'` (7,726), `'TSICU'` (6,415)
- **admissions.admission_type**: `'EMERGENCY'` (42,071), `'NEWBORN'` (7,863), `'ELECTIVE'` (7,706), `'URGENT'` (1,336)
- **admissions.insurance**: `'Medicare'` (28,215), `'Private'` (22,582), `'Medicaid'` (5,785), `'Government'` (1,783), `'Self Pay'` (611)
- **drgcodes.drg_type**: `'APR '` (66,634), `'HCFA'` (31,644), `'MS'` (27,279)
- **prescriptions.drug_type**: `'MAIN'` (3,216,882), `'BASE'` (925,089), `'ADDITIVE'` (14,479)
- **d_items.linksto**: `'chartevents'` (7,212), `'inputevents_cv'` (2,938), `'outputevents'` (1,161), `'microbiologyevents'` (436), `'inputevents_mv'` (422), `'datetimeevents'` (193), `'procedureevents_mv'` (125)
- **d_items.dbsource**: `'carevue'` (9,059), `'metavision'` (2,992), `'hospital'` (436)
- **services.curr_service**: `'MED'` (24,866), `'CMED'` (9,135), `'CSURG'` (7,911), `'NB'` (7,806), `'SURG'` (5,514), `'NSURG'` (4,100), `'TRAUM'` (3,137), `'NMED'` (2,957), `'OMED'` (2,286), `'VSURG'` (1,455), `'TSURG'` (1,338), `'ORTHO'` (1,101), `'GU'` (436), `'NBB'` (346), `'GYN'` (306), `'PSURG'` (283), `'ENT'` (247), `'OBS'` (113), `'DENT'` (<11), `'PSYCH'` (<11)
- **transfers.eventtype**: `'transfer'` (144,045), `'discharge'` (58,919), `'admit'` (58,909), `(null)` (24)
- **procedureevents_mv.statusdescription**: `'FinishedRunning'` (246,430), `'Rewritten'` (8,590), `'Stopped'` (2,846), `'Paused'` (200)
- **microbiologyevents.interpretation**: `(null)` (355,892), `'S'` (188,635), `'R'` (77,169), `'I'` (10,023), `'P'` (<11)

## Derived query conventions

Rules the system follows when writing SQL over this dataset.

1. These combinations repeat within one admission: diagnoses_icd (hadm_id, icd9_code), procedures_icd (hadm_id, icd9_code), drgcodes (hadm_id, drg_type). Count DISTINCT admissions or codes, not rows.
   *Evidence: diagnoses_icd (hadm_id, icd9_code) 60 of 651,047 (0.009%); procedures_icd (hadm_id, icd9_code) 11,416 of 240,095 (4.755%); drgcodes (hadm_id, drg_type) 27,272 of 125,557 (21.721%).*
2. These tables contain exact duplicate rows (all columns equal except row_id): drgcodes, inputevents_cv, microbiologyevents, prescriptions, transfers. Use COUNT(DISTINCT ...) or SELECT DISTINCT before counting or summing.
   *Evidence: drgcodes 25,233 of 125,557 (20.097%); inputevents_cv 9,418 of 17,527,935 (0.054%); microbiologyevents 18,414 of 631,726 (2.915%); prescriptions 236,244 of 4,156,450 (5.684%); transfers 40 of 261,897 (0.015%).*
3. Some codes have no entry in their dictionary table: diagnoses_icd.icd9_code -> d_icd_diagnoses, procedures_icd.icd9_code -> d_icd_procedures. Use a LEFT JOIN to the dictionary (an INNER JOIN drops those rows) and report unlabeled codes as such.
   *Evidence: diagnoses_icd.icd9_code -> d_icd_diagnoses 16,291 of 651,000 (2.502%); procedures_icd.icd9_code -> d_icd_procedures 2,147 of 240,095 (0.894%).*
4. For a few rows, the event's hadm_id differs from icustays.hadm_id of the same icustay_id: datetimeevents, inputevents_cv, prescriptions. Never join these tables to icustays on both icustay_id and hadm_id at once (those rows are dropped): join on icustay_id for ICU-stay questions and on the event's own hadm_id for admission questions.
   *Evidence: datetimeevents 408 of 4,481,781 (0.009%); inputevents_cv 4,314 of 17,497,482 (0.025%); prescriptions 607 of 2,708,742 (0.022%).*
5. Some end times precede their start times: admissions (dischtime < admittime), admissions (edouttime < edregtime), prescriptions (enddate < startdate), procedureevents_mv (endtime < starttime). Exclude those rows when computing durations or lengths of stay; keep them for counts.
   *Evidence: admissions (dischtime < admittime) 98 of 58,976 (0.166%); admissions (edouttime < edregtime) 17 of 30,877 (0.055%); prescriptions (enddate < startdate) 15,922 of 4,150,832 (0.384%); procedureevents_mv (endtime < starttime) 62 of 258,066 (0.024%).*
6. Some events are timed slightly outside [admittime, dischtime] of their own admission, mostly within 24 h (e.g. ED time before admission): callout.createtime, datetimeevents.charttime, inputevents_cv.charttime, microbiologyevents.chartdate, prescriptions.startdate, procedureevents_mv.starttime, services.transfertime, transfers.intime, icustays.intime. Link events to admissions by hadm_id, not by time overlap (a time-window filter would drop them); apply a time filter only when the question asks for one (e.g. 'first 24 hours').
   *Evidence: callout.createtime 36 of 34,499 (0.104%); datetimeevents.charttime 11,046 of 4,484,165 (0.246%); inputevents_cv.charttime 43,596 of 17,505,266 (0.249%); microbiologyevents.chartdate 1,655 of 631,726 (0.262%); prescriptions.startdate 4,897 of 4,153,268 (0.118%); procedureevents_mv.starttime 1,049 of 258,066 (0.406%); services.transfertime 6,898 of 73,343 (9.405%); transfers.intime 57,849 of 261,873 (22.09%); icustays.intime 585 of 61,532 (0.951%).*
7. Identify in-hospital death with admissions.hospital_expire_flag = 1, not by testing deathtime against the admission window.
   *Evidence: 126 of 5,854 (2.152%).*
8. Patients older than 89 at their first admission have DOB shifted so that computed age is about 300 years. For age questions treat computed age > 89 as '>89' (cap, or exclude); never average raw computed ages. MIMIC documents the median true age of this group as 91.4.
   *Evidence: 1,991 of 46,520 (4.28%).*
9. ICD-9 codes are stored as text without the decimal point ('4019' is 401.9; E and V codes keep their letter) in diagnoses_icd.icd9_code, procedures_icd.icd9_code, d_icd_diagnoses.icd9_code, d_icd_procedures.icd9_code. Compare as strings; never cast to numbers.
   *Evidence: diagnoses_icd.icd9_code 0 of 651,000 (0%); procedures_icd.icd9_code 0 of 240,095 (0%); d_icd_diagnoses.icd9_code 0 of 14,567 (0%); d_icd_procedures.icd9_code 0 of 3,882 (0%).*
10. ICU input (fluid/drug administration) data cover CareVue stays only (INPUTEVENTS_CV, 2001-2008); INPUTEVENTS_MV is not loaded, so input questions about MetaVision stays (2008-2012) cannot be answered and population-level input statistics are partial.
   *Evidence: 27,733 of 61,532 (45.071%).*
11. icustays.dbsource does not exactly partition the ICU event tables: inputevents_cv rows on 'metavision' stays, procedureevents_mv rows on 'carevue' stays. Find a stay's events by querying the event table on icustay_id; never choose the table from icustays.dbsource.
   *Evidence: inputevents_cv rows on 'metavision' stays 1,709 of 17,497,482 (0.01%); procedureevents_mv rows on 'carevue' stays 381 of 257,978 (0.148%).*
12. PROCEDUREEVENTS_MV covers MetaVision ICU stays only (2008-2012); CareVue stays have no ICU procedure events. Use PROCEDURES_ICD for hospital procedures across all years.
   *Evidence: 38,131 of 61,532 (61.969%).*
13. CPTEVENTS records billed professional services (mostly ICU); it is not a complete record of procedures. Use PROCEDURES_ICD for 'which procedures did the patient have'.
   *Evidence: 2,499 of 573,146 (0.436%).*
14. Many prescriptions have no usable NDC: find drugs by name (drug, drug_name_generic; case-insensitive, e.g. lower(drug) LIKE '%heparin%') rather than by NDC.
   *Evidence: 591,049 of 4,156,450 (14.22%).*
15. Exclude datetimeevents rows with error = 1 (charted in error).
   *Evidence: 595 of 4,485,937 (0.013%).*
16. Exclude procedureevents_mv rows with statusdescription = 'Rewritten' (replaced by a later entry) when counting procedures.
   *Evidence: 8,590 of 258,066 (3.329%).*
17. Microbiology charttime is often missing: use chartdate for microbiology timing.
   *Evidence: 41,772 of 631,726 (6.612%).*
18. Microbiology rows with org_name IS NULL record specimens without a grown organism; count positive cultures with org_name IS NOT NULL.
   *Evidence: 303,710 of 631,726 (48.076%).*
19. ICU data come from two systems: CareVue (2001-2008) and MetaVision (2008-2012); item IDs and event tables differ between them (dbsource).
20. admission_type = 'NEWBORN' marks neonatal admissions (age about 0); exclude them for adult cohort questions unless newborns are asked about.
21. DRGCODES mixes DRG systems (drg_type HCFA, MS, APR): filter by drg_type before comparing codes.
22. Some text values have leading or trailing spaces, so an exact match fails (every APR row has drg_type 'APR ', so drg_type = 'APR' finds nothing): admissions.diagnosis, d_items.label, d_items.abbreviation, drgcodes.drg_type, microbiologyevents.org_name, prescriptions.drug, prescriptions.drug_name_poe, prescriptions.drug_name_generic, prescriptions.gsn, prescriptions.prod_strength, prescriptions.dose_val_rx, prescriptions.form_val_disp, procedureevents_mv.location. Compare with trim(column) = 'value', or use LIKE / ILIKE patterns.
   *Evidence: admissions.diagnosis 460 values; d_items.label <11 values; d_items.abbreviation <11 values; drgcodes.drg_type 66,634 values; microbiologyevents.org_name 108 values; prescriptions.drug 19,577 values; prescriptions.drug_name_poe 16,651 values; prescriptions.drug_name_generic 16,105 values; prescriptions.gsn 1,125 values; prescriptions.prod_strength 2,783 values; prescriptions.dose_val_rx 60 values; prescriptions.form_val_disp <11 values; procedureevents_mv.location 369 values.*
23. These columns are always null in this dataset: d_items.conceptid, datetimeevents.resultstatus, procedureevents_mv.secondaryordercategoryname. Do not filter or group on them.
