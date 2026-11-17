# 结构化数据论文库价值复核｜2026-11-17

从公开目录撤下 **7 篇**，目录由 **380 篇调整为 373 篇**：2 篇当前独立收录增量有限，5 篇转为待补证据。原卡片、首发日期、收录日期和更新历史均归档，可在补足条件后恢复。

本次对 380 条记录做审核状态筛查，重点复核 12 篇候选的既有贡献、证据和局限；必要处补读一手正文。不是对全部论文重新完成全文审核，也没有本地运行模型。材料不足和证据不足不等于论文无价值；下列去留是针对共享研究库的取舍。

## 撤下清单

### [LLMs on Tabular Data with Limited Semantics: Evidence from Industrial Car Retrofit Prediction](https://arxiv.org/abs/2606.15314)

处理：排除当前公开目录。原因：常规应用，增量及匹配比较不足。

主要比较树模型、现成语言嵌入、提示和堆叠，混合结果仅在200行子集，未与全量基线构成配对。弱语义场景有线索价值，但当前材料未给出足够可靠、独立的新方法或部署收益，不再单独公开。

增量比较：相对既有树/嵌入/堆叠，以及库内 LightTAR 的配对语义特征评估，新增主要是一个工业任务场景；混合方案的关键优势未在相同测试集隔离。

恢复条件：补充相同测试样本、预算和输入下的受控对照，或能独立支持选型的时间外部署证据。

阅读范围：本轮重读 arXiv v1 §4.2、§5、§6.1–6.3/表1–3，核对提示与混合方案的200–500行子集；复用2026-10-15既有其余方法审核。

### [Data Presentation Over Architecture: Resampling Strategies for Credit Risk Prediction with Tabular Foundation Models](https://arxiv.org/abs/2605.18635)

处理：暂缓公开。原因：关键基线没有配平。

重采样和类别平衡的方向有价值，但传统基线未调整类别权重和阈值，默认零召回不能证明模型架构优势。相对库内银行少标签研究，当前未证明额外独立增量；先撤下，待补足公平对照。

增量比较：相对常见平衡采样/SMOTE/KMeans组合，以及库内 When Do In-Context Tabular Foundation Models Help in Banking? 的同样本少数类实验，本作仍缺基线同步重采样、阈值与预算控制。

恢复条件：在验证集调权重/阈值、对两类模型同步处理不平衡，并报告固定样本/预算的上下文策略增量。

阅读范围：本轮重读 arXiv v1 §4.2–4.4、§5.1–5.5，核对表1和采样策略定义；复用2026-10-15其余正文审核。

### [Interpretable Small-Sample Hyperspectral Phenotyping of Wheat Protein Fractions via Order-Optimized Derivative Preprocessing and TabPFN](https://www.mdpi.com/2304-8158/15/19/3507)

处理：排除当前公开目录。原因：应用增量有限。

已有光谱预处理和特征选择接 TabPFN 的单点应用；198样本、40例随机测试及同收获批次重取样支持局部可行性，但没有形成额外的通用方法或跨地区/年度证据。本库已有更广的光谱预处理评估，当前独立保留的增量有限。

增量比较：相对已有导数预处理、MRMR/RFE与 TabPFN，以及库内66项近红外任务评估，本作新增主要是小麦蛋白对象；没有新模型机制，品种外推波动且重取样来自同一收获批次。

恢复条件：补充跨年度/地区的独立外部验证，或证明可跨数据复用的新特征选择机制及实际测量成本收益。

阅读范围：本轮复核出版社 §2.4–2.8、§4.5与§5，确认训练内选择、158/40划分、25例同批次重制及跨品种范围；复用2026-11-13既有方法审核。

### [Image Dehazing as In-Context Tabular Inference](https://arxiv.org/abs/2610.25142)

处理：暂缓公开。原因：模型增量与独立测试证据不足。

把图块描述接入冻结 TabPFN 的问题改写有潜力，但主评测使用其余测试图的配对标签作参考，独立HSTS仅10对；缺同特征的树/近邻回归对照，尚未隔离TFM的额外贡献，暂缓公开。

增量比较：相对物理图块特征、参考检索和现成回归组件，核心增量是以冻结 TabPFN 替换回归器；论文未用相同表示和监督条件的普通回归器证明这一步的独立价值。

恢复条件：补充完全独立参考/测试集、同特征树/近邻回归及匹配监督预算的专用方法对照，报告重复实验。

阅读范围：本轮重读 arXiv v1 III-C–D、IV-A–B/表III，确认leave-one-image-out参考方式、HSTS10对与对照类型；复用2026-10-27既有方法及实验审核。

### [Context Curation Is Not a Free Lunch: An Empirical Test of Inference-Time Robustness for Tabular Foundation Models Under Distribution Shift](https://doi.org/10.5281/zenodo.24198181)

处理：暂缓公开。原因：核心实验配置冲突尚未解决。

