# Architecture

Job Intelligence Agent 保持确定性 pipeline，不引入多 Agent 框架。

```text
Collector
-> RawPost
-> ContentBuilder
-> OCRProvider
-> UnifiedContent
-> LLMProvider.classify
-> LLMProvider.extract
-> LLMProvider.normalize
-> Pydantic validation
-> Dedup
-> Repository / SQLite
-> ExcelExporter
```

## Provider 边界

- `Collector`: 平台或 fixture 到 `RawPost`。
- `OCRProvider`: 单图到 `OCRResult`，保留 status、confidence、error、raw_result。
- `LLMProvider`: 只接收 `UnifiedContent`，输出分类或类型 Schema。
- `Repository`: 唯一数据库写入入口。
- `ExcelExporter`: 只从 SQLite 全量导出。

## 类型体系

主类型：

- `recruitment`
- `interview`
- `offer`
- `information_gap`
- `progress`
- `other`

`work_condition` 是第一阶段旧命名，现在兼容归一为 `information_gap`。

## 真实样本

`RealSampleLoader` 读取 `real_samples/<type>/<id>/metadata.json`，并自动收集同目录图片。`infodiff` 目录名兼容映射为 `information_gap`。

Gold 标注可选，只对 `gold.json` 中实际出现的字段做 partial evaluation。

AI 初标写入 `gold_draft.json`，它不是正式评测基准。人工审核后通过 `promote-gold` 提升为 `gold.json`，提升时会自动去掉 `_draft` 元信息。

## 数据库兼容

第二阶段新增：

- `information_gaps`
- `schema_version`
- `pipeline_errors`
- `posts.ocr_results_json`

并保留 `work_conditions` 兼容视图或历史表，避免旧库直接断裂。

## CLI

- `python main.py`: 默认 Mock pipeline。
- `python main.py run --source real --llm mock --ocr mock`
- `python main.py inventory`
- `python main.py evaluate`
- `python main.py inspect <sample_dir>`
- `python main.py draft-gold`
- `python main.py promote-gold`
