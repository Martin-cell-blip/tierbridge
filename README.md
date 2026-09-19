# TierBridge 分层桥 — EAL 分层教学引擎

教师提供一节课的目标、成功标准、术语和材料，TierBridge 生成**同一学习目标下的三层任务单**（Foundation / Core / Extension）＋ 分层 exit ticket ＋ 教师手册，全部可直接 A4 打印；exit ticket 回收后一条命令算出 **EAL 与 non-EAL 学生的达标率差距**。

核心原则（代码级不变量，有测试守护）：
> **三个层级共享同一个学习目标、同一组成功标准、同一套 exit ticket 题目——只有语言支架不同。** 支持的是语言，从不降低思维要求；支架必须逐步撤除。
> **Tier determines challenge level; skill profile determines what happens inside the tier.**（v0.3.3：层级由整体 readiness 决定，弱项永不降级——弱项决定层级内怎么教）

## Skill Profile 与三问式 Rationale（v0.3.3）

统一评估数据模型：任何测评（诊断/exit ticket）用 `--items items.csv`（`item,function`）声明每题的认知功能（concept/calculate/interpret/define/explain/evaluate…），诊断和 exit ticket 共享同一套 taxonomy，按题型差距全链路自动计算。

每个学生的指派不再只有掌握率＋层级，而是回答三个问题：
1. **Why this tier**：整体 readiness ＋ 移动备注；
2. **What is limiting**：分技能画像（strong ≥75% / developing ≥40% / weak），有 secure 基础时点名最弱技能；无 secure 基础时判"foundations first"而非单点缺口；
3. **What next**：按 limiting 技能给教学动作模板（如 interpret 弱 → "targeted interpretation task on results the student can already compute, with reduced calculation load"）。

教师覆写时机器让位：覆写理由即教学决定，书面 profile 仅作参考附注（"Teacher's direct evidence takes precedence for tiering"），机器不再越权开处方。

## 快速开始

```bash
pip install -r requirements.txt

# 生成三层工作纸包（离线，无需任何 API）
python -m tierbridge generate examples/ped_lesson.yaml -o out
# → out/ped_lesson_pack.html   （Ctrl+P 打印，每页一张 A4）

# 回收 exit ticket 后算达标率差距
python -m tierbridge gap examples/results_demo.csv -o out
# → out/results_demo_gap.html  （演示数据：non-EAL 87.5% vs EAL 66.7%，差距 20.8pp）

# v0.2：由结果推导下一轮每个学生的层级指派（闭环）
python -m tierbridge assign examples/results_demo.csv -o out [--previous 上一轮指派.csv]
# → out/results_demo_assignments.csv + results_demo_groups.html（可打印分组表）
```

## 教学循环（v0.2 闭环）

```
generate 工作纸包 → 上课 → exit ticket → gap 差距报告
        ↑                                    ↓
        └────────── assign 下一轮层级指派 ←──┘
```

## 班级持久化与跨课趋势（v0.3）

单课工具之上加一层**班级记录**（单文件 `class.json`，透明可 diff，不引数据库）：

```bash
# 建班（roster: student,eal）
python -m tierbridge class init "10B Economics" --roster roster.csv --dir classes/10B

# 每节课后录入 exit ticket 结果：自动以上一课的层级为 previous 做指派，
# --lesson 提供课文件则同时按题型（define/calculate/interpret…）分解差距，
# --overrides (student,tier,reason) 记录教师覆写——reason 必填
python -m tierbridge class record classes/10B lesson1_results.csv --lesson ped_lesson.yaml
python -m tierbridge class record classes/10B lesson2_results.csv --lesson ped_lesson.yaml --overrides overrides.csv

# 跨课趋势报告
python -m tierbridge class trend classes/10B -o out
```

趋势报告（`*_trend.html`）回答两个真正的教学决策问题：

