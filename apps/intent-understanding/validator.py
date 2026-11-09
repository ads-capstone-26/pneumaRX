"""
Deterministic (non-LLM) steps of Figure 2: turning retrieved documents into
schema evidence, detecting partitioned tables, removing hallucinated names
from the grounding output, and deciding which result type to return.
"""
import math
import re
from typing import Any

from pneumarx.contracts.intent import (
    Answerability,
    AnswerabilityStatus,
    ClarificationNeeded,
    ClarificationPolicy,
    ColumnInfo,
    Concept,
    ConceptRole,
    Figure2Result,
    IntentSpec,
    IntentType,
    JoinPath,
    OutputSpec,
    TableInfo,
    Unanswerable,
)

# Query parameters that Figure 3 supplies at execution time (relative dates have no
# real anchor in de-identified, date-shifted data).
QUERY_PARAMETERS = {"current_time"}
_PARAMETER_ALIASES = {"current time": "current_time", "now": "current_time", "current_date": "current_time",
                      "current date": "current_time", "today": "current_time"}


# ----------------------------------------------------------------------
# Schema evidence
# ----------------------------------------------------------------------






# ----------------------------------------------------------------------
# Grounding validation
# ----------------------------------------------------------------------
def validate_grounding(
    grounding: dict[str, Any], tables: list[TableInfo]
) -> tuple[list[Concept], list[str], dict[str, dict[str, str]], list[str]]:
    """
    Keeps only table/column names that exist among the candidates.
    Returns (concepts, required_tables, schema_mapping, issues).
    """
    columns_by_table = {table.name: {c.name for c in table.columns} for table in tables}
    issues: list[str] = []

    concepts: list[Concept] = []
    for raw in grounding.get("concepts", []) or []:
        if not isinstance(raw, dict) or not raw.get("term"):
            continue
        table = _resolve_name(raw.get("table"), columns_by_table.keys())
        column = None
        if raw.get("table") and table is None:
            issues.append(f"Concept '{raw['term']}': unknown table '{raw.get('table')}'")
        if table is not None and raw.get("column"):
            column = _resolve_name(raw.get("column"), columns_by_table[table])
            if column is None:
                issues.append(f"Concept '{raw['term']}': unknown column '{table}.{raw.get('column')}'")
        concepts.append(
            Concept(
                term=str(raw["term"]),
                role=_coerce_enum(ConceptRole, raw.get("role"), ConceptRole.FILTER),
                table=table if column is not None or not raw.get("column") else None,
                column=column,
                filter_values=list(raw.get("filter_values") or []),
                value_format=raw.get("value_format"),
                evidence=str(raw.get("evidence") or ""),
                confidence=_clamp(raw.get("confidence"), default=0.5),
                derived_from=[_PARAMETER_ALIASES.get(str(t).strip().lower(), str(t)) for t in raw.get("derived_from") or [] if t],
                ontology=raw.get("ontology") or None,
                candidate_codes=[str(c) for c in raw.get("candidate_codes") or [] if c is not None],
            )
        )
    # A derived concept is grounded if every input is a grounded term, an existing
    # "table.column", or another grounded derived concept (resolved to a fixpoint).
    valid_inputs = {c.term for c in concepts if c.table and c.column}
    valid_inputs |= {f"{table}.{column}" for table, columns in columns_by_table.items() for column in columns}
    valid_inputs |= QUERY_PARAMETERS
    pending = [c for c in concepts if c.derived_from]
    changed = True
    while changed:
        changed = False
        for concept in list(pending):
            if set(concept.derived_from) <= valid_inputs:
                valid_inputs.add(concept.term)
                pending.remove(concept)
                changed = True
    for concept in pending:
        issues.append(f"Concept '{concept.term}' is derived from ungrounded terms {concept.derived_from}")
        concept.derived_from = []

    required_tables: list[str] = []
    for name in grounding.get("required_tables", []) or []:
        resolved = _resolve_name(name, columns_by_table.keys())
        if resolved is None:
            issues.append(f"Unknown required table '{name}'")
        elif resolved not in required_tables:
            required_tables.append(resolved)
    for concept in concepts:  # A grounded concept's table is always required
        if concept.table and concept.table not in required_tables:
            required_tables.append(concept.table)
        for ref in concept.derived_from:  # ...and so is a table used as a "table.column" input
            ref_table = ref.split(".", 1)[0] if "." in ref else None
            if ref_table in columns_by_table and ref_table not in required_tables:
                required_tables.append(ref_table)

    schema_mapping: dict[str, dict[str, str]] = {}
    for name, fields in (grounding.get("schema_mapping") or {}).items():
        table = _resolve_name(name, required_tables)
        if table is None or not isinstance(fields, dict):
            continue
        kept = {}
        for field, column in fields.items():
            resolved = _resolve_name(column, columns_by_table[table])
            if resolved is None:
                issues.append(f"schema_mapping: unknown column '{table}.{column}'")
            else:
                kept[str(field)] = resolved
        if kept:
            schema_mapping[table] = kept
    return concepts, required_tables, schema_mapping, issues


