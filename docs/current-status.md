# Current Status

日期：2026-08-15

## 测试状态

使用项目 `.venv`：

```powershell
.venv\Scripts\python.exe -m pytest --basetemp data\pytest-tmp -o cache_dir=data\pytest-cache
```

结果：`24 passed`。

## 真实样本盘点

当前 `real_samples/`：

- 总数：32
- `interview`: 15
- `recruitment`: 13
- `information_gap`（原 `infodiff`）: 4
- `offer`: 0
- 小红书：22
- 牛客：5
- 未填平台或空样本：5
- 含图片：15
- 纯文本：17
- 已有 `gold.json`: 12
- 空或不完整样本：5

Offer 真实样本为 0 是当前阶段允许状态；Mock Offer 和 Offer Schema 仍保留。

## 已完成

- `work_condition` 兼容迁移到 `information_gap`
- `InformationGap` Schema
- per-image OCR result
- 结构化 `UnifiedContent.segments`
- `RealSampleLoader`
- optional partial gold evaluation
- AI 初标 `gold_draft.json` 与人工确认 `gold.json` 分离
- inspect CLI
- inventory CLI
- RealLLMProvider 配置化骨架
- PaddleOCRProvider 可选骨架
- Excel “信息差” Sheet
- `docs/architecture.md`
- `docs/current-status.md`

## 未完成 / 下一步

- 真实 LLM prompt 需要继续用 gold 样本迭代。
- 当前真实样本已有 12 个审核通过的 gold，可用于初步回归；样本量仍需继续扩充。
- 可以继续运行 `draft-gold` 生成 `gold_draft.json`，审核后再 `promote-gold`。
- Moonshot/Kimi K3 `.env` 配置已接入；`llm-status` 可本地检查配置是否加载，不会发送样本内容。
- 真实 LLM 回归已跑通：Kimi K3 可完成分类和抽取，已补 schema 输出修复、metadata/source_url 输入、评估文本归一化和 `data/llm-cache/` 响应缓存。
- 当前 12 个 gold 样本在 mock OCR 下的真实 LLM 字段级评估基线为 `149 passed / 124 failed`。
- 用户已授权将真实样本文本和图片 OCR 派生文本发送给 Moonshot 做 inspect/evaluate。
- 当前 12 个 gold 样本在 PaddleOCR + Moonshot 下的字段级评估为 `204 passed / 69 failed`；国家电网图片样本已通过关键招聘字段，包括公司、岗位类型、届别、第一批网申时间、截止时间和 source_url。
- 评估器已支持同级列表匹配、文本包含匹配和高阈值近似文本匹配；剩余失败主要集中在信息差摘要粒度、面经系统设计题缺失、部分 interviewer_focus 缺失，以及少量公司类型/要求字段粒度。
- PaddleOCRProvider 已在项目 `.venv` 中用 PaddleOCR 3.7.0 跑通单图 inspect。
- 第一次运行 PaddleOCR 会下载官方模型到 `C:\Users\33967\.paddlex\official_models\`。
- 真实小红书/牛客自动采集仍属于后续阶段，不在本阶段实现。
