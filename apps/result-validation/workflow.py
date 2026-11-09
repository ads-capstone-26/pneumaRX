"""Lightweight Figure 4 / paper Figure 5 review. No repair or database tools."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pneumarx.contracts.results import ReviewInput, ReviewResult
from pneumarx.shared.messages import LLMMessage
from pneumarx.shared.options import LLMOption
from pneumarx_result_validation.checks import EvidenceReviewer
from pneumarx_result_validation.prompt_factory import SYSTEM_PROMPT, evidence_matches, review_payload

REQUIRED_ASPECTS = {'intent_alignment', 'output_shape', 'filters_and_codes', 'joins_and_grain',
                    'time_and_units', 'duplicates_and_missingness', 'result_interpretation'}

SCOPE = 'Lightweight result sanity review; no correctness certificate or independent population verification.'


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Finding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(min_length=1)
    aspect: Literal['intent_alignment', 'output_shape', 'filters_and_codes', 'joins_and_grain',
                    'time_and_units', 'duplicates_and_missingness', 'result_interpretation']
    status: Literal['pass', 'fail', 'unknown', 'not_applicable']
    evidence: list[Evidence] = Field(min_length=1)
    reason: str = Field(min_length=1)


class ModelReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['passed', 'error_detected', 'insufficient_evidence']
    explanation: str = Field(min_length=1)
    result_explanation: str
    checks: list[Finding] = Field(min_length=1)
    limitations: list[str]

    @model_validator(mode='after')
    def consistent(self):
        states = {c.status for c in self.checks}
        if {c.aspect for c in self.checks} != REQUIRED_ASPECTS:
            raise ValueError('Review must address every required aspect')
        if len({c.code for c in self.checks}) != len(self.checks):
            raise ValueError('Review check codes must be unique')
        if any(c.status == 'not_applicable' and c.aspect in {'intent_alignment', 'output_shape', 'result_interpretation'} for c in self.checks):
            raise ValueError('Core review aspects cannot be declared inapplicable')
        if self.status == 'error_detected' and 'fail' not in states:
            raise ValueError('Error verdict requires an evidenced failing check')
        if self.status == 'passed' and not states <= {'pass', 'not_applicable'}:
            raise ValueError('Passed verdict conflicts with unresolved/failed checks')
        if self.status == 'insufficient_evidence' and 'fail' in states:
            raise ValueError('A confirmed fail must not be hidden as an anomaly')
        return self


def local_checks(request):
    checks = EvidenceReviewer().review(request).checks
    rows = request.execution_result.rows
    names = [c['name'] for c in request.execution_result.result_schema]
    answer_type = request.intent_spec.get('output_spec', {}).get('answer_type')
    if answer_type not in {'number', 'string', 'boolean', 'list', 'table'}:
        checks.append({'code': 'output_contract', 'status': 'unknown',
                       'evidence': {'answer_type': answer_type}, 'reason': 'Expected output type is unspecified or unsupported.'})
    if answer_type == 'list':
        checks.append({'code': 'list_shape', 'status': 'pass' if len(names) == 1 else 'fail',
                       'evidence': {'expected_columns': 1, 'observed_columns': len(names)}})
    if len(rows) == len(names) == 1:
        value = rows[0].get(names[0])
        if value is not None and answer_type in {'string', 'boolean'}:
            expected_type = str if answer_type == 'string' else bool
            checks.append({'code': 'scalar_type', 'status': 'pass' if isinstance(value, expected_type) else 'fail',
                           'evidence': {'expected': answer_type, 'observed_type': type(value).__name__}})
    extra = request.execution_result.model_extra or {}
    if 'answer' in extra:
        consistent = len(rows) == len(names) == 1
        if consistent:
            actual, displayed = rows[0].get(names[0]), extra['answer']
            if answer_type == 'number' and actual is not None and displayed is not None:
                from decimal import Decimal, InvalidOperation
                try:
                    consistent = not isinstance(actual, bool) and not isinstance(displayed, bool) and Decimal(str(actual)) == Decimal(str(displayed))
                except (InvalidOperation, ValueError):
                    consistent = False
            else:
                consistent = type(actual) is type(displayed) and actual == displayed
        checks.append({'code': 'answer_consistency', 'status': 'pass' if consistent else 'fail',
                       'evidence': {'matches_single_result_cell': consistent},
                       'reason': 'The displayed scalar answer must agree with the materialized result.'})
    duplicates = len(rows) - len({json.dumps(r, sort_keys=True, default=str) for r in rows})
    nulls = sum(v is None for row in rows for v in row.values())
    if duplicates:
        checks.append({'code': 'duplicate_rows', 'status': 'unknown',
                       'evidence': {'extra_identical_rows': duplicates},
                       'reason': 'Duplicates may be valid; no independently verified uniqueness requirement.'})
    if nulls:
        checks.append({'code': 'missing_values', 'status': 'unknown',
                       'evidence': {'null_cells': nulls},
                       'reason': 'NULL may be legitimate; completeness and its impact need interpretation.'})
    if not rows:
        checks.append({'code': 'empty_result', 'status': 'unknown',
                       'evidence': {'rows': 0}, 'reason': 'Empty output alone is not an error.'})
    return checks


class LightweightReviewer:
    def __init__(self, llm=None, *, mode='hybrid', max_rows=20, max_payload_chars=80000):
        if mode not in {'sanity', 'llm', 'hybrid'}:
            raise ValueError('Unknown review mode')
        if mode != 'sanity' and llm is None:
            raise ValueError('LLM and hybrid review require a configured model')
        if max_rows < 1 or max_payload_chars < 1:
            raise ValueError('Review input limits must be positive')
        self.llm, self.mode = llm, mode
        self.max_rows, self.max_payload_chars = max_rows, max_payload_chars

    def review(self, request: ReviewInput) -> ReviewResult:
        model_calls = 0
        local = local_checks(request) if self.mode != 'llm' else []
        checks = [dict(c, source='deterministic') for c in local]
        limitations = [SCOPE]
        explanation = 'No inconsistency found in the performed lightweight checks.'
        result_explanation = f'Execution returned {request.execution_result.row_count} row(s); output columns: ' + ', '.join(c['name'] for c in request.execution_result.result_schema) + '.'
        if self.mode == 'sanity':
            limitations.append('Semantic alignment has not been reviewed by a model or an independent database check.')
        else:
            failure_detail = {}
            try:
                payload = review_payload(request, local, self.max_rows)
                if payload['execution_result']['rows_truncated']:
                    limitations.append('Only a bounded row preview was sent to the model.')
                    checks.append({'code': 'preview_coverage', 'status': 'unknown', 'source': 'input_scope',
                                   'evidence': {'max_rows': self.max_rows},
                                   'reason': 'The model did not review every result row.'})
                encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                if len(encoded) > self.max_payload_chars:
                    raise ValueError('Review payload exceeds configured limit')
                model_calls += 1
                raw = ''.join(self.llm.chat([
                    LLMMessage(role='system', content=SYSTEM_PROMPT),
                    LLMMessage(role='user', content=encoded)],
                    LLMOption(json_mode=True, stream=False, max_new_tokens=3000, temperature=0)))
                model = ModelReview.model_validate_json(raw)
                invalid_paths = [e.path for c in model.checks for e in c.evidence
                                 if not evidence_matches(payload, e.path, e.quote)]
                if invalid_paths:
                    failure_detail = {'failure_kind': 'evidence_mismatch',
                                      'invalid_paths': list(dict.fromkeys(invalid_paths))}
                    raise ValueError('Review cites absent input evidence')
                checks.extend(dict(c.model_dump(), source='llm_judgment') for c in model.checks)
                if model.status == 'insufficient_evidence' and not any(c.status == 'unknown' for c in model.checks):
                    checks.append({'code': 'model_uncertainty', 'status': 'unknown', 'source': 'llm_judgment',
                                   'evidence': model.explanation})
                limitations.extend(model.limitations)
                explanation, result_explanation = model.explanation, model.result_explanation
            except Exception as exc:
                if isinstance(exc, ValidationError):
                    failure_detail = {'failure_kind': 'review_contract',
                                      'violations': [{'path': list(e['loc']), 'type': e['type']}
                                                     for e in exc.errors(include_input=False, include_context=False)]}
                checks.append({'code': 'review_unavailable', 'status': 'unknown', 'source': 'review_workflow',
                               'evidence': {'error_type': type(exc).__name__, **failure_detail},
                               'reason': 'Model response unavailable, malformed, or unsupported by supplied evidence; no retry.'})
        failures = [c['code'] for c in checks if c['status'] == 'fail']
        unknown = [c['code'] for c in checks if c['status'] == 'unknown']
        status = 'error_detected' if failures else 'insufficient_evidence' if unknown else 'passed'
        if failures:
            explanation = 'Detected inconsistencies: ' + ', '.join(failures) + '. The result must not be presented as valid.'
            result_explanation = ''
        elif unknown:
            explanation = 'Unresolved findings: ' + ', '.join(unknown) + '. ' + explanation
        return ReviewResult(status=status, explanation=explanation, checks=checks,
                            review_mode=self.mode, model_calls=model_calls,
                            scope=SCOPE, limitations=list(dict.fromkeys(limitations)),
                            result_explanation=result_explanation)


def presentation(review, execution_result):
    status = review.status
    return {'disposition': 'withheld' if status == 'error_detected' else
                           'with_caveats' if status != 'passed' else 'reviewed',
            'result': None if status == 'error_detected' else execution_result,
            'review_status': status, 'explanation': review.explanation,
            'result_explanation': review.result_explanation,
            'limitations': review.limitations, 'scope': review.scope}
