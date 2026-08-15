from __future__ import annotations

from pathlib import Path

from scheduler.runner import PipelineRunner
from storage.repository import Repository


def test_full_pipeline_and_rerun_dedup(tmp_path: Path) -> None:
    db_path = tmp_path / "job.sqlite3"
    excel_path = tmp_path / "job_intelligence.xlsx"
    runner = PipelineRunner(db_path=db_path, excel_path=excel_path)

    first = runner.run()
    second = runner.run()

    assert first.collected_count == 4
    assert first.inserted_count == 4
    assert first.skipped_count == 0
    assert second.inserted_count == 0
    assert second.skipped_reasons == {"duplicate_post_id": 4}
    assert excel_path.exists()

    with Repository(db_path) as repository:
        assert repository.count_rows("posts") == 4
        assert repository.count_rows("recruitments") == 1
        assert repository.count_rows("interviews") == 1
        assert repository.count_rows("interview_rounds") == 2
        assert repository.count_rows("offers") == 1
        assert repository.count_rows("information_gaps") == 1
        assert repository.count_rows("work_conditions") == 1
