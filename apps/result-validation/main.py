"""Final lightweight sanity review and explanation; no additional repair loop."""
from typing import Protocol

from pneumarx.contracts.results import ReviewInput, ReviewResult


class Reviewer(Protocol):
    def review(self, request: ReviewInput) -> ReviewResult: ...


class PendingReviewer:
    def review(self, request: ReviewInput) -> ReviewResult:
        return ReviewResult(status='not_implemented', review_mode='pending',
                            explanation='Independent semantic validation has not been implemented. '
                                        'SQL execution success is not independent validation.')


def main(argv=None):
    import argparse
    from pathlib import Path
    from pneumarx.shared.cli import add_model_arguments, finish, failure
    from pneumarx.shared.io import read_json

    parser = argparse.ArgumentParser(description='Lightweight review: no issue, confirmed error, or unresolved anomaly. No SQL repair.')
    add_model_arguments(parser)
    parser.add_argument('--reviewer', choices=['sanity', 'llm', 'hybrid', 'pending'], default='sanity')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = read_json(args.input)
        if 'question' not in payload and 'intent_spec' in payload:
            payload['question'] = payload['intent_spec']['question']
        request = ReviewInput.model_validate(payload)
        from pneumarx_result_validation.workflow import LightweightReviewer, presentation
        if args.reviewer == 'pending':
            result = PendingReviewer().review(request)
        elif args.reviewer == 'sanity':
            result = LightweightReviewer(mode='sanity').review(request)
        else:
            if not args.allow_private_llm:
                raise PermissionError('Model review sends question, SQL/parameters and bounded result rows; use --allow-private-llm only for your approved endpoint.')
            from pneumarx.shared.config import Config
            from pneumarx.shared.llm import configured_llm
            llm = configured_llm(Config(args.env_file, args.model))
            try:
                result = LightweightReviewer(llm, mode=args.reviewer).review(request)
            finally:
                llm.client.close()
        report = {**result.model_dump(mode='json'),
                  'presentation': presentation(result, request.execution_result.model_dump(mode='json', by_alias=True))}
        return finish('result-validation', args.output, report)
    except Exception as exc:
        return failure(exc)


if __name__ == '__main__':
    raise SystemExit(main())
