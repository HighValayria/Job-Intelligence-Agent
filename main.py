from __future__ import annotations

import argparse
import sys
from pathlib import Path

from annotation import draft_gold, promote_gold, render_draft_summary
from collectors.html_snapshot import (
    inventory_html_snapshots,
    render_html_snapshot_inventory,
)
from collectors.real_fixture import RealSampleLoader
from config_loader import load_project_config
from evaluation import evaluate_samples, render_report
from inspection import inspect_sample
from scheduler.provider_factory import (
    create_collector,
    create_llm_provider,
    create_ocr_provider,
)
from scheduler.runner import PipelineRunner


def main() -> None:
    _configure_utf8_stdio()
    args = _parse_args()
    if args.command == "llm-status":
        config = load_project_config(args.config_dir)
        provider = create_llm_provider("real", config)
        status = provider.configuration_status()
        for key, value in status.items():
            print(f"{key}: {value}")
        return
    if args.command == "inventory":
        inventory = RealSampleLoader(args.samples_root).inventory()
        for key, value in inventory.items():
            print(f"{key}: {value}")
        return
    if args.command == "inbox-inventory":
        inventory = inventory_html_snapshots(args.inbox_dir)
        print(render_html_snapshot_inventory(inventory, limit=args.limit))
        return
    if args.command == "evaluate":
        config = load_project_config(args.config_dir)
        report = evaluate_samples(
            args.samples_root,
            llm_provider=create_llm_provider(args.llm, config),
            ocr_provider=create_ocr_provider(args.ocr),
        )
        print(render_report(report))
        return
    if args.command == "inspect":
        config = load_project_config(args.config_dir)
        print(
            inspect_sample(
                args.sample_dir,
                llm_provider=create_llm_provider(args.llm, config),
                ocr_provider=create_ocr_provider(args.ocr),
            )
        )
        return
    if args.command == "draft-gold":
        config = load_project_config(args.config_dir)
        summary = draft_gold(
            args.samples_root,
            llm_provider=create_llm_provider(args.llm, config),
            ocr_provider=create_ocr_provider(args.ocr),
            sample_dir=args.sample_dir,
            output_name=args.output_name,
            overwrite=args.overwrite,
            include_existing_gold=args.include_existing_gold,
        )
        print(render_draft_summary(summary))
        return
    if args.command == "promote-gold":
        summary = promote_gold(
            args.samples_root,
            sample_dir=args.sample_dir,
            draft_name=args.draft_name,
            overwrite=args.overwrite,
        )
        print(render_draft_summary(summary))
        return

    stats = PipelineRunner(
        db_path=args.db_path,
        excel_path=args.excel_path,
        config_dir=args.config_dir,
        collector=create_collector(
            args.source,
            samples_root=args.samples_root,
            inbox_dir=args.inbox_dir,
        ),
        ocr_provider=create_ocr_provider(args.ocr),
        llm_provider=create_llm_provider(args.llm, load_project_config(args.config_dir)),
    ).run()
    print(
        "Job Intelligence Agent run complete: "
        f"collected={stats.collected_count}, "
        f"inserted={stats.inserted_count}, "
        f"skipped={stats.skipped_count}, "
        f"db={stats.db_path}, "
        f"excel={stats.excel_path}"
    )
    if stats.skipped_reasons:
        print(f"Skipped reasons: {stats.skipped_reasons}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job Intelligence Agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the pipeline")
    _add_common_run_args(run_parser)

    llm_status_parser = subparsers.add_parser(
        "llm-status", help="Check real LLM configuration without sending sample data"
    )
    llm_status_parser.add_argument("--config-dir", type=Path, default=Path("config"))

    inventory_parser = subparsers.add_parser(
        "inventory", help="Inventory real fixture samples"
    )
    inventory_parser.add_argument("--samples-root", default="real_samples")

    inbox_inventory_parser = subparsers.add_parser(
        "inbox-inventory", help="Inventory local HTML snapshot inbox"
    )
    inbox_inventory_parser.add_argument(
        "--inbox-dir", type=Path, default=Path("data/inbox/html")
    )
    inbox_inventory_parser.add_argument("--limit", type=int, default=20)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate gold samples")
    evaluate_parser.add_argument("--samples-root", default="real_samples")
    evaluate_parser.add_argument("--config-dir", default="config")
    evaluate_parser.add_argument("--llm", choices=["mock", "real"], default="mock")
    evaluate_parser.add_argument("--ocr", choices=["mock", "paddle"], default="mock")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one sample")
    inspect_parser.add_argument("sample_dir")
    inspect_parser.add_argument("--config-dir", default="config")
    inspect_parser.add_argument("--llm", choices=["mock", "real"], default="mock")
    inspect_parser.add_argument("--ocr", choices=["mock", "paddle"], default="mock")

    draft_parser = subparsers.add_parser(
        "draft-gold", help="Generate reviewable gold_draft.json files"
    )
    draft_parser.add_argument("--samples-root", type=Path, default=Path("real_samples"))
    draft_parser.add_argument("--sample-dir", type=Path)
    draft_parser.add_argument("--config-dir", type=Path, default=Path("config"))
    draft_parser.add_argument("--llm", choices=["mock", "real"], default="mock")
    draft_parser.add_argument("--ocr", choices=["mock", "paddle"], default="mock")
    draft_parser.add_argument("--output-name", default="gold_draft.json")
    draft_parser.add_argument("--overwrite", action="store_true")
    draft_parser.add_argument("--include-existing-gold", action="store_true")

    promote_parser = subparsers.add_parser(
        "promote-gold", help="Promote reviewed gold_draft.json files to gold.json"
    )
    promote_parser.add_argument("--samples-root", type=Path, default=Path("real_samples"))
    promote_parser.add_argument("--sample-dir", type=Path)
    promote_parser.add_argument("--draft-name", default="gold_draft.json")
    promote_parser.add_argument("--overwrite", action="store_true")

    parser.set_defaults(
        command="run",
        source="mock",
        db_path=Path("data/job_intelligence.sqlite3"),
        excel_path=Path("data/job_intelligence.xlsx"),
        config_dir=Path("config"),
        samples_root=Path("real_samples"),
        inbox_dir=Path("data/inbox/html"),
        llm="mock",
        ocr="mock",
    )
    args = parser.parse_args()
    if args.command == "run" and not hasattr(args, "source"):
        _add_default_run_values(args)
    return args


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        choices=["mock", "real", "html", "html-snapshot"],
        default="mock",
    )
    parser.add_argument("--db-path", type=Path, default=Path("data/job_intelligence.sqlite3"))
    parser.add_argument("--excel-path", type=Path, default=Path("data/job_intelligence.xlsx"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--samples-root", type=Path, default=Path("real_samples"))
    parser.add_argument("--inbox-dir", type=Path, default=Path("data/inbox/html"))
    parser.add_argument("--llm", choices=["mock", "real"], default="mock")
    parser.add_argument("--ocr", choices=["mock", "paddle"], default="mock")


def _add_default_run_values(args: argparse.Namespace) -> None:
    args.source = "mock"
    args.db_path = Path("data/job_intelligence.sqlite3")
    args.excel_path = Path("data/job_intelligence.xlsx")
    args.config_dir = Path("config")
    args.samples_root = Path("real_samples")
    args.inbox_dir = Path("data/inbox/html")
    args.llm = "mock"
    args.ocr = "mock"


if __name__ == "__main__":
    main()