# ----------------------------------------------------------------------
# Decision
# ----------------------------------------------------------------------
def ungrounded_terms(concepts: list[Concept]) -> list[str]:
    """Metrics and filters with neither a column nor grounded inputs."""
    return [
        c.term for c in concepts
        if c.role in (ConceptRole.METRIC, ConceptRole.FILTER)
        and (c.table is None or c.column is None)
        and not c.derived_from
        and _PARAMETER_ALIASES.get(c.term.strip().lower(), c.term) not in QUERY_PARAMETERS
    ]


def repairable_issues(grounding: dict[str, Any], tables: list[TableInfo]) -> list[str]:
    """
    Problems worth one S4 repair round: unknown names and ungrounded metrics/filters.
    Not raised when the model itself judged the request unanswerable.
    """
    if grounding.get("answerable") is False:
        return []
    concepts, required_tables, _, issues = validate_grounding(grounding, tables)
    issues = list(issues)
    issues += [f"Concept '{term}' has no table/column and no grounded inputs" for term in ungrounded_terms(concepts)]
    if not required_tables:
        issues.append("No required table was selected")
    return issues


def unsupported_refusal(grounding: dict[str, Any], tables: list[TableInfo]) -> list[str]:
    """
    An "unanswerable" verdict that names no missing data although every metric and
    filter is mapped to an existing column: worth one S4 repair round.
    """
    if grounding.get("answerable") is not False or grounding.get("missing_concepts"):
        return []
    concepts, _, _, _ = validate_grounding(grounding, tables)
    if not any(c.table and c.column for c in concepts) or ungrounded_terms(concepts):
        return []
    return [
        "You marked the request unanswerable, but every concept is mapped to an existing column and "
        "\"missing_concepts\" is empty. If some required data really does not exist in the tables, list it in "
        "\"missing_concepts\"; otherwise set \"answerable\" to true."
    ]


