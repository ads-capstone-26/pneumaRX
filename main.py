"""Select an application. Implementation and arguments are owned by that app."""
import importlib
import sys

COMMANDS = {
    'data-processing': 'pneumarx_data.main',
    'intent-understanding': 'pneumarx_intent_understanding.main',
    'query-execution': 'pneumarx_query_execution.main',
    'result-validation': 'pneumarx_result_validation.main',
    'run': 'pneumarx_pipeline.main',
}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {'-h', '--help'}:
        print('Usage: python main.py {' + ','.join([*COMMANDS, 'demo']) + '} [app arguments]')
        return 0
    command = args.pop(0)
    if command == 'demo':
        command, args = 'run', ['--demo', *args]
    if command not in COMMANDS:
        print(f'Unknown app: {command}', file=sys.stderr)
        return 2
    return importlib.import_module(COMMANDS[command]).main(args)


if __name__ == '__main__':
    raise SystemExit(main())