1. **这个学生为什么升级/没升级？** 每格层级旁附机器规则备注（moves up / stays / anti-crutch / 限一步），教师覆写以 † 标记并显示 reason——系统的每个决定都可追问。
2. **差距在收敛吗？** 逐课 EAL 差距序列（±3pp 噪声带内判 flat）＋**按题型分解的差距趋势**（↓收敛/→持平/↑扩大）——能看出"概念题差距在关、解释题差距还开着"这类可行动信号。

演示班级（`examples/class_demo/`，10 人 4 EAL、3 节课、1 次覆写、1 次缺勤）：差距 +50.0 → +25.0 → +0.0 pp，判定 converging；Alex（EAL）走出 Bridge→Core→Stretch 的完整轨迹。

`assign` 的规则是确定性的、印在分组表上、教师可推翻：
1. **层级只看 readiness**（上次 exit ticket 掌握率）：≥80% → Stretch；50–79% → Core；<50% → Bridge。
2. **EAL 是独立的语言轴**：EAL 学生在任何层级保留词表支持，**EAL 永远不把人往下压层**。
3. 有上一轮指派时，每周期最多移动一层（防止来回甩）。
4. **反拐杖规则**：Bridge 层学生带全支架拿到 ≥80%，必须上移——支架变成了天花板。
5. 下移的学生意味着要重教，不只是换层。

## 两种生成模式

| 模式 | 触发 | 说明 |
|---|---|---|
| **authored** | lesson.yaml 内含 `worksheets:` | 任务由教师（或经教师审核的 AI 草稿）成文，直接排版。`examples/ped_lesson.yaml` 是一份完整成文示例（IGCSE 经济·需求价格弹性） |
| **template** | 无 `worksheets:` | 离线从成功标准＋句式框架库生成任务骨架（标注 `[teacher: ...]` 待填），教师十分钟内补完 |

可选 AI 起草（`--ai`，需 `TIERBRIDGE_API_KEY`，OpenAI 兼容端点，默认 DeepSeek）：模型按合同起草三层任务（同目标、t1 嵌句式框架、t3 必含 challenge、每任务 ≤70 词），**违反合同即拒绝**；通过后教师手册自动加红色「AI 起草——课前必须人工审核」标记。

## 工作纸包里有什么（7 页）

1. **教师手册**：分层带班要点（t1 词表先行口头预教、t3 不许提前完工闲置等）、支架撤除原则、exit ticket 评分口径、结果记录方法
2. **三层任务单**：t1 = 双语词表＋句式起步＋分步计算；t2 = 英文词表＋半开放句式框架；t3 = 无支架＋迁移挑战题——三张纸页眉印着同一行学习目标
3. **三层 exit ticket**：题目完全相同（这是差距可比的前提），仅 t1/t2 附句式支架

## 结果记录与差距报告

CSV 三列起：`student,group,q1..qN`（group = `EAL` / `non-EAL`，每题 0/1）。
报告输出：两组掌握率（≥⅔ 题正确=掌握，阈值可调）、总差距 pp、逐题差距、SVG 条形图，并附解读警示：单次 exit ticket 是噪声信号，要看跨课收敛趋势；若 EAL 分数只在有支架时上涨，说明支架成了拐杖，须撤除后复测。

## 测试

```bash
python -m pytest tests/ -q     # 68 项，全部离线（AI 走 mock）
```

覆盖：lesson 校验（缺字段/非法题型/空层任务）、**三层同目标不变量**、词表分层策略（t1 双语/t2 英文/t3 无）、template 模式骨架、渲染断言（7 页/中文仅出现在 t1/目标行 ×3）、AI 起草合同的接受与全部拒绝路径、差距计算（手工核对的期望值）、坏数据拒绝、CLI 端到端。

## 诚实边界

- 分层与支架设计遵循通行的 scaffolding / differentiation 实践，但**本工具未经真实课堂对照实验验证**；「差距收敛」是它优化的目标，不是它已证明的效果。
- 演示 CSV 是合成数据，仅用于展示报告形态。
- AI 起草的任务必须经教师审核后使用——报告与手册中均有强制提示。
