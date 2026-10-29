"""
MIMIC-III v1.4 table specifications: every table's name, its columns in file
order with their types, and its published row count. The loader uses them to
read the CSVs with explicit types instead of letting DuckDB guess, and the
inventory uses them to check the files' headers.

How this file was created
- Column names, order and types: written from the official MIMIC-III v1.4
  table definitions (MIT-LCP mimic-code, mimic-iii/buildmimic/postgres/
  postgres_create_tables.sql), from knowledge of that file rather than a
  fresh download, then translated to DuckDB types (mapping below).
- Row counts: the published MIMIC-III v1.4 counts (https://mimic.mit.edu/docs/iii/tables/).
- Verified against the team's copy of the data: for the 21 tables in
  TEAM_TABLES, every CSV header matched these columns (inventory stage) and
  every loaded row count matched exactly, with no unreadable rows (load stage).
  The specs of the other 5 tables (CHARTEVENTS, INPUTEVENTS_MV, LABEVENTS,
  NOTEEVENTS, OUTPUTEVENTS) have NOT been checked against files yet; the
  inventory stage will report any mismatch once those files are available.

Type mapping from the PostgreSQL definitions:
    INT / SMALLINT           -> INTEGER / SMALLINT
    DOUBLE PRECISION         -> DOUBLE
    TIMESTAMP(0)             -> TIMESTAMP  (MIMIC writes dates as 'YYYY-MM-DD 00:00:00')
    VARCHAR(n) / CHAR / TEXT -> VARCHAR

Code columns (icd9_code, cpt_cd, drg_code, loinc_code, ndc, gsn, ...) are
VARCHAR on purpose: they look numeric but leading zeros are meaningful
(ICD-9 '0066' is not '66').

To describe another dataset, see "Setting up a new dataset" in the README.md
next to this file.
"""
from dataclasses import dataclass

I, S, D, T, V = "INTEGER", "SMALLINT", "DOUBLE", "TIMESTAMP", "VARCHAR"


@dataclass(frozen=True)
class TableSpec:
    name: str  # Upper case, as in the CSV file name
    columns: tuple[tuple[str, str], ...]  # (CSV header name, DuckDB type), in file order
    official_rows: int | None  # Published row count; None if the dataset publishes none

    @property
    def table_name(self) -> str:
        """Name inside the dataset DB (lower case, as the query system expects)."""
        return self.name.lower()

    @property
    def column_names(self) -> list[str]:
        return [name for name, _ in self.columns]

    @property
    def types(self) -> dict[str, str]:
        return dict(self.columns)


def _spec(name: str, rows: int | None, columns: str) -> TableSpec:
    """columns: 'NAME:TYPE NAME:TYPE ...' (keeps the table below readable).
    Table and column descriptions are in mimic3_docs.py."""
    pairs = tuple(tuple(item.split(":")) for item in columns.split())
    return TableSpec(name, pairs, rows)  # type: ignore[arg-type]


