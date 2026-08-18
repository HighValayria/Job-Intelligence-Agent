from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from env_loader import load_env_file

from algorithm_push.entertainment import fetch_recent_meme_images
from algorithm_push.ingestion import import_default_questions, import_questions_file
from algorithm_push.models import (
    DailySelection,
    Platform,
    Question,
    QuestionInput,
    QuestionPool,
    QuestionStatus,
)
from algorithm_push.push import (
    ConsoleAdapter,
    PushAdapter,
    PushService,
    QQBotAdapter,
    QQBotCheckResult,
    load_qq_bot_config,
)
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector import DailySelector
from algorithm_push.selector.config_loader import load_selection_config
from algorithm_push.selector.simulation import audit_simulation, render_simulation_audit
from algorithm_push.scheduler import DailyScheduler, load_scheduler_config
from algorithm_push.validation import (
    check_readiness,
    render_readiness,
    render_registry_health,
    validate_registry,
)
from algorithm_push.webhook.server import run_qq_webhook_server


DEFAULT_DB_PATH = Path("data/algorithm_push.sqlite3")
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config" / "algorithm_push.yaml"


def main(argv: list[str] | None = None) -> None:
    _configure_utf8_stdio()
    load_env_file(".env")
    args = _parse_args(argv)
    with AlgorithmQuestionRepository(args.db_path) as repository:
        repository.initialize()
        if args.command == "init-db":
            print(f"initialized algorithm registry: {args.db_path}")
            return
        if args.command == "import-defaults":
            total = import_default_questions(repository)
            print(f"imported default algorithm questions: {total}")
            return
        if args.command == "import-file":
            imported = import_questions_file(
                repository,
                args.path,
                default_pool=args.pool,
            )
            print(f"imported questions: {len(imported)}")
            return
        if args.command == "add-question":
            question = repository.upsert_question(
                QuestionInput(
                    canonical_key=args.canonical_key,
                    title=args.title,
                    url=args.url,
                    pool=args.pool,
                    platform=args.platform,
                    primary_tag=args.tag,
                    tags=args.tags or [],
                    aliases=args.aliases or [],
                    priority=args.priority,
                    enabled=not args.disabled,
                )
            )
            print(f"saved question: {question.question_id} {question.canonical_key}")
            return
        if args.command == "list":
            for question in repository.list_questions(
                pool=args.pool,
                status=args.status,
                active_only=args.active_only,
            ):
                print(
                    "\t".join(
                        [
                            question.question_id,
                            question.pool.value,
                            question.canonical_key,
                            question.primary_tag,
                            question.title,
                            question.url or "",
                        ]
                    )
                )
            return
        if args.command == "export":
            questions = repository.list_questions(
                pool=args.pool,
                status=args.status,
                active_only=args.active_only,
            )
            _export_questions_csv(questions, args.output)
            print(f"exported questions: {len(questions)} -> {args.output}")
            return
        if args.command == "review-pending":
            rows = repository.review_rows(status=args.status)
            print(_render_review_rows(rows))
            return
        if args.command == "resolve-pending":
            question = repository.resolve_pending_question(
                question_id=args.question_id,
                url=args.url,
                canonical_key=args.canonical_key,
                title=args.title,
                primary_tag=args.tag,
                tags=args.tags,
                aliases=args.aliases,
                priority=args.priority,
            )
            print(f"resolved question: {question.question_id} {question.canonical_key}")
            return
        if args.command == "validate-registry":
            report = validate_registry(repository, taxonomy_path=args.taxonomy)
            print(render_registry_health(report))
            if args.strict and report.error_count:
                raise SystemExit(1)
            return
        if args.command == "readiness":
            report = check_readiness(
                repository,
                config=load_selection_config(args.config),
                days=args.days,
                taxonomy_path=args.taxonomy,
            )
            print(render_readiness(report))
            if args.strict and not report.ok:
                raise SystemExit(1)
            return
        if args.command == "status":
            print(_render_status(repository, args))
            return
        if args.command == "qq-check":
            config = load_qq_bot_config(args.config)
            adapter: QQBotAdapter | None = None
            try:
                adapter = QQBotAdapter(config)
                report = adapter.check(fetch_token=args.fetch_token or args.send_test_message)
            except Exception as exc:
                report = QQBotCheckResult(
                    ok=False,
                    auth_mode=_qq_auth_mode(config),
                    endpoint=None,
                    token_checked=False,
                    warnings=[],
                    error=str(exc),
                )
            print(_render_qq_check(report))
            if not report.ok:
                raise SystemExit(1)
            if args.send_test_message:
                if adapter is None:
                    raise SystemExit(1)
                result = adapter.send_daily_questions(args.message)
                print(f"send_status={result.status.value}")
                if result.error:
                    print(f"error={result.error}")
                    raise SystemExit(1)
            return
        if args.command == "qq-webhook":
            run_qq_webhook_server(
                host=args.host,
                port=args.port,
                db_path=args.db_path,
                config_path=args.config,
            )
            return
        if args.command == "fun-memes":
            memes = fetch_recent_meme_images(
                limit=args.limit,
                days=args.days,
                forum=args.forum,
                shuffle=not args.no_shuffle,
            )
            if args.json:
                print(
                    json.dumps(
                        [
                            {
                                "image_url": meme.image_url,
                                "thread_url": meme.thread_url,
                                "title": meme.title,
                                "post_date": meme.post_date.isoformat()
                                if meme.post_date
                                else None,
                            }
                            for meme in memes
                        ],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(_render_memes(memes))
            if len(memes) < args.limit:
                raise SystemExit(1)
            return
        if args.command == "preview":
            selection = _selector(repository, args).select(
                args.date,
                seed=args.seed,
                reuse_existing=False,
                persist=False,
            )
            print(_render_selection(selection))
            return
        if args.command == "select":
            selection = _selector(repository, args).select(
                args.date,
                seed=args.seed,
                reuse_existing=True,
                persist=True,
            )
            print(_render_selection(selection))
            return
        if args.command == "simulate":
            selections = _simulate(
                repository,
                start_date=args.start_date,
                days=args.days,
                seed=args.seed,
                config_path=args.config,
            )
            print(_render_simulation(selections))
            if args.validate:
                report = audit_simulation(
                    selections,
                    config=load_selection_config(args.config),
                )
                print("")
                print(render_simulation_audit(report))
                if not report.ok:
                    raise SystemExit(1)
            return
        if args.command == "push":
            result = PushService(repository, _push_adapter(args)).push_existing_selection(
                args.date
            )
            print(f"push_status={result.status.value}")
            if result.error:
                print(f"error={result.error}")
            return
        if args.command == "run-daily":
            selection = _selector(repository, args).select(
                args.date,
                seed=args.seed,
                reuse_existing=True,
                persist=True,
            )
            result = PushService(repository, _push_adapter(args)).push_existing_selection(
                selection.selection_date
            )
            print(f"push_status={result.status.value}")
            if result.error:
                print(f"error={result.error}")
            return
        if args.command == "scheduler-once":
            scheduler = DailyScheduler(
                repository,
                selection_config=load_selection_config(args.config),
                scheduler_config=load_scheduler_config(args.config),
                adapter=_push_adapter(args),
            )
            result = scheduler.run_once(
                now=args.now,
                seed=args.seed,
                force=args.force,
            )
            print(
                "scheduler_status="
                f"{result.status.value} date={result.selection_date} message={result.message}"
            )
            if result.push_status:
                print(f"push_status={result.push_status}")
            return


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Algorithm Daily Push registry tools")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the algorithm registry database")
    subparsers.add_parser("import-defaults", help="Import bundled seed question files")

    import_parser = subparsers.add_parser("import-file", help="Import a YAML question file")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--pool", choices=[pool.value for pool in QuestionPool])

    add_parser = subparsers.add_parser("add-question", help="Add or update one question")
    add_parser.add_argument("--canonical-key")
    add_parser.add_argument("--pool", required=True, choices=[pool.value for pool in QuestionPool])
    add_parser.add_argument("--platform", choices=[platform.value for platform in Platform])
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--url")
    add_parser.add_argument("--tag", required=True)
    add_parser.add_argument("--tags", nargs="*", default=[])
    add_parser.add_argument("--aliases", nargs="*", default=[])
    add_parser.add_argument("--priority", type=float, default=1.0)
    add_parser.add_argument("--disabled", action="store_true")

    list_parser = subparsers.add_parser("list", help="List questions")
    list_parser.add_argument("--pool", choices=[pool.value for pool in QuestionPool])
    list_parser.add_argument("--status", choices=[status.value for status in QuestionStatus])
    list_parser.add_argument("--active-only", action="store_true")

    export_parser = subparsers.add_parser("export", help="Export questions to CSV")
    export_parser.add_argument("--output", type=Path, default=Path("data/algorithm_questions.csv"))
    export_parser.add_argument("--pool", choices=[pool.value for pool in QuestionPool])
    export_parser.add_argument("--status", choices=[status.value for status in QuestionStatus])
    export_parser.add_argument("--active-only", action="store_true")

    review_parser = subparsers.add_parser(
        "review-pending", help="List questions waiting for manual review"
    )
    review_parser.add_argument(
        "--status",
        choices=[QuestionStatus.PENDING.value, QuestionStatus.MANUAL_REVIEW.value],
        default=QuestionStatus.PENDING.value,
    )

    resolve_parser = subparsers.add_parser(
        "resolve-pending", help="Resolve a pending question with a usable URL"
    )
    resolve_parser.add_argument("--question-id", required=True)
    resolve_parser.add_argument("--url", required=True)
    resolve_parser.add_argument("--canonical-key")
    resolve_parser.add_argument("--title")
    resolve_parser.add_argument("--tag")
    resolve_parser.add_argument("--tags", nargs="*")
    resolve_parser.add_argument("--aliases", nargs="*")
    resolve_parser.add_argument("--priority", type=float)

    validate_parser = subparsers.add_parser(
        "validate-registry", help="Validate registry health before selection/push"
    )
    validate_parser.add_argument(
        "--taxonomy",
        type=Path,
        default=PACKAGE_ROOT / "config" / "tag_taxonomy.yaml",
    )
    validate_parser.add_argument("--strict", action="store_true")

    readiness_parser = subparsers.add_parser(
        "readiness", help="Check whether the registry is ready for scheduled push"
    )
    readiness_parser.add_argument("--days", type=int, default=30)
    readiness_parser.add_argument(
        "--taxonomy",
        type=Path,
        default=PACKAGE_ROOT / "config" / "tag_taxonomy.yaml",
    )
    readiness_parser.add_argument("--strict", action="store_true")

    status_parser = subparsers.add_parser(
        "status", help="Show readiness, daily selection, and recent push status"
    )
    status_parser.add_argument("--date", type=_parse_date, default=date.today())
    status_parser.add_argument("--recent", type=int, default=7)
    status_parser.add_argument(
        "--taxonomy",
        type=Path,
        default=PACKAGE_ROOT / "config" / "tag_taxonomy.yaml",
    )

    qq_check_parser = subparsers.add_parser(
        "qq-check", help="Validate QQ Bot configuration and optionally send a test message"
    )
    qq_check_parser.add_argument(
        "--fetch-token",
        action="store_true",
        help="Fetch or validate the access token without sending a message",
    )
    qq_check_parser.add_argument(
        "--send-test-message",
        action="store_true",
        help="Send a short QQ Bot test message after configuration checks pass",
    )
    qq_check_parser.add_argument(
        "--message",
        default="Algorithm Daily Push QQ Bot test",
    )

    qq_webhook_parser = subparsers.add_parser(
        "qq-webhook", help="Run a local QQ Bot event webhook server"
    )
    qq_webhook_parser.add_argument("--host", default="127.0.0.1")
    qq_webhook_parser.add_argument("--port", type=int, default=8787)

    fun_parser = subparsers.add_parser(
        "fun-memes", help="Fetch recent meme images from Baidu Tieba"
    )
    fun_parser.add_argument("--limit", type=int, default=4)
    fun_parser.add_argument("--days", type=int, default=5)
    fun_parser.add_argument("--forum", default="meme图")
    fun_parser.add_argument("--json", action="store_true")
    fun_parser.add_argument("--no-shuffle", action="store_true")

    preview_parser = subparsers.add_parser("preview", help="Preview one daily selection")
    preview_parser.add_argument("--date", type=_parse_date, default=date.today())
    preview_parser.add_argument("--seed", type=int)

    select_parser = subparsers.add_parser("select", help="Create or reuse one daily selection")
    select_parser.add_argument("--date", type=_parse_date, default=date.today())
    select_parser.add_argument("--seed", type=int)

    simulate_parser = subparsers.add_parser(
        "simulate", help="Simulate consecutive daily selections without writing history"
    )
    simulate_parser.add_argument("--start-date", type=_parse_date, default=date.today())
    simulate_parser.add_argument("--days", type=int, default=30)
    simulate_parser.add_argument("--seed", type=int)
    simulate_parser.add_argument(
        "--validate",
        action="store_true",
        help="Fail if simulated selections violate source, dedup, recency, or topic rules",
    )

    push_parser = subparsers.add_parser("push", help="Push an existing daily selection")
    push_parser.add_argument("--date", type=_parse_date, default=date.today())
    push_parser.add_argument("--adapter", choices=["console", "qq"])

    run_daily_parser = subparsers.add_parser(
        "run-daily", help="Create today's selection if needed, then push it"
    )
    run_daily_parser.add_argument("--date", type=_parse_date, default=date.today())
    run_daily_parser.add_argument("--seed", type=int)
    run_daily_parser.add_argument("--adapter", choices=["console", "qq"])

    scheduler_parser = subparsers.add_parser(
        "scheduler-once",
        help="Run the configured daily scheduler once if enabled and due",
    )
    scheduler_parser.add_argument("--now", type=_parse_datetime)
    scheduler_parser.add_argument("--seed", type=int)
    scheduler_parser.add_argument("--force", action="store_true")
    scheduler_parser.add_argument("--adapter", choices=["console", "qq"])

    args = parser.parse_args(argv)
    if hasattr(args, "pool") and isinstance(args.pool, str):
        args.pool = QuestionPool(args.pool)
    if hasattr(args, "platform") and isinstance(args.platform, str):
        args.platform = Platform(args.platform)
    if hasattr(args, "status") and isinstance(args.status, str):
        args.status = QuestionStatus(args.status)
    return args


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _selector(repository: AlgorithmQuestionRepository, args: argparse.Namespace) -> DailySelector:
    return DailySelector(repository, config=load_selection_config(args.config))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _render_selection(selection: DailySelection) -> str:
    lines = [f"Algorithm selection for {selection.selection_date.isoformat()}"]
    for index, item in enumerate(selection.items, start=1):
        question = item.question
        lines.append(
            f"{index}. [{item.slot}] {question.title} "
            f"({question.primary_tag}, score={item.selected_score:.4f})"
        )
        lines.append(question.url or "")
    return "\n".join(lines)


def _export_questions_csv(questions: list[Question], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "question_id",
        "canonical_key",
        "title",
        "url",
        "pool",
        "platform",
        "primary_tag",
        "tags",
        "status",
        "enabled",
        "priority",
        "created_at",
        "updated_at",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for question in questions:
            writer.writerow(
                {
                    "question_id": question.question_id,
                    "canonical_key": question.canonical_key,
                    "title": question.title,
                    "url": question.url or "",
                    "pool": question.pool.value,
                    "platform": question.platform.value,
                    "primary_tag": question.primary_tag,
                    "tags": ";".join(question.tags),
                    "status": question.status.value,
                    "enabled": int(question.enabled),
                    "priority": question.priority,
                    "created_at": question.created_at.isoformat(),
                    "updated_at": question.updated_at.isoformat(),
                }
            )


def _render_review_rows(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "no questions waiting for review"
    lines = [
        "\t".join(
            [
                "question_id",
                "pool",
                "status",
                "primary_tag",
                "title",
                "mention_count",
                "latest_source_post_url",
                "latest_context",
            ]
        )
    ]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    str(row.get("question_id") or ""),
                    str(row.get("pool") or ""),
                    str(row.get("status") or ""),
                    str(row.get("primary_tag") or ""),
                    str(row.get("title") or ""),
                    str(row.get("mention_count") or 0),
                    str(row.get("latest_source_post_url") or ""),
                    str(row.get("latest_context") or ""),
                ]
            )
        )
    return "\n".join(lines)


