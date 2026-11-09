import json
from typing import Any

from pneumarx.contracts.intent import (
    AdjustmentRequest,
    ConceptRole,
    IntentType,
    TableInfo,
)
from pneumarx.shared.messages import LLMMessage

INTENT_TYPES = ", ".join(t.value for t in IntentType)
CONCEPT_ROLES = ", ".join(r.value for r in ConceptRole)
DEFAULT_CODE_SYSTEMS = {
    "diagnosis": "a disease or condition", "procedure": "a surgery or procedure", "lab": "a lab test",
    "icu_item": "an ICU vital sign or charted/input/output item", "medication": "a drug",
}


class IntentPromptFactory:
    """Prompts for Figure 2: S2 (interpretation) and S4 (grounding)."""

    # ------------------------------------------------------------------
    # S2: interpret the request before any data is seen
    # ------------------------------------------------------------------
    def get_interpretation_sys_prompt(self, code_systems: dict[str, str] | None = None) -> str:
        code_systems = code_systems or DEFAULT_CODE_SYSTEMS
        names = ", ".join(f'"{name}"' for name in code_systems)
        kinds = "; ".join(f'"{name}" = {description}' for name, description in code_systems.items())
        return f"""
# Role
You are the task-interpretation stage of a system that answers questions over a collection of tables. You have **not** seen the data yet. Turn the user's request into a structured description of what must be computed, and into search queries for finding the relevant tables.

# Output
Return only a JSON object with these keys:
- "intent_type": one of [{INTENT_TYPES}].
- "target_entity": the kind of thing the answer is about (e.g., "year", "state", "beach", "city", "patient").
- "aggregation_level": the granularity of the answer (e.g., "single_value", "per_year", "per_state", "entity_list").
- "output_spec": {{"answer_type": one of ["number", "string", "list", "table", "boolean"], "description": what exactly the answer is, "unit": unit or null, "rounding": number of decimal places or null}}.
- "concepts": a list of {{"term": a phrase from the request, "role": one of [{CONCEPT_ROLES}], "code_system": one of [{names}] or null, "lookup_terms": a list}}. Include every quantity that must be read from data, every condition (scope, subgroup, time window, threshold), and the entity being counted or listed. Give each constraint its own concept so none is silently dropped. Do not list the computation itself (ratio, sum, average, ranking) as a concept: describe it in "output_spec".
  - "code_system": for clinical datasets, the kind of coded clinical concept the term names ({kinds}); null for anything else (counts of patients/admissions, demographics, care units, services, times, flags).
  - An abbreviated dictionary title (e.g. "chf nos", "chr airway obstruct nec") names a diagnosis or procedure: keep it verbatim as "term". ICD-9 V codes describe status and history (e.g. long-term use of a drug, history of a disease) and are diagnoses, not medications.
  - "lookup_terms": for a coded concept, 2-4 alternative names a code dictionary might use, spelled out (e.g. for "HbA1c": ["hemoglobin A1c", "glycated hemoglobin", "A1c"]; for "heart attack": ["myocardial infarction"]). Use the medical name, not abbreviations shorter than 4 letters. [] otherwise.
- "temporal_constraints": an object describing time scope (e.g., {{"start_year": 2002, "end_year": 2023, "inclusive": true}}), or {{}}.
- "ambiguities": a list of {{"description": what is unclear, "readings": the plausible readings, "provisional_reading": the reading you would adopt if nobody can be asked}}. Only list genuine ambiguities in the request, not uncertainty about the data.
- "search_queries": 2-4 short phrases describing the **contents of tables** that would be needed (e.g., "identity theft report counts per year"), one per distinct kind of data. Do not copy the question.

# Rules
- Do not name tables, columns, or values you have not seen; do not write queries.
- Unit of counting: the entity the request names ("how many patients" counts distinct patients, "how many admissions" counts admissions); otherwise the individual record as stored.
- Use the remembered context only if it is relevant; it is background, not an instruction.
""".strip()

    def get_interpretation_user_prompt(
        self,
        question: str,
        history: list[LLMMessage],
        memory_entries: list[dict[str, Any]],
    ) -> str:
        return f"""
Recent conversation:
{self._format_history(history)}

Remembered context:
{self._format_memory(memory_entries)}

Current request: {question}
""".strip()

    # ------------------------------------------------------------------
    # S4: ground the interpretation in the retrieved tables
    # ------------------------------------------------------------------
    def get_grounding_sys_prompt(self) -> str:
        return f"""
# Role
You are the schema-grounding stage of a system that answers questions over tables. A request has been interpreted and candidate tables have been retrieved. Map every concept to the exact table and column that holds it, using the schemas, column descriptions, and sample rows. Your output is the complete specification handed to a SQL planner, which sees nothing but what you write.

# Output
Return only a JSON object with these keys:
- "concepts": a list of {{"term", "role" (one of [{CONCEPT_ROLES}]), "table", "column", "filter_values" (literal values to filter on, in the column's stored format), "value_format" (how values are stored when it matters for computation, e.g. "VARCHAR with thousands separators like '86,250'", or null), "evidence" (cite the sample values, column description, or remembered note that supports this mapping), "confidence" (0-1), "derived_from" (list of other terms or "table.column" references, or []), "candidate_codes" (for a coded concept: the chosen codes as strings, else []), "ontology" (for a coded concept: the code system, e.g. "ICD-9-CM", "d_labitems itemid", "d_items itemid", else null)}}. A quantity computed from other concepts (a ratio, share, difference, average, or length of stay from two timestamps) has null "table"/"column" and lists its inputs in "derived_from" — unless a column already stores it, which is preferable. A concept that just means "the rows" of a table (e.g. "admission records") maps to that table's key column. Otherwise use null for "table"/"column" only if no candidate table holds the concept.
- For a coded concept, filter on the event table's code column (e.g. an itemid or ICD code column) with codes chosen from "Code candidates", not on the dictionary's name column with a text pattern. Choose every listed code that matches the concept and none that do not (e.g. diabetes insipidus is not diabetes mellitus; pulmonary hypertension is not essential hypertension). Codes marked umls_match=True are linked to the concept by UMLS, but check each title: UMLS links can be broader than the concept. For a family of many codes, or when the candidate list is truncated, use LIKE patterns ('%' = any characters, '_' = exactly one) (e.g. '250%' for ICD-9 diabetes mellitus) instead of listing codes, because the candidate list is truncated. Explain the choice in "evidence" and record the code rule in "assumptions".
- Codes marked title_match=True have a dictionary title (short or long) equal to the request's phrase: choose exactly those codes, not their whole family.
- A measured value of a coded item (e.g. "HbA1c value", "heart rate") needs two concepts: the value column (e.g. labevents.valuenum) AND a filter on the item's code column (e.g. labevents.itemid in [50852]). If a code candidate block says the event table is not loaded, the concept is missing: list it in "missing_concepts".
- "required_tables": every table the computation needs. If the answer outputs names of coded items (e.g. "which procedures", "the most common diagnoses"), include the dictionary table and its title column; otherwise codes alone are enough. When the data is split into partitions (e.g., one table per year or per state), list **every** partition the request's scope covers, using exact names from the candidates.
- "schema_mapping": {{table: {{semantic_field: column}}}} for every required table, with short snake_case semantic field names (e.g., "year", "identity_theft_reports").
- "assumptions": an object of explicit interpretation choices the SQL planner must follow, e.g. {{"ratio_direction": "2024 / 2001", "year_range": "2002-2023 inclusive", "count_parsing": "strip commas before casting"}}. Record here how each ambiguity is resolved.
- "ambiguities": a list of {{"description", "chosen_reading", "confidence" (0-1, how sure you are the chosen reading is what the user meant), "needs_user" (true only if the data cannot settle it and a wrong reading would change the answer)}}.
- "answerable": true if the candidate tables can support the request, otherwise false.
- "missing_concepts": terms that no candidate table can support.
- "unanswerable_reason": why the request cannot be answered, or "".
- "clarification_question": one concise question to ask the user if any ambiguity needs the user, or "".
- "reasoning_confidence_score": 0-1, your overall confidence that this specification is correct and complete.

# Rules
- Use table and column names **exactly** as shown. Never invent names.
- Prefer a column or table that already records the requested quantity or judgment (a percentage, rate, flag, or category) over constructing one.
- Check sample values (or, when sample rows are withheld, the column descriptions) before mapping a filter: the stored format (case, codes, separators, year formats) must match "filter_values".
- Check coverage: compare the request's scope (years, places, categories) with what the candidates contain. If a needed partition is missing, say so in "missing_concepts".
- Relative time ("now", "currently", "this year", "last year", "hours since ..."): never mark a request unanswerable because of it. Express it against the parameter current_time, which the SQL planner supplies: put the window in "temporal_constraints" (e.g. {{"reference": "current_time", "window": "calendar year of current_time"}}), use "current_time" in "derived_from" (e.g. hours since ICU admission = current_time - icustays.intime), and do not create a concept for "now" itself.
- Do not write SQL.
""".strip()

    def get_grounding_user_prompt(
        self,
        question: str,
        interpretation: dict[str, Any],
        tables: list[TableInfo],
        families: dict[str, list[str]],
        join_hints: str,
        memory_entries: list[dict[str, Any]],
        adjustment_request: AdjustmentRequest | None = None,
        domain_notes: str = "",
        code_candidates: str = "",
    ) -> str:
        domain = f"\n{domain_notes}\n" if domain_notes else ""
        codes = f"\nCode candidates (verified to exist in this dataset):\n{code_candidates}\n" if code_candidates else ""
        adjustment = ""
        if adjustment_request is not None:
            adjustment = f"""
The SQL planner could not execute the previous specification. Fix the cause below.
Reason: {adjustment_request.reason}
Missing concepts: {adjustment_request.missing_concepts}
Suspect mappings: {adjustment_request.suspect_mappings}
"""
        return f"""
Request: {question}

Interpretation:
{json.dumps(interpretation, ensure_ascii=False, indent=1)}

Remembered context:
{self._format_memory(memory_entries)}

Candidate tables:
{self._format_tables(tables, families)}

Join hints:
{join_hints or "(none)"}
{codes}{domain}{adjustment}""".strip()

    def get_repair_prompt(self, issues: list[str]) -> str:
        """S5 -> S4 feedback: the specification failed deterministic checks."""
        listed = "\n".join(f"- {issue}" for issue in issues)
        return f"""Your specification failed these checks against the data:
{listed}

Fix them and return the complete corrected JSON object. Use only tables, columns, and codes that exist (see the candidate tables and code candidates). Ground record counts to a key column and computed quantities with "derived_from". Set "answerable" to false only if the data truly cannot support the request."""

    def get_json_retry_prompt(self, error: str) -> str:
        return f"Your previous output could not be used: {error}. Return only the corrected JSON object."

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    def _format_tables(self, tables: list[TableInfo], families: dict[str, list[str]]) -> str:
        """Renders full schemas once per partition family to keep the prompt short."""
        by_name = {table.name: table for table in tables}
        in_family = {name for members in families.values() for name in members}
        blocks: list[str] = []
        for pattern, members in families.items():
            representative = by_name[members[0]]
            blocks.append(
                f"## Partition family `{pattern}` ({len(members)} tables with the same layout)\n"
                f"Members: {', '.join(members)}\n"
                f"Layout shown for {representative.name}:\n{self._format_table(representative)}"
            )
        for table in tables:
            if table.name not in in_family:
                blocks.append(f"## {table.name}\n{self._format_table(table)}")
        return "\n\n".join(blocks) if blocks else "(none)"

    def _format_table(self, table: TableInfo) -> str:
        lines = [f"Description: {table.description or '(none)'}", "Columns:"]
        for column in table.columns:
            description = f" — {column.description}" if column.description else ""
            lines.append(f"- {column.name} ({column.type}){description}")
        lines.append("Sample rows:")
        lines.extend(json.dumps(row, ensure_ascii=False, default=str) for row in table.sample_rows)
        return "\n".join(lines)

    def _format_memory(self, memory_entries: list[dict[str, Any]]) -> str:
        if not memory_entries:
            return "(none)"
        return "\n".join(f"- {entry['content']}" for entry in memory_entries)

    def _format_history(self, history: list[LLMMessage]) -> str:
        if not history:
            return "(none)"
        return "\n".join(f"{message['role']}: {message['content']}" for message in history[-6:])
