"""
Interface between Figure 2 (Task Interpretation and Schema Lookup) and its
consumers: Figure 3 (Planning and Execution) and Figure 4 (Review).

Figure 2 returns exactly one of:
- IntentSpec: requirements are clear and the data can support the task.
  Only this result is passed to Figure 3.
- ClarificationNeeded: the request is ambiguous and the user must be asked.
- Unanswerable: the available data cannot support the request.

Field names follow the Figure 3 prototype (examples/intent_spec.json);
`clinical_concepts` is generalized to `concepts`, and the schema mapping and
explicit assumptions that the prototype hard-codes are produced here instead.
"""
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

INTENT_SPEC_VERSION = "0.1"


class IntentType(str, Enum):
    LOOKUP = "lookup"  # Read one or a few stored values
    AGGREGATION = "aggregation"  # count / sum / average / min / max
    COMPARISON = "comparison"  # ratio, difference, or change between values
    RANKING = "ranking"  # top-k, most / least
    FILTER_LIST = "filter_list"  # list records or entities matching conditions
    TREND = "trend"  # change over an ordered dimension such as time
    COHORT_IDENTIFICATION = "cohort_identification"  # entities satisfying joint conditions
    OTHER = "other"


class ConceptRole(str, Enum):
    METRIC = "metric"  # The quantity being measured or returned
    FILTER = "filter"  # A condition restricting rows
    DIMENSION = "dimension"  # A grouping or ordering attribute
    ENTITY = "entity"  # The identifier of the target entity


class AnswerabilityStatus(str, Enum):
    ANSWERABLE = "answerable"
    UNANSWERABLE = "unanswerable"


class OutputSpec(BaseModel):
    """What the final answer should look like."""

    answer_type: Literal["number", "string", "list", "table", "boolean"]
    description: str = ""
    unit: str | None = None
    rounding: int | None = Field(default=None, ge=0)


class Concept(BaseModel):
    """A term in the request, grounded to a physical column."""

    term: str
    role: ConceptRole
    table: str | None = None
    column: str | None = None
    filter_values: list[Any] = Field(default_factory=list)
    value_format: str | None = None  # e.g. 'string with thousands separator, "86,250"'
    evidence: str = ""  # Why this column: name match, sample values, memory entry
    confidence: float = Field(ge=0.0, le=1.0)
    # For computed quantities (ratio, share, difference): the terms they are computed
    # from. A derived concept has no table/column of its own.
    derived_from: list[str] = Field(default_factory=list)
    # Optional, for coded domains such as biomedical data
    ontology: str | None = None
    candidate_codes: list[str] = Field(default_factory=list)


class ColumnInfo(BaseModel):
    name: str
    type: str = ""
    description: str = ""