def _render_qq_check(report: QQBotCheckResult) -> str:
    lines = [
        "QQ Bot check",
        f"status: {'ok' if report.ok else 'failed'}",
        f"auth_mode: {report.auth_mode}",
        f"endpoint: {report.endpoint or '-'}",
        f"token_checked: {str(report.token_checked).lower()}",
    ]
    if report.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.error:
        lines.append("")
        lines.append(f"error: {report.error}")
    return "\n".join(lines)


def _render_memes(memes) -> str:
    if not memes:
        return "没有抓到 5 天内的楼主 meme 图。"
    lines = ["来点趣味"]
    for index, meme in enumerate(memes, start=1):
        date_text = meme.post_date.isoformat() if meme.post_date else "unknown-date"
        lines.extend(
            [
                f"{index}. {meme.title} ({date_text})",
                meme.image_url,
                f"source: {meme.thread_url}",
            ]
        )
    return "\n".join(lines)


def _render_status(
    repository: AlgorithmQuestionRepository,
    args: argparse.Namespace,
) -> str:
    readiness = check_readiness(
        repository,
        config=load_selection_config(args.config),
        days=30,
        taxonomy_path=args.taxonomy,
    )
    selection = repository.get_daily_selection(args.date)
    push_status = repository.latest_push_status(args.date)
    push_error = repository.latest_push_error(args.date)
    recent = repository.recent_push_statuses(limit=args.recent)

    lines = [
        "Algorithm push status",
        f"date: {args.date.isoformat()}",
        f"readiness: {'ready' if readiness.ok else 'not_ready'} "
        f"(errors={readiness.error_count}, warnings={readiness.warning_count})",
        f"selection: {'created' if selection is not None else 'missing'}",
        f"push: {push_status or 'not_sent'}",
    ]
    if push_error:
        lines.append(f"push_error: {push_error}")

    lines.append("")
    lines.append("Today selection")
    if selection is None:
        lines.append("  none")
    else:
        for index, item in enumerate(selection.items, start=1):
            question = item.question
            lines.append(
                f"  {index}. [{item.slot}] {question.title} ({question.primary_tag})"
            )

    lines.append("")
    lines.append("Recent pushes")
    if not recent:
        lines.append("  none")
    else:
        for row in recent:
            error = row.get("error")
            suffix = f" error={error}" if error else ""
            lines.append(
                "  "
                f"{row['selection_date']} attempt={row['attempt']} "
                f"status={row['push_status']} questions={row['question_count']}"
                f"{suffix}"
            )
    return "\n".join(lines)