_SPECS = [
    _spec("ADMISSIONS", 58_976,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ADMITTIME:{T} DISCHTIME:{T} DEATHTIME:{T} "
          f"ADMISSION_TYPE:{V} ADMISSION_LOCATION:{V} DISCHARGE_LOCATION:{V} INSURANCE:{V} LANGUAGE:{V} "
          f"RELIGION:{V} MARITAL_STATUS:{V} ETHNICITY:{V} EDREGTIME:{T} EDOUTTIME:{T} DIAGNOSIS:{V} "
          f"HOSPITAL_EXPIRE_FLAG:{S} HAS_CHARTEVENTS_DATA:{S}"),
    _spec("CALLOUT", 34_499,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} SUBMIT_WARDID:{I} SUBMIT_CAREUNIT:{V} CURR_WARDID:{I} "
          f"CURR_CAREUNIT:{V} CALLOUT_WARDID:{I} CALLOUT_SERVICE:{V} REQUEST_TELE:{S} REQUEST_RESP:{S} "
          f"REQUEST_CDIFF:{S} REQUEST_MRSA:{S} REQUEST_VRE:{S} CALLOUT_STATUS:{V} CALLOUT_OUTCOME:{V} "
          f"DISCHARGE_WARDID:{I} ACKNOWLEDGE_STATUS:{V} CREATETIME:{T} UPDATETIME:{T} ACKNOWLEDGETIME:{T} "
          f"OUTCOMETIME:{T} FIRSTRESERVATIONTIME:{T} CURRENTRESERVATIONTIME:{T}"),
    _spec("CAREGIVERS", 7_567,
          f"ROW_ID:{I} CGID:{I} LABEL:{V} DESCRIPTION:{V}"),
    _spec("CHARTEVENTS", 330_712_483,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} ITEMID:{I} CHARTTIME:{T} STORETIME:{T} "
          f"CGID:{I} VALUE:{V} VALUENUM:{D} VALUEUOM:{V} WARNING:{I} ERROR:{I} RESULTSTATUS:{V} STOPPED:{V}"),
    _spec("CPTEVENTS", 573_146,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} COSTCENTER:{V} CHARTDATE:{T} CPT_CD:{V} CPT_NUMBER:{I} "
          f"CPT_SUFFIX:{V} TICKET_ID_SEQ:{I} SECTIONHEADER:{V} SUBSECTIONHEADER:{V} DESCRIPTION:{V}"),
    _spec("D_CPT", 134,
          f"ROW_ID:{I} CATEGORY:{S} SECTIONRANGE:{V} SECTIONHEADER:{V} SUBSECTIONRANGE:{V} "
          f"SUBSECTIONHEADER:{V} CODESUFFIX:{V} MINCODEINSUBSECTION:{I} MAXCODEINSUBSECTION:{I}"),
    _spec("D_ICD_DIAGNOSES", 14_567,
          f"ROW_ID:{I} ICD9_CODE:{V} SHORT_TITLE:{V} LONG_TITLE:{V}"),
    _spec("D_ICD_PROCEDURES", 3_882,
          f"ROW_ID:{I} ICD9_CODE:{V} SHORT_TITLE:{V} LONG_TITLE:{V}"),
    _spec("D_ITEMS", 12_487,
          f"ROW_ID:{I} ITEMID:{I} LABEL:{V} ABBREVIATION:{V} DBSOURCE:{V} LINKSTO:{V} CATEGORY:{V} "
          f"UNITNAME:{V} PARAM_TYPE:{V} CONCEPTID:{I}"),
    _spec("D_LABITEMS", 753,
          f"ROW_ID:{I} ITEMID:{I} LABEL:{V} FLUID:{V} CATEGORY:{V} LOINC_CODE:{V}"),
    _spec("DATETIMEEVENTS", 4_485_937,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} ITEMID:{I} CHARTTIME:{T} STORETIME:{T} "
          f"CGID:{I} VALUE:{T} VALUEUOM:{V} WARNING:{S} ERROR:{S} RESULTSTATUS:{V} STOPPED:{V}"),
    _spec("DIAGNOSES_ICD", 651_047,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} SEQ_NUM:{I} ICD9_CODE:{V}"),
    _spec("DRGCODES", 125_557,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} DRG_TYPE:{V} DRG_CODE:{V} DESCRIPTION:{V} "
          f"DRG_SEVERITY:{S} DRG_MORTALITY:{S}"),
    _spec("ICUSTAYS", 61_532,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} DBSOURCE:{V} FIRST_CAREUNIT:{V} "
          f"LAST_CAREUNIT:{V} FIRST_WARDID:{S} LAST_WARDID:{S} INTIME:{T} OUTTIME:{T} LOS:{D}"),
    _spec("INPUTEVENTS_CV", 17_527_935,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} CHARTTIME:{T} ITEMID:{I} AMOUNT:{D} "
          f"AMOUNTUOM:{V} RATE:{D} RATEUOM:{V} STORETIME:{T} CGID:{I} ORDERID:{I} LINKORDERID:{I} "
          f"STOPPED:{V} NEWBOTTLE:{I} ORIGINALAMOUNT:{D} ORIGINALAMOUNTUOM:{V} ORIGINALROUTE:{V} "
          f"ORIGINALRATE:{D} ORIGINALRATEUOM:{V} ORIGINALSITE:{V}"),
    _spec("INPUTEVENTS_MV", 3_618_991,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} STARTTIME:{T} ENDTIME:{T} ITEMID:{I} "
          f"AMOUNT:{D} AMOUNTUOM:{V} RATE:{D} RATEUOM:{V} STORETIME:{T} CGID:{I} ORDERID:{I} "
          f"LINKORDERID:{I} ORDERCATEGORYNAME:{V} SECONDARYORDERCATEGORYNAME:{V} "
          f"ORDERCOMPONENTTYPEDESCRIPTION:{V} ORDERCATEGORYDESCRIPTION:{V} PATIENTWEIGHT:{D} "
          f"TOTALAMOUNT:{D} TOTALAMOUNTUOM:{V} ISOPENBAG:{S} CONTINUEINNEXTDEPT:{S} CANCELREASON:{S} "
          f"STATUSDESCRIPTION:{V} COMMENTS_EDITEDBY:{V} COMMENTS_CANCELEDBY:{V} COMMENTS_DATE:{T} "
          f"ORIGINALAMOUNT:{D} ORIGINALRATE:{D}"),
    _spec("LABEVENTS", 27_854_055,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ITEMID:{I} CHARTTIME:{T} VALUE:{V} VALUENUM:{D} "
          f"VALUEUOM:{V} FLAG:{V}"),
    _spec("MICROBIOLOGYEVENTS", 631_726,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} CHARTDATE:{T} CHARTTIME:{T} SPEC_ITEMID:{I} "
          f"SPEC_TYPE_DESC:{V} ORG_ITEMID:{I} ORG_NAME:{V} ISOLATE_NUM:{S} AB_ITEMID:{I} AB_NAME:{V} "
          f"DILUTION_TEXT:{V} DILUTION_COMPARISON:{V} DILUTION_VALUE:{D} INTERPRETATION:{V}"),
    _spec("NOTEEVENTS", 2_083_180,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} CHARTDATE:{T} CHARTTIME:{T} STORETIME:{T} CATEGORY:{V} "
          f"DESCRIPTION:{V} CGID:{I} ISERROR:{V} TEXT:{V}"),
    _spec("OUTPUTEVENTS", 4_349_218,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} CHARTTIME:{T} ITEMID:{I} VALUE:{D} "
          f"VALUEUOM:{V} STORETIME:{T} CGID:{I} STOPPED:{V} NEWBOTTLE:{V} ISERROR:{I}"),
    _spec("PATIENTS", 46_520,
          f"ROW_ID:{I} SUBJECT_ID:{I} GENDER:{V} DOB:{T} DOD:{T} DOD_HOSP:{T} DOD_SSN:{T} EXPIRE_FLAG:{I}"),
    _spec("PRESCRIPTIONS", 4_156_450,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} STARTDATE:{T} ENDDATE:{T} DRUG_TYPE:{V} "
          f"DRUG:{V} DRUG_NAME_POE:{V} DRUG_NAME_GENERIC:{V} FORMULARY_DRUG_CD:{V} GSN:{V} NDC:{V} "
          f"PROD_STRENGTH:{V} DOSE_VAL_RX:{V} DOSE_UNIT_RX:{V} FORM_VAL_DISP:{V} FORM_UNIT_DISP:{V} ROUTE:{V}"),
    _spec("PROCEDUREEVENTS_MV", 258_066,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} STARTTIME:{T} ENDTIME:{T} ITEMID:{I} "
          f"VALUE:{D} VALUEUOM:{V} LOCATION:{V} LOCATIONCATEGORY:{V} STORETIME:{T} CGID:{I} ORDERID:{I} "
          f"LINKORDERID:{I} ORDERCATEGORYNAME:{V} SECONDARYORDERCATEGORYNAME:{V} "
          f"ORDERCATEGORYDESCRIPTION:{V} ISOPENBAG:{S} CONTINUEINNEXTDEPT:{S} CANCELREASON:{S} "
          f"STATUSDESCRIPTION:{V} COMMENTS_EDITEDBY:{V} COMMENTS_CANCELEDBY:{V} COMMENTS_DATE:{T}"),
    _spec("PROCEDURES_ICD", 240_095,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} SEQ_NUM:{I} ICD9_CODE:{V}"),
    _spec("SERVICES", 73_343,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} TRANSFERTIME:{T} PREV_SERVICE:{V} CURR_SERVICE:{V}"),
    _spec("TRANSFERS", 261_897,
          f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} ICUSTAY_ID:{I} DBSOURCE:{V} EVENTTYPE:{V} "
          f"PREV_CAREUNIT:{V} CURR_CAREUNIT:{V} PREV_WARDID:{S} CURR_WARDID:{S} INTIME:{T} OUTTIME:{T} LOS:{D}"),
]

TABLES: dict[str, TableSpec] = {spec.name: spec for spec in _SPECS}

# The 21 tables in the team's shared copy of MIMIC-III. The other 5 (CHARTEVENTS,
# INPUTEVENTS_MV, LABEVENTS, NOTEEVENTS, OUTPUTEVENTS) are known to be absent;
# questions that need them are unanswerable from this dataset.
TEAM_TABLES: tuple[str, ...] = (
    "ADMISSIONS", "CALLOUT", "CAREGIVERS", "CPTEVENTS", "D_CPT", "D_ICD_DIAGNOSES",
    "D_ICD_PROCEDURES", "D_ITEMS", "D_LABITEMS", "DATETIMEEVENTS", "DIAGNOSES_ICD",
    "DRGCODES", "ICUSTAYS", "INPUTEVENTS_CV", "MICROBIOLOGYEVENTS", "PATIENTS",
    "PRESCRIPTIONS", "PROCEDUREEVENTS_MV", "PROCEDURES_ICD", "SERVICES", "TRANSFERS",
)
