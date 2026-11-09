"""Versioned JSON boundaries for planning, execution and independent review."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = '0.1'


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra='allow')
    dialect: Literal['duckdb']
    steps: list[str] = Field(default_factory=list)
    sql: str = Field(min_length=1)
    parameters: list[Any]


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    result_schema: list[dict[str, str]] = Field(alias='schema')
    row_count: int = Field(ge=0)
    storage: Literal['inline']
    result_reference: str
    rows: list[dict[str, Any]]
    preview: list[dict[str, Any]]


class ReviewInput(BaseModel):
    version: Literal['0.1'] = CONTRACT_VERSION
    question: str
    intent_spec: dict[str, Any]
    query_plan: QueryPlan
    execution_result: ExecutionResult


class ReviewResult(BaseModel):
    version: Literal['0.1'] = CONTRACT_VERSION
    status: Literal['not_implemented', 'passed', 'error_detected', 'insufficient_evidence']
    explanation: str
    checks: list[dict[str, Any]] = Field(default_factory=list)

    scope: str = 'Unspecified review scope'
    limitations: list[str] = Field(default_factory=list)
    result_explanation: str = ''
    review_mode: Literal['sanity', 'llm', 'hybrid', 'pending', 'custom'] = 'custom'
    model_calls: int = Field(default=0, ge=0)