def decide(
    question: str,
    dataset_name: str,
    interpretation: dict[str, Any],
    grounding: dict[str, Any],
    tables: list[TableInfo],
    join_paths: list[JoinPath],
    memory_used: list[str],
    interactive: bool,
    threshold: float,
    value_issues: list[str] | None = None,
) -> Figure2Result:
    """Chooses IntentSpec, ClarificationNeeded, or Unanswerable."""
    concepts, required_tables, schema_mapping, issues = validate_grounding(grounding, tables)
    issues = issues + list(value_issues or [])
    candidate_names = [table.name for table in tables]

    # Unanswerable: the model says so, or a metric/filter could not be grounded.
    ungrounded = ungrounded_terms(concepts)
    missing = list(dict.fromkeys(list(grounding.get("missing_concepts") or []) + ungrounded))
    if grounding.get("answerable") is False or not required_tables or ungrounded:
        reason = grounding.get("unanswerable_reason") or (
            f"No candidate table supports: {', '.join(missing)}" if missing else "No usable table found"
        )
        if issues:
            reason += f" (validation: {'; '.join(issues[:3])})"
        return Unanswerable(
            question=question,
            dataset_name=dataset_name,
            reason=reason,
            missing_concepts=missing,
            searched_tables=candidate_names,
        )

    ambiguities = [a for a in grounding.get("ambiguities") or [] if isinstance(a, dict)]
    reasoning_confidence = _clamp(grounding.get("reasoning_confidence_score"), default=0.5)
    concept_confidence = min((c.confidence for c in concepts), default=reasoning_confidence)
    confidence = min(reasoning_confidence, concept_confidence)

    # Clarification: only when a user is available to answer.
    unsure = [
        a for a in ambiguities
        if a.get("needs_user") or _clamp(a.get("confidence"), default=1.0) < threshold
    ]
    if interactive and (unsure or confidence < threshold):
        markers = [str(a.get("description", "")) for a in unsure] or [
            f"Low confidence in the specification ({confidence:.2f} < {threshold})"
        ]
        clarification = grounding.get("clarification_question") or (
            "Could you clarify: " + "; ".join(markers)
        )
        return ClarificationNeeded(
            question=question,
            dataset_name=dataset_name,
            ambiguity_markers=markers,
            clarification_questions=[clarification],
            candidate_tables=required_tables,
        )

    # Otherwise resolve every ambiguity into an explicit assumption.
    assumptions = dict(grounding.get("assumptions") or {})
    for index, ambiguity in enumerate(ambiguities, start=1):
        key = f"ambiguity_{index}"
        if ambiguity.get("chosen_reading") and key not in assumptions:
            assumptions[key] = f"{ambiguity.get('description', '')} -> {ambiguity['chosen_reading']}"
    if issues:
        assumptions["figure2_validation_notes"] = issues

    required = set(required_tables)
    output_spec = interpretation.get("output_spec") or {}
    return IntentSpec(
        question=question,
        dataset_name=dataset_name,
        intent_type=_coerce_enum(IntentType, interpretation.get("intent_type"), IntentType.OTHER),
        target_entity=str(interpretation.get("target_entity") or ""),
        aggregation_level=str(interpretation.get("aggregation_level") or ""),
        output_spec=OutputSpec(
            answer_type=output_spec.get("answer_type")
            if output_spec.get("answer_type") in ("number", "string", "list", "table", "boolean")
            else "string",
            description=str(output_spec.get("description") or ""),
            unit=output_spec.get("unit"),
            rounding=output_spec.get("rounding") if isinstance(output_spec.get("rounding"), int) else None,
        ),
        concepts=concepts,
        temporal_constraints=interpretation.get("temporal_constraints") or {},
        required_tables=required_tables,
        tables=[table for table in tables if table.name in required],
        schema_mapping=schema_mapping,
        join_paths=[p for p in join_paths if p.left_table in required and p.right_table in required],
        assumptions=assumptions,
        memory_used=memory_used,
        reasoning_confidence_score=confidence,
        ambiguity_markers=[],
        clarification_policy=ClarificationPolicy(
            trigger=False,
            reason="Resolved without user input; see assumptions." if ambiguities else "No ambiguity found.",
            threshold=threshold,
        ),
        answerability=Answerability(status=AnswerabilityStatus.ANSWERABLE),
    )


def drop_key_only_tables(spec: IntentSpec, key_only_tables: dict[str, tuple[str, ...]]) -> IntentSpec:
    """Removes a required table whose concepts use only key columns that another required
    table also has (e.g. patients used just for subject_id next to diagnoses_icd). Concepts
    and schema_mapping entries move to that table."""
    for table, keys in key_only_tables.items():
        if table not in spec.required_tables or len(spec.required_tables) < 2:
            continue
        used = {c.column for c in spec.concepts if c.table == table}
        used |= set(spec.schema_mapping.get(table, {}).values())
        if not used <= set(keys):
            continue
        columns = {t.name: {c.name for c in t.columns} for t in spec.tables}
        others = [t for t in spec.required_tables if t != table]
        target = next((t for t in others if used <= columns.get(t, set())), None)
        if target is None:
            continue
        concepts = [c.model_copy(update={"table": target}) if c.table == table else c for c in spec.concepts]
        mapping = {t: dict(m) for t, m in spec.schema_mapping.items() if t != table}
        if spec.schema_mapping.get(table):
            mapping.setdefault(target, {}).update(spec.schema_mapping[table])
        assumptions = dict(spec.assumptions)
        assumptions.setdefault("figure2_validation_notes", [])
        assumptions["figure2_validation_notes"] = list(assumptions["figure2_validation_notes"]) + [
            f"Dropped {table}: only {', '.join(sorted(used)) or 'no columns'} used, available in {target}."]
        spec = spec.model_copy(update={
            "required_tables": others,
            "tables": [t for t in spec.tables if t.name != table],
            "concepts": concepts,
            "schema_mapping": mapping,
            "join_paths": [p for p in spec.join_paths if table not in (p.left_table, p.right_table)],
            "assumptions": assumptions,
        })
    return spec


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _resolve_name(name: Any, known) -> str | None:
    """Exact match first, then a case/whitespace-insensitive match."""
    if not isinstance(name, str) or not name.strip():
        return None
    known = list(known)
    if name in known:
        return name
    normalized = re.sub(r"\W+", "_", name.strip().strip('"').lower()).strip("_")
    for candidate in known:
        if re.sub(r"\W+", "_", candidate.lower()).strip("_") == normalized:
            return candidate
    return None


def _coerce_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _clamp(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return max(0.0, min(1.0, number))
