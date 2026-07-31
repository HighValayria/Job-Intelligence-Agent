from __future__ import annotations

from scheduler.runner import PipelineRunner


def main() -> None:
    stats = PipelineRunner().run()
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


if __name__ == "__main__":
    main()

