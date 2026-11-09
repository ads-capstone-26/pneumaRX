"""Programmatic data-processing boundary; no LLM or network calls."""
from dataclasses import dataclass
from pathlib import Path

from pneumarx_data.inventory import run_inventory
from pneumarx_data.loader import load_all, results_to_dict
from pneumarx_data.quality import run_quality
from pneumarx_data.profile import build_profile
from pneumarx_data.snapshot import fingerprint, write_snapshot
from pneumarx.shared.io import read_json, write_json
from pneumarx.shared.paths import DEFAULT_DB, PROJECT_ROOT


@dataclass(frozen=True)
class PreparationRequest:
    stage: str
    source_dir: Path | None = None
    db_path: Path = DEFAULT_DB
    report_dir: Path = PROJECT_ROOT / 'data/mimic_iii/reports'
    snapshot_dir: Path = PROJECT_ROOT / 'docs/mimic3'
    tables: list[str] | None = None
    memory_limit: str | None = None
    threads: int | None = None
    dataset_config: Path | None = None


def run(request: PreparationRequest) -> dict:
    if request.dataset_config is not None:
        from pneumarx_data.dataset import run_configured
        return run_configured(request)
    stages = ['inventory', 'load', 'quality', 'profile'] if request.stage == 'all' else [request.stage]
    if any(s not in {'inventory', 'load', 'quality', 'profile', 'publish'} for s in stages):
        raise ValueError('Unknown preparation stage')
    artifacts, inventory, quality = {}, None, None
    attention = []
    for stage in stages:
        if stage in {'inventory', 'load'}:
            if request.source_dir is None:
                raise ValueError('A source directory is required for inventory/load')
            inventory = inventory or run_inventory(request.source_dir)
            if stage == 'inventory':
                payload = inventory.to_dict()
                if inventory.problems:
                    attention.append('Inventory has missing or malformed expected files')
            else:
                if not inventory.loadable:
                    raise ValueError('No loadable source tables; existing database left unchanged')
                if inventory.problems and request.tables is None:
                    raise ValueError('Inventory has problems; fix the source files or explicitly select --tables before loading')
                loaded = load_all(inventory, request.db_path, request.tables,
                                  request.memory_limit, request.threads, progress=lambda _: None)
                payload = {'tables': results_to_dict(loaded)}
                attention.extend(f'{r.table}: {r.status}' for r in loaded if not r.status.startswith('ok'))
        elif stage == 'quality':
            quality = run_quality(request.db_path, progress=lambda _: None)
            payload = quality.to_dict()
            if any(c.status == 'error' for c in quality.checks):
                attention.append('Some data quality checks failed to execute')
        elif stage == 'profile':
            evidence = quality.to_dict() if quality else read_json(request.report_dir / 'quality.json')
            payload = build_profile(request.db_path, evidence)
        else:
            quality = run_quality(request.db_path, progress=lambda _: None)
            profile = build_profile(request.db_path, quality.to_dict())
            written = write_snapshot(quality, fingerprint(request.db_path),
                                     request.snapshot_dir, profile=profile)
            payload = {k: str(v) for k, v in written.items()}
        output = request.report_dir / f'{stage}.json'
        write_json(output, payload)
        artifacts[stage] = str(output)
    return {'version': '0.1', 'component': 'data-processing',
            'status': 'needs_attention' if attention else 'success',
            'database': str(request.db_path), 'artifacts': artifacts, 'issues': attention}


def main(argv=None):
    import argparse
    from pneumarx.shared.cli import finish, failure
    from pneumarx_data.paths import resolve_mimic_dir

    parser = argparse.ArgumentParser(description='Prepare CSV datasets or profile existing DuckDB databases; MIMIC defaults remain supported.')
    parser.add_argument('stage', choices=['inventory', 'load', 'quality', 'profile', 'all', 'publish'])
    parser.add_argument('--mimic-dir', type=Path, help='Legacy MIMIC source directory')
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--dataset-config', type=Path, help='Explicit dataset definition JSON')
    parser.add_argument('--db', type=Path)
    parser.add_argument('--report-dir', type=Path)
    parser.add_argument('--snapshot-dir', type=Path)
    parser.add_argument('--tables', help='Comma-separated table names')
    parser.add_argument('--memory-limit')
    parser.add_argument('--threads', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = args.source_dir or args.mimic_dir
        if args.dataset_config:
            from pneumarx.contracts.dataset import DatasetDefinition
            name = DatasetDefinition.load(args.dataset_config).dataset
            args.db = args.db or PROJECT_ROOT / "data" / name / (name + ".db")
            args.report_dir = args.report_dir or PROJECT_ROOT / "data" / name / "reports"
            args.snapshot_dir = args.snapshot_dir or PROJECT_ROOT / "docs" / "datasets" / name
        else:
            args.db = args.db or DEFAULT_DB
            args.report_dir = args.report_dir or PROJECT_ROOT / "data/mimic_iii/reports"
            args.snapshot_dir = args.snapshot_dir or PROJECT_ROOT / "docs/mimic3"
        if not args.dataset_config and args.stage in {'inventory', 'load', 'all'}:
            source = resolve_mimic_dir(str(source) if source else None)
        request = PreparationRequest(args.stage, source, args.db, args.report_dir,
                                     args.snapshot_dir, args.tables.split(',') if args.tables else None,
                                     args.memory_limit, args.threads, args.dataset_config)
        return finish('data-processing', args.output, run(request))
    except Exception as exc:
        return failure(exc)


if __name__ == '__main__':
    raise SystemExit(main())