def _qq_auth_mode(config) -> str:
    if config.access_token:
        return "access_token"
    if config.app_id and config.client_secret:
        return "app_credentials"
    return "missing"


def _simulate(
    repository: AlgorithmQuestionRepository,
    *,
    start_date: date,
    days: int,
    seed: int | None,
    config_path: Path,
) -> list[DailySelection]:
    if days <= 0:
        raise ValueError("--days must be positive")

    with tempfile.TemporaryDirectory() as tmp_dir:
        with AlgorithmQuestionRepository(Path(tmp_dir) / "simulation.sqlite3") as sim_repo:
            sim_repo.initialize()
            for question in repository.list_questions():
                sim_repo.upsert_question(
                    QuestionInput(
                        canonical_key=question.canonical_key,
                        title=question.title,
                        url=question.url,
                        pool=question.pool,
                        platform=question.platform,
                        primary_tag=question.primary_tag,
                        tags=question.tags,
                        enabled=question.enabled,
                        priority=question.priority,
                        status=question.status,
                    )
                )
            selector = DailySelector(sim_repo, config=load_selection_config(config_path))
            selections: list[DailySelection] = []
            for offset in range(days):
                selection_seed = None if seed is None else seed + offset
                selection = selector.select(
                    start_date + timedelta(days=offset),
                    seed=selection_seed,
                    reuse_existing=False,
                    persist=True,
                )
                selections.append(selection)
            return selections


def _render_simulation(selections: list[DailySelection]) -> str:
    topic_counts: Counter[str] = Counter()
    lines: list[str] = []
    for selection in selections:
        lines.append(_render_selection(selection))
        lines.append("")
        topic_counts.update(question.primary_tag for question in selection.questions)
    lines.append("Primary tag distribution")
    for tag, count in sorted(topic_counts.items()):
        lines.append(f"{tag}: {count}")
    return "\n".join(lines).rstrip()


def _push_adapter(args: argparse.Namespace) -> PushAdapter:
    configured = load_scheduler_config(args.config).adapter
    adapter = args.adapter or configured
    if adapter == "console":
        return ConsoleAdapter()
    if adapter == "qq":
        return QQBotAdapter(load_qq_bot_config(args.config))
    raise ValueError(f"unsupported push adapter: {adapter}")
