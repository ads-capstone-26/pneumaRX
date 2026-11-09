"""Opt-in structural/result checks. Passing these is not semantic validation."""
import math

from pneumarx.contracts.results import ReviewInput, ReviewResult


class EvidenceReviewer:
    """No gold answers, model calls, SQL rewriting, or clinical inference."""
    def review(self, request: ReviewInput) -> ReviewResult:
        result = request.execution_result
        checks = []

        def record(code, passed, evidence):
            checks.append({'code': code, 'status': 'pass' if passed else 'fail', 'evidence': evidence})

        record('row_count', result.row_count == len(result.rows),
               {'declared': result.row_count, 'materialized': len(result.rows)})
        names = [column['name'] for column in result.result_schema]
        record('row_schema', len(names) == len(set(names)) and all(set(row) == set(names) for row in result.rows),
               {'columns': names})
        output = request.intent_spec.get('output_spec', {})
        if output.get('answer_type') in {'number', 'string', 'boolean'}:
            scalar = len(names) == 1 and result.row_count == 1 and len(result.rows) == 1
            record('scalar_shape', scalar, {'rows': result.row_count, 'columns': len(names)})
            if scalar and output['answer_type'] == 'number':
                value = result.rows[0].get(names[0])
                try:
                    valid_number = not isinstance(value, bool) and (value is None or math.isfinite(float(value)))
                except (TypeError, ValueError, OverflowError):
                    valid_number = False
                record('finite_number', valid_number, {'is_null': value is None})
                bounds = request.intent_spec.get('validation_requirements', {}).get('numeric_range')
                if bounds is not None:
                    if not isinstance(bounds, list) or len(bounds) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bounds) or bounds[0] > bounds[1]:
                        raise ValueError('Invalid explicit numeric_range in validation contract')
                    if valid_number and value is not None:
                        record('numeric_range', bounds[0] <= float(value) <= bounds[1], {'range': bounds})
        failures = [c['code'] for c in checks if c['status'] == 'fail']
        return ReviewResult(
            status='error_detected' if failures else 'insufficient_evidence',
            explanation=('Failed deterministic checks: ' + ', '.join(failures)) if failures else
                        'Structural checks passed; clinical scope, filters, joins, grain and denominator are not independently verified.',
            checks=checks)