负结果本身可有价值，但模型版本未固定、类别采样正文与实现不一致，部分策略不足名义样本数，妨碍解释固定预算下的上下文选择结果。今天初次收录后按更严格价值门槛撤下，待协议统一再审。

增量比较：相对随机上下文、密度重加权和库内 LUCoS/ARASH，新增价值应来自可信的分布漂移负结果；现有版本与实际样本预算冲突阻碍这项独立证据成立。

恢复条件：固定 TabPFN/权重版本，统一正文与代码中的采样策略，补足或披露各策略实际样本数，并重跑匹配预算结果。

阅读范围：复用今天09:03批次已经读过的15页正文§3–6/表2–6、9及作者strategies.py、baselines.py、requirements、EXPERIMENT_MANIFEST；本轮重评收录价值，未重复下载或声称独立复现。

### [Pavement performance prediction via a tabular foundation model](https://doi.org/10.1016/j.cacaie.2026.100097)

处理：暂缓公开。原因：未完成全文方法审核。

此前只有出版商索引的部分正文，完整方法/外部验证尚未取得；跨路网及巡检减负主张缺少可核验的完整依据。不能用行业相关性替代完整证据，转为待核验。

增量比较：现有贡献是把 TabPFN 用于路面状态预测。相对普通小样本预测应用，独立价值需要可核验的外部路网/少数维修类与实际巡检效果，目前资料不足。

恢复条件：取得完整方法与外部验证正文，核对时间划分、少数类结果、基线配置与巡检减负测算。

阅读范围：复用2026-10-15部分审核：仅出版商索引第3–5节片段；本轮DOI打开重定向仍不可读。未取得完整PDF，不声明完成方法重审。

### [Conformal Prediction for Tabular Prior-Data Fitted Networks with Missing Data](https://openreview.net/pdf?id=TnZcC7GXI5)

处理：暂缓公开。原因：正文缺失且实现冲突。

此前仅有摘要和作者notebook，完整正文仍受访问限制；主函数与附加实验的分位数修正不一致、未见缺失模式仅告警，核心覆盖主张未完成审核，撤下待补。

增量比较：相对已有 CP-MDA 缺失模式校准，新增是接入 TabPFN 分位数预测；是否保留覆盖条件、如何处理未见模式，现有部分材料不足以确认独立方法价值。

恢复条件：取得全文并核对假设/证明，统一分位数公式，明确未见缺失模式的处理及覆盖实验。

阅读范围：复用2026-10-15作者两个notebook的静态审核；本轮OpenReview论坛返回验证页、PDF返回403，未新增完整正文阅读或运行复现。

## 复核后保留

- [Accurate predictions of properties of energetic materials with tabular foundation models](https://arxiv.org/abs/2611.14462)：保留材料预测评估：同材料分组、重复评估与折内表示构建提供受控的独立领域证据；不因没有新基础模型就删除，也不据混合硬件计时认定加速。
- [Prediction of cognitive impairment in Parkinson’s disease using TabPFN: an integrative analysis of clinical data, longitudinal trajectories, and lipidomics](https://www.frontiersin.org/journals/aging-neuroscience/articles/10.3389/fnagi.2026.1905374/full)：保留帕金森认知预测：有独立PPMI队列的外部区分能力证据；时间窗与缺失特征限制仍保留，不作为临床部署证明。
- [TabFM-Auto: Self-Evolving Pipelines for Tabular Foundation Models](https://arxiv.org/abs/2609.37989)：保留 TabFM-Auto：虽然跨折汇总有搜索信息交叉风险，独立第0折及模型外流程搜索仍有明确技术贡献；不沿用无条件泛化主张。
- [Entity Matching using Decision Models](https://arxiv.org/abs/2610.34626)：保留 Entity Matching using Decision Models：固定提示B0的八基准对照可独立保留；测试标签选择F0后的级联等结果仍明确限制。
- [Structure-agnostic Causal Representation Learning](https://arxiv.org/abs/2610.00968)：保留 Structure-agnostic Causal Representation Learning：软选择不变性具有独立机制和限定假设下的理论线索；oracle选参实验不作为部署优势证明。

以上保留判断复用已有全文审核；材料预测评估另补读§3.4–3.5等评测协议。原结论与局限不改写，不制造新的收录或更新日期。

## 后续收录

新增前须分别完成正文质量审核与独立价值判断；对照前作，交代具体增量和支撑证据。常规场景替换、没有配平的微小收益或关键协议未解决的候选保留为线索。基准、负结果、工程工具和行业应用仍可凭其独立证据或可复用能力收录。

规则见 [COLLECTION.md](COLLECTION.md#新增价值门槛)。撤下的完整记录见 [withheld-papers.json](withheld-papers.json)，筛选决定见 [decisions.json](decisions.json)。已发小报保留当时记录；站点和后续小报总数使用当前公开目录。