class TableInfo(BaseModel):
    """Schema evidence for one retrieved table, as seen by Figure 2."""

    name: str  # Table id, e.g. "2024_csn_number_of_reports_by_type"
    path: str  # Fully qualified DuckDB name, e.g. 'legal."2024_csn_number_of_reports_by_type"'
    description: str = ""
    columns: list[ColumnInfo] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class JoinPath(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    score: float = 0.0  # From join path discovery; a hint, not a verified key


class ClarificationPolicy(BaseModel):
    trigger: bool = False
    reason: str = ""
    clarification_question: str = ""
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class Answerability(BaseModel):
    status: AnswerabilityStatus = AnswerabilityStatus.ANSWERABLE
    reason: str = ""
    missing_concepts: list[str] = Field(default_factory=list)


class IntentSpec(BaseModel):
    """A fully specified, data-supported task. The only result handed to Figure 3."""

    status: Literal["ready"] = "ready"
    version: str = INTENT_SPEC_VERSION
    question: str
    dataset_name: str

    intent_type: IntentType
    target_entity: str
    aggregation_level: str
    output_spec: OutputSpec
    concepts: list[Concept]
    temporal_constraints: dict[str, Any] = Field(default_factory=dict)

    required_tables: list[str]
    tables: list[TableInfo] = Field(default_factory=list)
    # {table: {semantic field: physical column}}, as consumed by Figure 3
    schema_mapping: dict[str, dict[str, str]] = Field(default_factory=dict)
    join_paths: list[JoinPath] = Field(default_factory=list)
    # Explicit interpretation choices, e.g. {"year_boundary": "inclusive"}
    assumptions: dict[str, Any] = Field(default_factory=dict)
    # Figure 1 query conventions that apply to required_tables: [{"id": ..., "rule": ...}].
    # Figure 3 must follow them when writing SQL (e.g. COUNT DISTINCT on tables with duplicate rows).
    query_conventions: list[dict[str, str]] = Field(default_factory=list)

    memory_used: list[str] = Field(default_factory=list)  # memory_id values
    reasoning_confidence_score: float = Field(ge=0.0, le=1.0)
    ambiguity_markers: list[str] = Field(default_factory=list)
    clarification_policy: ClarificationPolicy = Field(default_factory=ClarificationPolicy)
    answerability: Answerability = Field(default_factory=Answerability)

    @model_validator(mode="after")
    def _check_consistency(self) -> "IntentSpec":
        """Guarantees Figure 3 never receives an ambiguous or ungrounded spec."""
        if self.clarification_policy.trigger or self.ambiguity_markers:
            raise ValueError(
                "An IntentSpec cannot carry unresolved ambiguity; return ClarificationNeeded "
                "or record the chosen reading in `assumptions`."
            )
        if self.answerability.status != AnswerabilityStatus.ANSWERABLE:
            raise ValueError("An IntentSpec must be answerable; return Unanswerable instead.")
        if not self.required_tables:
            raise ValueError("required_tables must not be empty.")

        required = set(self.required_tables)
        known = {table.name for table in self.tables}
        if self.tables and not required <= known:
            raise ValueError(f"required_tables without schema evidence: {sorted(required - known)}")
        for concept in self.concepts:
            if concept.table is not None and concept.table not in required:
                raise ValueError(f"Concept '{concept.term}' uses table '{concept.table}' not in required_tables.")
        if not set(self.schema_mapping) <= required:
            raise ValueError("schema_mapping references tables not in required_tables.")
        return self

    def to_figure3_view(self, max_sample_rows: int = 3) -> dict[str, Any]:
        """
        The subset of this spec that SQL planning needs. Omits fields that are fixed
        for any IntentSpec (status, answerability, clarification) and audit fields
        used by Figure 4 (evidence, confidence, memory_used). Keep each physical
        table and its descriptions: identical column layouts do not imply that
        tables represent the same entity or code system.
        """
        concepts = [
            {
                key: value
                for key, value in concept.model_dump(mode="json").items()
                if key in ("term", "role", "table", "column", "filter_values", "value_format", "derived_from")
                and value not in (None, [], "")
            }
            for concept in self.concepts
        ]

        tables = []
        for table in self.tables:
            entry = {
                "name": table.name,
                "path": table.path,
                "description": table.description,
                "columns": [
                    {"name": c.name, "type": c.type, **({"description": c.description} if c.description else {})}
                    for c in table.columns
                ],
                "sample_rows": table.sample_rows[:max_sample_rows],
            }
            tables.append(entry)

        return {
            "question": self.question,
            "dataset_name": self.dataset_name,
            "intent_type": self.intent_type.value,
            "target_entity": self.target_entity,
            "aggregation_level": self.aggregation_level,
            "output_spec": self.output_spec.model_dump(mode="json"),
            "concepts": concepts,
            "temporal_constraints": self.temporal_constraints,
            "required_tables": self.required_tables,
            "tables": tables,
            "schema_mapping": self.schema_mapping,
            "join_paths": [
                {k: v for k, v in path.model_dump(mode="json").items() if k != "score"}
                for path in self.join_paths
            ],
            "assumptions": self.assumptions,
            "query_conventions": self.query_conventions,
        }

    def to_figure3_inputs(self) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, Any]]:
        """Returns (compact spec, schema_mapping, assumptions) as the Figure 3 prototype expects."""
        return self.to_figure3_view(), self.schema_mapping, self.assumptions


class ClarificationNeeded(BaseModel):
    """The request is ambiguous in a way the data cannot settle; ask the user."""

    status: Literal["needs_clarification"] = "needs_clarification"
    version: str = INTENT_SPEC_VERSION
    question: str
    dataset_name: str
    ambiguity_markers: list[str]
    clarification_questions: list[str]
    candidate_tables: list[str] = Field(default_factory=list)


class Unanswerable(BaseModel):
    """The available data cannot support the request."""

    status: Literal["unanswerable"] = "unanswerable"
    version: str = INTENT_SPEC_VERSION
    question: str
    dataset_name: str
    reason: str
    missing_concepts: list[str] = Field(default_factory=list)
    searched_tables: list[str] = Field(default_factory=list)


Figure2Result = IntentSpec | ClarificationNeeded | Unanswerable


class AdjustmentRequest(BaseModel):
    """Sent by Figure 3 (via the workflow layer) when the spec cannot be executed as given."""

    reason: str
    missing_concepts: list[str] = Field(default_factory=list)
    suspect_mappings: list[str] = Field(default_factory=list)  # e.g. ["table.column"]
