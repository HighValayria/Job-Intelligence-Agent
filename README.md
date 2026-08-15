# Job Intelligence Agent

求职情报采集与整理系统。当前版本保留第一阶段完全离线 Mock 闭环，并开始支持第二阶段真实 fixture：招聘信息、面经、Offer、信息差帖，清洗文本，合并 OCR，分类与结构化抽取，去重，写入 SQLite，并从 SQLite 全量导出 Excel。

当前版本不包含真实小红书/牛客自动搜索、浏览器自动化、登录、Cookie、验证码、Embedding 去重、Web 前端或通知功能。真实 LLM 和 PaddleOCR 已有 Provider 接口/骨架，但默认测试不会调用它们。

## 架构

```text
Scheduler / Runner
-> Query 配置
-> Collector
-> RawPost
-> 文本清洗
-> 图片 OCR
-> UnifiedContent
-> LLM 分类
-> 类型对应的结构化抽取
-> Normalization
-> Validation
-> Deduplication
-> SQLite
-> Excel Export
```

核心边界：

- Collector 只负责把平台数据转换成 `RawPost`。
- OCR Provider 只负责图片到文本。
- LLM Provider 只接收 `UnifiedContent`，只输出 Pydantic Schema 数据。
- Repository 是唯一 SQLite 写入入口。
- Excel 只从 SQLite 全量导出，不参与去重或状态判断。

## 目录职责

- `config/`: 查询、平台、公司别名、岗位 taxonomy 配置。
- `collectors/`: 采集接口与 MockCollector。
- `models/`: RawPost、UnifiedContent、分类结果和四类业务 Schema。
- `processing/`: 文本清洗、OCR 抽象、UnifiedContent 构建。
- `llm/`: LLMProvider 抽象、MockLLMProvider、分类/抽取/标准化调用薄层。
- `validation/`: Pydantic Schema 校验与置信度辅助。
- `dedup/`: post_id 去重与内容 fingerprint 去重。
- `storage/`: SQLite schema 与 Repository。
- `exporters/`: Excel 导出。
- `scheduler/`: PipelineRunner。
- `evaluation/`: partial gold 自动评估。
- `inspection/`: 单篇样本 inspect 输出。
- `prompts/`: 类型专用 LLM prompt。
- `tests/`: pytest 测试与 Mock 帖子 fixture。
- `data/`: 默认输出目录，生成 SQLite 和 Excel。

## 如何运行

安装依赖：

```bash
pip install -e ".[dev]"
```

执行 Mock 全链路：

```bash
python main.py
```

等价于：

```bash
python main.py run --source mock --llm mock --ocr mock
```

盘点真实样本：

```bash
python main.py inventory --samples-root real_samples
```

运行真实 fixture + Mock Provider smoke：

```bash
python main.py run --source real --llm mock --ocr mock --db-path data/real.sqlite3 --excel-path data/real.xlsx
```

Inspect 单篇样本：

```bash
python main.py inspect real_samples/interview/012 --llm mock --ocr mock
```

Evaluation：

```bash
python main.py evaluate --samples-root real_samples --llm mock --ocr mock
```

AI 初标、人工审核：

```bash
python main.py draft-gold --samples-root real_samples --llm real --ocr paddle
```

这会生成 `gold_draft.json`，不会直接生成正式 `gold.json`。你审核并修改 draft 后，再执行：

```bash
python main.py promote-gold --samples-root real_samples
```

真实 LLM 使用环境变量，不要把 Secret 写入代码：

```powershell
$env:JOB_INTEL_LLM_API_URL="https://example.com/v1/chat/completions"
$env:JOB_INTEL_LLM_API_KEY="..."
$env:JOB_INTEL_LLM_MODEL="..."
python main.py run --source real --llm real --ocr mock
```

默认生成：

- `data/job_intelligence.sqlite3`
- `data/job_intelligence.xlsx`

再次运行会读取同一批 Mock 帖子，但相同 `platform + post_id` 不会重复插入。

运行测试：

```bash
python -m pytest
```

如果本机没有把 Python 加入 PATH，可以直接使用当前机器的 Python：

```powershell
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe main.py
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe -m pytest --basetemp data\pytest-tmp -o cache_dir=data\pytest-cache
```

## 数据库设计

SQLite 是主数据源，当前 schema 至少包含：

- `posts`: 所有帖子的基础索引，保存原始正文、OCR、URL、发布时间、抓取时间、分类结果、抽取结果、confidence、needs_review 和内容 fingerprint。
- `recruitments`: 招聘信息结构化结果。
- `interviews`: 面经主表。
- `interview_rounds`: 面试轮次明细。
- `offers`: Offer 和薪酬福利结构化结果。
- `information_gaps`: 信息差结构化结果。
- `work_conditions`: 兼容旧命名的读取视图或历史表。
- `companies`: 公司标准名、类型、别名。
- `crawl_runs`: 每次 pipeline 运行记录。

一级去重使用 `platform + post_id`。二级去重使用规范化 `full_content` 后的 SHA256 fingerprint。

## 增加新的 Collector

1. 在 `collectors/` 新增类并继承 `collectors.base.Collector`。
2. 实现 `collect(self, queries) -> list[RawPost]`。
3. 平台原始字段必须在 Collector 内转换成统一 `RawPost`。
4. 在 `config/platforms.yaml` 中登记平台和 Collector 路径。

Collector 不应该调用 LLM、SQLite 或 Excel。

## 增加新的 OCR Provider

1. 在 `processing/ocr.py` 或新文件中继承 `OCRProvider`。
2. 实现 `extract(image) -> OCRResult`。
3. 在 runner 初始化时注入新的 provider：

```python
PipelineRunner(ocr_provider=YourOCRProvider()).run()
```

OCR Provider 只返回 OCR 文本和置信度，不参与分类、抽取或入库。

## 增加新的 LLM Provider

1. 继承 `llm.base.LLMProvider`。
2. 实现：
   - `classify(content)`
   - `extract(content, post_type)`
   - `normalize(result)`
3. 输出必须通过 `validation/schema_validator.py` 的 Pydantic Schema 校验。
4. 在 runner 初始化时注入：

```python
PipelineRunner(llm_provider=YourLLMProvider()).run()
```

LLM Provider 不应直接操作网页、SQLite 或 Excel。

## Mock 数据

`tests/fixtures/mock_posts.json` 包含 4 篇 Mock 帖子：

- 招聘信息
- 面经
- Offer
- 信息差/工作体验

其中面经样例正文很少，核心内容来自 `MockOCRProvider` 的图片 OCR 文本，用于验证 `UnifiedContent -> 分类 -> 抽取 -> SQLite -> Excel` 全链路。

## 真实样本与 Gold

真实样本默认读取 `real_samples/`，每篇样本支持：

- `metadata.json`: 必需，包含 platform、url、title、text、expected_type 等。
- `image_*.jpg/png/webp`: 可选，按文件名顺序 OCR。
- `gold.json`: 可选，只评估其中已人工确认的字段。
- `gold_draft.json`: AI 初标草稿，不会被 evaluation 当作正式标准答案。

目录名 `infodiff` 会兼容映射为 `information_gap`。当前真实样本中 Offer 数量允许为 0，evaluation 会跳过而不是报错。

推荐流程是：先由系统生成 `gold_draft.json`，人工只审核需要关心的核心字段；确认后用 `promote-gold` 生成 `gold.json`。这样可以避免未经确认的模型输出污染评测基准。
