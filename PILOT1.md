# Pilot 1 — 真实课堂验证协议

> Pilot 0 判定（2026-08-25，第一用户评审）：Engineering 9 / Decision quality 9 /
> Teacher usability 8.5 / Instructional intelligence 7.5 / **Pilot readiness: READY**。
> 本协议执行期间**冻结全部功能开发**。验证的问题不是"它能不能分组"，而是：
> **它能不能帮助老师改变教学决策？老师为什么信它？什么时候老师应该不信它？**

## 范围

- 真实学生 10–15 人 × 2–3 节课（一个教学小单元）
- 使用当前版本（TierBridge v0.3.3），不改一行代码
- 常规流程照旧：`class init` → 诊断 `record --items` → 上课 → exit ticket `record --items [--overrides]` → `class trend`

## 每节课只记录四件事（pilot_log.csv，每生一行）

| 字段 | 内容 |
|---|---|
| `system_recommendation` | 系统给的 tier + rationale 要点（从 class.json 抄，不改写） |
| `teacher_decision` | 老师实际采用的 tier / 支架（含 override 及理由） |
| `actually_taught` | 该生实际做了什么任务（一句话，事后如实记） |
| `exit_result` | exit ticket 得分（与 record 数据一致） |

外加一个字段 `divergence_reason`：**老师没听系统时，为什么**——这一列的价值可能超过所有 accuracy 数字。

## 纪律

1. 系统建议永远先于老师决定被记录（防止事后合理化）；
2. override 必须走 `--overrides` 留档，不允许口头改完不记；
3. 缺勤记缺勤，不补 0；
4. 若凑得齐 pre/post（首末课同构测评），挂 edulab：`import-tierbridge` 出增益报告；
5. 任何"顺手修一下"的冲动 → 写进本文件末尾的 backlog，不动代码。

## 成功判据（定性优先）

- 老师在第 2、3 节课是否**主动**去看 rationale（而不是被要求看）；
- divergence 案例里，系统错在哪一类（数据缺口 / 阈值 / 教师私有信息）；
- 有没有一次教学决策因为 skill profile 而改变（如 Michael 型：不降级但换任务）。

## 冻结 Backlog（Pilot 1 之后再议）

1. **重复 limiting skill 升级阶梯**（Pilot 0 遗留的核心洞察）：同一 limiting skill 连续
   N 轮未收敛时，rationale 从 "interpretation is weak" → "remains weak despite targeted
   practice" → "current intervention is not producing improvement; reconsider the
   instructional approach"。adaptive teaching ≠ adaptive grouping。
2. Instructional execution 深化：从 next-move 一句话到"材料/题量/model-first 还是
   independent/支架何时撤"的课内执行层（评审维度⑥，7.5 分短板）。
3. 15 人 rationale 的课前汇总视图（"老师读完还要自己汇总一次"，评审维度①）。
