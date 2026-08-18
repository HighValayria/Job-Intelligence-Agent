# Algorithm Daily Push

This module is intentionally independent from the Job Intelligence Agent
pipeline. Stage A provides the question registry, import path, canonical keys,
alias matching, and SQLite persistence.

## Stage A Commands

Initialize the registry:

```powershell
python -m algorithm_push --db-path data/algorithm_push.sqlite3 init-db
```

Import bundled seed files:

```powershell
python -m algorithm_push --db-path data/algorithm_push.sqlite3 import-defaults
```

The bundled defaults include 100 LeetCode HOT100 questions, 101 NowCoder
TOP101 questions, 2 custom LeetCode questions, and 3 manual interview-extra
questions.

Add a custom LeetCode question without changing selector code:

```powershell
python -m algorithm_push add-question --pool leetcode_custom --title "47. 全排列 II" --url "https://leetcode.cn/problems/permutations-ii/" --tag backtracking
```

Add a manual interview question:

```powershell
python -m algorithm_push add-question --pool interview_manual --title "手撕 LRU" --url "https://leetcode.cn/problems/lru-cache/" --tag design
```

Preview a deterministic daily selection without writing history:

```powershell
python -m algorithm_push preview --date 2026-08-15 --seed 42
```

Persist the daily selection. If the same date already exists, the existing
selection is reused:

```powershell
python -m algorithm_push select --date 2026-08-15 --seed 42
```

Run a 30-day simulation in a temporary database:

```powershell
python -m algorithm_push simulate --days 30 --seed 42 --validate
```

The simulation needs enough active interview extra questions in
`interview_manual` or `interview_extracted` to satisfy the hard recency window.
It does not write simulated history back to `data/algorithm_push.sqlite3`.
With `--validate`, the command exits non-zero if source ratios, same-day
canonical dedup, the hard recency window, or daily topic constraints are broken.

Push an already persisted selection through the development console adapter:

```powershell
python -m algorithm_push push --date 2026-08-15 --adapter console
```

Run the daily flow. This creates the date's selection if needed, persists it,
then pushes the saved selection:

```powershell
python -m algorithm_push run-daily --date 2026-08-15 --seed 42 --adapter console
```

If push fails, retry `push` or `run-daily` for the same date. The module loads
the existing `daily_selections` rows and does not select another five questions.

QQ push is available through the same adapter interface. Configure credentials
with environment variables rather than committing secrets:

```powershell
$env:PUSH_ADAPTER="qq"
$env:QQ_BOT_APP_ID="..."
$env:QQ_BOT_CLIENT_SECRET="..."
$env:QQ_BOT_TARGET_TYPE="group"
$env:QQ_BOT_TARGET_ID="..."
python -m algorithm_push push --date 2026-08-15
```

If you already manage the QQ access token elsewhere, use
`QQ_BOT_ACCESS_TOKEN` instead of `QQ_BOT_APP_ID` and
`QQ_BOT_CLIENT_SECRET`.

QQ Bot preflight does not print secrets. Run it before sending to confirm the
target endpoint and auth mode:

```powershell
python -m algorithm_push qq-check
python -m algorithm_push qq-check --fetch-token
python -m algorithm_push qq-check --send-test-message --message "Algorithm push test"
```

For group sends, `QQ_BOT_TARGET_ID` must be the group openid exposed by QQ Bot
events/API, not the visible QQ group number.

Run a local QQ event webhook server for @/private-message commands:

```powershell
python -m algorithm_push --db-path data/algorithm_push.sqlite3 qq-webhook --host 127.0.0.1 --port 8787
```

Expose `http://127.0.0.1:8787/qq/events` through a public HTTPS tunnel such as
Cloudflare Tunnel, ngrok, or frp, then configure that URL in the QQ Bot callback
settings. Supported commands:

```text
帮助
今日算法
状态
加题 <pool> <url> <tag> <title>
来点趣味
```

`加题` only allows `leetcode_custom` and `interview_manual`, and requires the
sender openid to be listed in `QQ_BOT_ADMIN_OPENIDS`.

The entertainment command recognizes common variants such as `来点妙趣`,
`来点乏味`, `整点乐子`, `来点梗图`, and `来点 meme`. It fetches four image URLs
from recent first-floor posts in Baidu Tieba `meme图吧`, limited to posts within
the last five days.

The same entertainment feature is exposed as a CLI command, which is convenient
when WorkBuddy is the QQ entry point:

```powershell
python -m algorithm_push fun-memes --limit 4 --days 5
python -m algorithm_push fun-memes --limit 4 --days 5 --json
```

Recommended WorkBuddy command mapping:

