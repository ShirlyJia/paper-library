# 研究书架维护

- 当前目录以 `data/papers.json` 为唯一维护源。保留已有论文和目录 ID。
- 涉及检索、收录或查漏时，先读 `research/COLLECTION.md`。同时使用主题、模型家族／版本、正式会议、作者发布及引用追溯，不只搜 arXiv 标题。
- 每日更新遵循 `research/DAILY_UPDATE.md`：`npm run collect:daily` 采集到期渠道，`npm run queue` 管理待审队列，`npm run apply:review` 写入审核结果，`npm run collect:finish` 生成 review.json 与小报并推进完整完成的渠道检查点；审核者按 `research/BRIEFING_PROMPT.md` 只写小报的 `briefing-highlights.md`（"今天的看点"：150–300 字平实说明今天的主线和重点论文）；过程问题写进 `run-notes.md`，不混入小报。不为这些步骤另写一次性脚本。没有内容变化时不改目录更新时间。
- 内容编辑完成后、提交前运行 `npm run record:updates`，维护不可随更正改写的 `addedAt` 和按日去重的 `collectionUpdates`。首发、论文修订与本站收录是三个独立日期。
- 用户已授权的飞书群小报由 `collect:finish` 按本机 `work/notifications/feishu.json` 发送；只发已上线小报与站点链接，读取回执去重，失败用 `npm run briefing:send` 重试。群 ID、身份配置、回执和凭证不提交仓库，不向其他接收方发送。
- 站点为团队共享论文库；页面、分享信息和公开目录不加个人署名。论文默认按首发时间倒序，修订和入库不能覆盖首发日期。
- 近半年重点覆盖，关键前作保留；不得按固定篇数、已有代表作或包含预训练内容直接删掉相关模型论文。
- TabArena 相关论文也可收录，包括基准、数据集与评测协议、在其上评估的模型和算法，以及性能、效率与复现研究；不限于基础模型，核验后说明与 TabArena 的关联。
- `npm run collect` 产生候选，核验后再写公开目录；筛选去向记录在 `research/decisions.json`，新模型与版本补入 `research/model-families.json`。
- 新增收录和涉及方法／实验结论的更正须按 `research/COLLECTION.md` 的“质量与价值审核”阅读相关正文，记录贡献、证据、局限和价值；仅摘要不足以完成审核。卡片概览与更新小报保留关键判断，不以会议、引用量或机构名替代质量依据，不给未经校准的综合分数。
- 不运行仓库外历史 `build-report.py` / `prepare-library.py` 覆盖当前目录；旧排除名单不再适用。
- 保持现有六大类完整标题、主会与 Workshop 区分、已核实的展示标签及直接原文跳转。不要恢复“优先阅读”或“验证与边界”。
- 发布前运行 `npm run check`，再检查新增条目在相关目录、年份和简称搜索下能否找到。对采集失败、未核验候选和未复现结果明确保留证据边界。
