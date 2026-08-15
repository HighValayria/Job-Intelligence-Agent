# Current Status

日期：2026-08-15

## 测试状态

使用本机 Python：

```powershell
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe -m pytest --basetemp data\pytest-tmp -o cache_dir=data\pytest-cache
```

结果：`10 passed`。

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
- 已有 `gold.json`: 0
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

- 真实 LLM prompt 需要用 gold 样本迭代。
- 当前真实样本没有 gold，evaluation 只能验证流程，不能衡量准确率。
- 可以先运行 `draft-gold` 生成 `gold_draft.json`，审核后再 `promote-gold`。
- PaddleOCRProvider 已在项目 `.venv` 中用 PaddleOCR 3.7.0 跑通单图 inspect。
- 第一次运行 PaddleOCR 会下载官方模型到 `C:\Users\33967\.paddlex\official_models\`。
- 真实小红书/牛客自动采集仍属于后续阶段，不在本阶段实现。