```text
帮助/菜单 -> reply with the command template directly.
加题 ... -> run python -m algorithm_push --db-path data/algorithm_push.sqlite3 add-question ...
强推 -> run python -m algorithm_push --db-path data/algorithm_push.sqlite3 scheduler-once --force --adapter qq
来点趣味/来点妙趣/来点乏味/整点乐子 -> run python -m algorithm_push fun-memes --limit 4 --days 5
```

Export the registry to CSV for review:

```powershell
python -m algorithm_push export --output data/algorithm_questions.csv
```

Review pending interview questions extracted from posts:

```powershell
python -m algorithm_push review-pending
```

Resolve a pending question after manually confirming its canonical problem and
URL:

```powershell
python -m algorithm_push resolve-pending --question-id ... --canonical-key leetcode:146 --title "146. LRU 缓存" --url "https://leetcode.cn/problems/lru-cache/" --tag design --aliases "手撕 LRU" LRU
```

After resolution the question becomes `active`, `enabled`, and eligible for the
interview extra slot unless its canonical key is also present in HOT100/HOT101.

Validate registry health before running a long simulation or enabling push:

```powershell
python -m algorithm_push validate-registry --strict
```

The health report checks pool/status/tag counts, invalid `primary_tag` values,
active questions without URLs, and duplicate canonical keys across rows.

Check whether the registry has enough eligible questions for scheduled daily
push:

```powershell
python -m algorithm_push readiness --days 30 --strict
```

This is the go-live gate. It combines registry health with source-pool capacity:
LeetCode needs at least 6 active eligible questions, NowCoder needs at least 6,
and the interview extra pool needs at least 3 when the hard recency window is 2
days. HOT duplicates in the interview pool are excluded from the capacity count.

Run the algorithm module smoke suite without requiring `pytest`:

```powershell
python scripts/run_algorithm_smoke.py
```

The smoke runner discovers `tests/test_algorithm_*.py`, supports the current
`tmp_path` test fixture usage, imports bundled seed data into a temporary
database, and runs `validate-registry --strict`.

Check daily operational status:

```powershell
python -m algorithm_push status --date 2026-08-16
```

This reports readiness, whether the date already has a saved selection, whether
the selection has been pushed, and recent push history.

Run the scheduler decision once. By default this follows `push.enabled`,
`push.time`, and `push.timezone` in `algorithm_push/config/algorithm_push.yaml`,
with optional environment overrides `PUSH_ENABLED`, `PUSH_TIME`, `TIMEZONE`, and
`PUSH_ADAPTER`.

```powershell
python -m algorithm_push scheduler-once --now 2026-08-15T09:00:00+08:00 --seed 42
```

For local smoke testing, bypass `PUSH_ENABLED` and the due-time check:

```powershell
python -m algorithm_push scheduler-once --now 2026-08-15T08:30:00+08:00 --seed 42 --force
```

For Windows scheduled execution, first run the same wrapper that the scheduled
task will call:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_algorithm_scheduler_once.ps1 -Adapter console -Force -Seed 42
```

Then register a daily Windows Task Scheduler task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_algorithm_push_scheduler.ps1 -Time 09:00 -Adapter qq -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_algorithm_push_scheduler.ps1 -Time 09:00 -Adapter qq
```

The wrapper imports bundled defaults idempotently, runs
`readiness --days 30 --strict`, then calls `scheduler-once`. Logs are appended
to `data/logs/algorithm_push_scheduler.log`. To remove the task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_algorithm_push_scheduler.ps1
```

## Database

Default database path:

```text
data/algorithm_push.sqlite3
```

SQLite is the source of truth. Excel or CSV exports can be added later as views
over the registry.

Core tables:

- `questions`
- `question_aliases`
- `question_mentions`
- `daily_selections`
- `push_history`

Only questions with `status = active`, `enabled = 1`, and a non-empty `url`
should enter the future daily selector.

For v0.1, recency is based on `daily_selections`, not successful push records.
The push stage can later switch the source to `push_history` once QQ retry
behavior is implemented.

## Integration Boundary

The future Job Search Agent integration should call:

```python
AlgorithmQuestionRepository.upsert_interview_question(...)
```

That API records interview mentions and lets the algorithm module handle
canonical matching, alias matching, and HOT100/HOT101 exclusion.

Stage C adds an optional Job Search Agent bridge:

```powershell
python main.py run --source mock --llm mock --ocr mock --ingest-algorithm-questions --algorithm-db-path data/algorithm_push.sqlite3
```

When enabled, the runner imports default HOT/custom seed questions first, then
converts `Interview.rounds[*].coding_questions` and
`Interview.rounds[*].algorithm_questions` into algorithm candidates. Existing
HOT100/HOT101 aliases are linked as mentions instead of being duplicated into
the interview extra pool. Questions without URLs are saved as pending and are
not eligible for daily selection.
