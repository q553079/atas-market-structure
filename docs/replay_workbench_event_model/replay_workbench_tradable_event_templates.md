# Replay Workbench 可交易事件标准模板

> 状态：v0.1
>
> 用途：将“事件交易”从抽象理念进一步落成可执行模板。
>
> 目标：为当前最重要的三类事件提供统一结构，便于：
>
> - 盘中快速命名
> - 定义确认条件
> - 定义失效条件
> - 定义时间窗
> - 定义接管事件
> - 用于复盘和未来 AI 协作

---

## 0. 相关文档

建议按下面顺序配合阅读：

1. `docs/replay_workbench_event_model/replay_workbench_event_reasoning_playbook.md`
   - 理解总体理念
2. `docs/replay_workbench_event_model/replay_workbench_hidden_state_event_memory_model.md`
   - 理解正式模型
3. `docs/replay_workbench_event_model/replay_workbench_event_trading_training_checklist.md`
   - 理解训练方式
4. 本文档
   - 直接拿来做盘中与复盘模板

---

## 1. 使用方式

本模板册不是让你机械背诵，而是用于回答以下问题：

1. 当前主事件是什么
2. 我现在是在交易“像”，还是交易“开始兑现”
3. 这个事件接下来该如何展开
4. 它多久内该展开
5. 出现什么说明它已经不成立
6. 出现什么说明新事件已经接管

建议盘中至少压缩成这 6 行：

```text
当前主事件：
当前背景：
确认条件：
时间窗：
失效条件：
潜在接管事件：
```

---

## 2. 模板字段总规范

每个可交易事件模板都应包含以下字段。

## 2.1 基本字段

- `event_name`
- `canonical_kind`
- `event_family`
- `market_context`
- `related_regime`

## 2.2 盘中判断字段

- `core_question`
- `setup_features`
- `validation_rules`
- `invalidation_rules`
- `time_window`
- `anchor_dependencies`
- `dom_orderflow_checks`

## 2.3 执行字段

- `entry_style`
- `exit_logic`
- `downgrade_logic`
- `replacement_events`

## 2.4 复盘字段

- `common_false_positive`
- `common_false_negative`
- `review_questions`

---

## 3. 事件一：动能延续

## 3.1 核心定义

动能延续不是“已经涨了很多所以还会涨”，也不是“已经跌了很多所以还会跌”。

它真正的定义是：

**原主导方向仍具有 initiative，且在合理时间窗内能够重新发动新一波推进。**

---

## 3.2 标准模板

### `event_name`

`动能延续`

### `canonical_kind`

`momentum_continuation`

### `event_family`

`initiative / continuation`

### `market_context`

适用于：

- 强动能趋势中
- 弱动能趋势但仍未回到旧平衡中心
- 经过浅回调后观察是否再发动

### `related_regime`

优先出现于：

- `strong_momentum_trend`
- `weak_momentum_trend_narrow`

---

## 3.3 核心问题

盘中要问的不是：

- 它是不是已经涨了很多

而是：

**如果它仍然是趋势延续事件，那么它应当在合理时间窗内再次发动，而不是一直拖着不走。**

---

## 3.4 Setup Features

常见前置特征：

- 前一波已有明确位移
- pullback 相对浅
- 没有深回旧平衡中心
- 主导方尚未出现明显效率崩塌
- 结构上仍维持高低点优势

---

## 3.5 Validation Rules

成立时通常应看到：

1. 在合理时间窗内出现新的 initiative push
2. 回调后重新夺回位移效率
3. 回调深度受控
4. 没有明显回到旧 balance center
5. 若接近历史锚点，突破后表现出 acceptance 而不是立即收回

可以简化成一句盘中表达：

`如果它真是延续，就应该尽快重新发动，而不是长时间拖入平衡。`

---

## 3.6 Time Window

重点不是绝对分钟数，而是“相对节奏”。

建议初版训练时使用经验化时间窗：

- 强动能：`3~10 根 K 内`
- 中等动能：`10~30 分钟内`
- 若超过该时间窗仍无新 initiative，则降级

建议你训练时明确写：

- `next_5_bars`
- `next_15m`
- `before_return_to_old_balance`

---

## 3.7 Invalidation Rules

下列情况通常说明“动能延续”不再可靠：

1. 在预期时间窗内没有重新发动
2. 价格重新回到旧平衡中心
3. pullback 明显变深，趋势效率破坏
4. 出现明显 opposite initiative displacement
5. 接近关键锚点后不是 acceptance，而是 rejection / trap

---

## 3.8 Anchor Dependencies

要特别注意以下锚点是否影响延续：

- 旧平衡中心
- 旧累积中心
- 缺口边缘
- 启动点
- 前一轮失败突破参考位

如果价格重新深回这些区域，延续剧本通常需要降级。

---

## 3.9 DOM / Order Flow Checks

DOM 只作为机制证据：

- 是否有延续方向的主动推进
- pullback 时对手是否真正压进来
- 穿越前方档位是否容易
- 是否出现真空区支持推进
- 是否出现对手刷新防守并拖慢节奏

---

## 3.10 Entry Style

更稳的参与方式通常是：

1. 浅回后确认再次发动
2. 小平衡后向原方向 acceptance
3. 关键锚点测试后确认继续推进

不建议：

- 只因为“已经很强”就追
- 只因为“看起来像趋势”就忽略时间窗

---

## 3.11 Exit / Downgrade Logic

退出或降级的核心不是亏损，而是：

- 该事件没有按预期展开
- 该事件节奏明显变慢
- 该事件被新事件接管

常见降级路径：

`momentum_continuation -> balance_formation`

常见接管路径：

`momentum_continuation -> reversal_preparation`

---

## 3.12 Common False Positive

常见误判：

1. 把“停顿”误认成“必然再发动”
2. 把“趋势余温”误认成“仍然强趋势”
3. 忽略回到旧中心后的结构变化
4. 只看方向，不看节奏

---

## 3.13 Review Questions

复盘时重点问：

1. 我看到的是“趋势还在”，还是“趋势真的重新发动”？
2. 时间窗是否已经超期？
3. 它是否已经回到不该回到的旧中心？
4. 我是否把拖延误当成酝酿？

---

## 4. 事件二：均值回归

## 4.1 核心定义

均值回归不是“跌多了就该涨，涨多了就该跌”。

它真正的定义是：

**价格偏离某个被市场记住的中心后，重新向该中心或其附近价值区回归。**

这个中心可能是：

- 平衡中心
- 累积中心
- 高成交接受区
- 震荡中轴

---

## 4.2 标准模板

### `event_name`

`均值回归`

### `canonical_kind`

`mean_reversion`

### `event_family`

`balance / reversion / target-seeking`

### `market_context`

适用于：

- 当前处于平衡区或过渡区
- 明显偏离某个历史或当前中心
- 当前更像测试/回归，而不是单边加速

### `related_regime`

优先出现于：

- `balance_mean_reversion`
- `compression`
- `transition_exhaustion`

---

## 4.3 核心问题

盘中要问的不是：

- 它是不是跌太多了

而是：

**市场是否正在把价格重新拉回某个有效中心。**

---

## 4.4 Setup Features

常见前置特征：

- 价格偏离中心较远
- 存在明确的中心或锚点
- 单边推进效率下降
- 出现回归路径而非继续失衡
- 当前更像目标回补 / 回访，而非新一轮单边启动

---

## 4.5 Validation Rules

成立时通常应看到：

1. 价格开始朝中心移动，而非继续远离
2. 偏离方向的 initiative 减弱
3. 回归过程中没有被强 opposite event 打断
4. 中心附近确实表现出吸引力
5. 到达中心后出现合理反应，而不是直接轻松穿透后接受新区域

盘中可以简化成：

`如果它真是均值回归，就应当逐步回到中心，而不是重新加速离开中心。`

---

## 4.6 Time Window

均值回归通常比强动能延续更允许“慢一点”，但也不能无限拖。

建议训练时按以下方式写时间窗：

- `within_current_session`
- `within_next_20m`
- `before_new_initiative_breakout`

关键是：

- 回归要在合理时间内持续朝中心推进
- 如果长时间既不到中心，也不再接近中心，则剧本要降级

---

## 4.7 Invalidation Rules

下列情况通常说明“均值回归”不再可靠：

1. 出现更强 initiative displacement，重新单边离开中心
2. 回归过程中被关键位 rejection 后迅速失败
3. 市场表现出 acceptance 于新单边区域，而不再以中心为目标
4. 原本应回归的中心被明显消耗、失效或角色变化

---

## 4.8 Anchor Dependencies

均值回归高度依赖锚点。

重点锚点包括：

- balance center
- accumulation center
- high-volume acceptance zone
- old distribution center

没有明确中心，通常就不应轻易把它叫做“均值回归”。

---

## 4.9 DOM / Order Flow Checks

DOM 在这里主要用来看：

- 价格靠近中心时是否真的被吸引
- 中心附近是否存在稳定流动性兴趣
- 到达中心后是 acceptance、停留，还是 rejection 后离开
- 是否出现更强 opposite initiative 破坏回归路径

---

## 4.10 Entry Style

更稳的参与方式通常是：

1. 已经确认开始回归中心
2. 路径中没有被更强单边事件打断
3. 到达中心附近时，结合反应决定是否继续持有或减仓

不建议：

- 只因“离得远了”就逆着做
- 没有中心概念就硬说均值回归

---

## 4.11 Exit / Downgrade Logic

均值回归事件常见的退出逻辑：

1. 已达到预期中心或目标带
2. 到达中心后反应不如预期
3. 新单边事件接管，原回归逻辑被破坏

常见降级路径：

`mean_reversion -> balance_formation`

常见接管路径：

`mean_reversion -> initiative_displacement`

---

## 4.12 Common False Positive

常见误判：

1. 把“超涨超跌感受”误当成均值回归
2. 没有明确中心，仍然强行做回归
3. 忽略更强 initiative 已经接管
4. 到达中心后还把同一剧本硬扛到底

---

## 4.13 Review Questions

复盘时重点问：

1. 我回归的目标中心到底是什么？
2. 市场真的在回归中心，还是我在主观想象？
3. 到中心后，市场反应是什么？
4. 我有没有把“到达目标”误判成“还会继续回归”？

---

## 5. 事件三：吸收 -> 反转准备

## 5.1 核心定义

吸收本身不是反转。

本事件的真正定义是：

**原单边推进在关键区域出现持续吸收与效率下降，使市场从单边推进逐步转入“可能反转”的准备阶段，但尚未完成反转确认。**

所以它的关键词是：

- `吸收`
- `压缩`
- `效率下降`
- `反转准备`

而不是：

- `已经反转`

---

## 5.2 标准模板

### `event_name`

`吸收 -> 反转准备`

### `canonical_kind`

`absorption_to_reversal_prep`

### `event_family`

`absorption / exhaustion / transition`

### `market_context`

适用于：

- 单边推进后期
- 关键位置附近出现反复承接
- 推进效率下降
- 市场开始从失衡走向过渡

### `related_regime`

优先出现于：

- `transition_exhaustion`
- `compression`

---

## 5.3 核心问题

盘中要问的不是：

- 这里是不是已经见底 / 见顶

而是：

**这里的吸收，是普通获利了结、下跌中继停顿，还是正在为反转创造条件。**

---

## 5.4 Setup Features

常见前置特征：

- 原趋势推进速度变慢
- K 线实体逐步缩短
- 在相对窄空间内持续停留
- 主动打击仍在，但位移效率下降
- 接近关键锚点或旧中心

---

## 5.5 Validation Rules

只有以下条件逐步出现，才可从“吸收”升级为“反转准备”：

1. 吸收持续存在，而不是一次性停顿
2. 原趋势方向的新高/新低效率持续下降
3. 出现较窄空间内的压缩与承接
4. 开始出现 opposite initiative 的早期迹象
5. 接近关键锚点后，不再轻易继续原方向扩展

盘中可简化成：

`吸收必须先成立，反转准备才可能成立；没有后续 opposite evidence，就不能直接叫反转。`

---

## 5.6 Time Window

这类事件通常比动能延续更慢，但一定要有“从吸收到反转准备”的推进过程。

建议训练时写成：

- `over_next_10_to_30m`
- `within_next_few_tests`
- `before_fresh_trend_reacceleration`

如果吸收持续很久，却始终没有 opposite initiative、没有关键位回补、没有结构改善，则不能一直把它解释成“马上反转”。

---

## 5.7 Invalidation Rules

以下情况通常说明“吸收 -> 反转准备”失效：

1. 原方向出现新的强 initiative，再次有效推进
2. 窄区间被原趋势方向轻松打穿并接受
3. 关键确认迟迟不出现，只剩静态横盘
4. 接近关键锚点后，没有任何 opposite response

---

## 5.8 Anchor Dependencies

这类事件对锚点特别敏感。

重点关注：

- 旧累积中心
- 旧平衡中心
- 缺口边缘
- 启动点
- 失败突破参考位

如果吸收恰好发生在这些结构附近，其“反转准备”意义通常更高。

---

## 5.9 DOM / Order Flow Checks

这里是 DOM 与 order flow 最有价值的场景之一。

重点观察：

- 是否存在持续被动吸收
- 主动打击后价格是否越来越难走远
- 关键位上是否反复刷新防守
- 原方向是否开始出现流动性撤退
- opposite initiative 是否开始出现

但要记住：

DOM 只能增强“准备阶段”的判断，不能单独宣布反转完成。

---

## 5.10 Entry Style

更稳的参与方式通常是：

1. 先确认吸收不是一次性停顿
2. 再等待 opposite initiative 或关键结构改善
3. 更偏向“反转准备后的确认参与”，而不是“只因吸收就提前赌顶底”

---

## 5.11 Exit / Downgrade Logic

这类事件最常见的错误是：

- 把吸收直接做成反转

因此退出与降级逻辑应格外明确：

1. 若一直没有 opposite confirmation，则降回普通吸收/过渡
2. 若原趋势重新发动，则直接失效
3. 若被更强位移事件接管，则退出旧叙事

常见降级路径：

`absorption_to_reversal_prep -> passive_absorption_only`

常见接管路径：

`absorption_to_reversal_prep -> momentum_continuation`

---

## 5.12 Common False Positive

常见误判：

1. 看见吸收就当成反转
2. 只因为窄，就以为是底部/顶部
3. 忽略原趋势方向仍未真正失效
4. 没有等 opposite initiative 和结构确认

---

## 5.13 Review Questions

复盘时重点问：

1. 当时我看到的是“吸收”，还是“已经反转”？
2. opposite confirmation 有没有真正出现？
3. 原趋势方向是否已经真正丧失效率？
4. 我是不是把普通获利了结误判成反转准备？

---

## 6. 事件四：突破接受

## 6.1 核心定义

突破接受不是“价格碰过去一下”。

它真正的定义是：

**价格突破旧边界、旧平衡区或关键结构位后，不只是短暂穿越，而是开始在新区域被市场接受。**

关键关键词：

- 突破
- 站稳
- 接受
- 新区域组织

---

## 6.2 标准模板

### `event_name`

`突破接受`

### `canonical_kind`

`breakout_acceptance`

### `event_family`

`break / initiative / acceptance`

### `market_context`

适用于：

- 压缩后突破
- 平衡区边界突破
- 关键高低点突破后观察是否站稳
- 旧缺口边缘或关键锚点上破/下破后观察是否形成新接受区

### `related_regime`

优先出现于：

- `compression`
- `strong_momentum_trend`
- `transition_exhaustion` 结束后向新方向切出

---

## 6.3 核心问题

盘中要问的不是：

- 它是不是已经破位了

而是：

**它破位之后，市场是否真的愿意在新区域继续成交、停留、组织，而不是只是扫过去一下。**

---

## 6.4 Setup Features

常见前置特征：

- 旧平衡区或明显边界存在
- 价格已接近边界
- 压缩或组织完成
- 一侧开始出现明显 initiative
- 突破后理论上有新空间可走

---

## 6.5 Validation Rules

成立时通常应看到：

1. 突破后没有立即被打回旧区域
2. 新区域内开始有停留、组织或二次推进
3. 回踩边界时能守住，而不是深度回收
4. 突破后的 order flow / DOM 不表现为明显失败
5. 若存在历史锚点，突破后表现为 acceptance，而不是 test 后 rejection

盘中可简化成：

`如果它真是突破接受，就不应很快回到旧平衡里，而应在新区域开始站稳。`

---

## 6.6 Time Window

突破接受的时间窗通常偏短。

建议训练时优先写成：

- `next_3_to_8_bars`
- `within_next_5_to_15m`
- `before_full_reentry_into_old_balance`

如果突破后很久都无法在新区域站稳，则要快速降级。

---

## 6.7 Invalidation Rules

以下情况通常说明“突破接受”失效：

1. 突破后迅速回到旧平衡区
2. 回踩边界时明显失守
3. 新区域没有形成接受，反而快速被 opposite initiative 打回
4. 突破方向只完成了扫流动性，没有后续组织

---

## 6.8 Anchor Dependencies

重点锚点包括：

- 旧平衡区边界
- 旧震荡上沿 / 下沿
- 缺口边缘
- 前高 / 前低
- 历史接受区边缘

突破是否被接受，常常取决于这些边界在突破后的反应。

---

## 6.9 DOM / Order Flow Checks

重点观察：

- 打穿边界后是否容易继续 trade through
- 是否出现顺突破方向的挂单迁移
- 是否没有立刻遭遇强 opposite defense
- 回踩时 defense 是否有效
- 是否出现新区域内的接受，而不是冲高/冲低后空心化

---

## 6.10 Entry Style

更稳的参与方式通常是：

1. 突破后确认没有立刻失败
2. 新区域站稳后参与
3. 或边界回踩守住后参与

不建议：

- 只因“刚刚突破”就立刻默认接受已经成立

---

## 6.11 Exit / Downgrade Logic

退出或降级逻辑重点看：

1. 是否重新回到旧平衡区
2. 是否形成真正接受失败
3. 是否被“失败突破”事件接管

常见降级路径：

`breakout_acceptance -> pending_break_test`

常见接管路径：

`breakout_acceptance -> failed_breakout_rejection`

---

## 6.12 Common False Positive

常见误判：

1. 把“碰过去一下”当成接受
2. 只看一根突破 K，不看后续站稳
3. 忽略回踩守不住
4. 把扫流动性误判成真突破

---

## 6.13 Review Questions

复盘时重点问：

1. 突破后，市场有没有真的在新区域接受？
2. 是“穿越”了，还是“站稳”了？
3. 回踩时有没有守住边界？
4. 我是不是把 stop run 当成了 breakout acceptance？

---

## 7. 事件五：失败突破 / 假突破拒绝

## 7.1 核心定义

失败突破不是“突破之后回调一下”。

它真正的定义是：

**价格穿越明显边界或流动性池后，未能在新区域形成接受，反而迅速被打回原区域，并开始表现出陷阱或拒绝特征。**

关键关键词：

- 扫过
- 没站住
- 回收
- 拒绝
- 陷阱

---

## 7.2 标准模板

### `event_name`

`失败突破 / 假突破拒绝`

### `canonical_kind`

`failed_breakout_rejection`

### `event_family`

`sweep / trap / rejection`

### `market_context`

适用于：

- 明显边界附近
- 旧高 / 旧低附近
- 平衡区边界
- 缺口边缘
- session high / low

### `related_regime`

优先出现于：

- `compression`
- `balance_mean_reversion`
- `transition_exhaustion`

---

## 7.3 核心问题

盘中要问的不是：

- 它是不是扫流动性了

而是：

**扫完以后，市场有没有接受新区域；如果没有，是否正在把追进去的人变成被困盘。**

---

## 7.4 Setup Features

常见前置特征：

- 市场接近明显边界或流动性池
- 存在突破预期
- 穿越边界后出现短暂位移
- 但突破后缺乏持续接受

---

## 7.5 Validation Rules

成立时通常应看到：

1. 价格穿越关键边界或前高 / 前低
2. 穿越后未能在新区域停留和组织
3. 很快重新回到旧区域
4. 出现 opposite initiative 或明显 rejection
5. 被套盘开始显现，原突破方向跟进不足

盘中可简化成：

`如果它真是失败突破，就应当很快回收边界，而不是在新区域继续站稳。`

---

## 7.6 Time Window

失败突破通常比真正接受更快暴露。

建议训练时优先写成：

- `next_1_to_5_bars`
- `within_next_3_to_10m`
- `before_breakout_side_reorganizes`

如果突破后长时间在新区域站住，就不该再硬坚持“失败突破”叙事。

---

## 7.7 Invalidation Rules

以下情况通常说明“失败突破”失效：

1. 价格没有快速回收边界
2. 新区域开始形成接受
3. 回踩后反而守住新边界
4. breakout 方向重新出现有效 initiative 并继续组织

---

## 7.8 Anchor Dependencies

重点锚点包括：

- 旧高 / 旧低
- balance edge
- 缺口边缘
- session extreme
- 历史失败突破参考位

失败突破往往与“明显大家都看见的边界”高度相关。

---

## 7.9 DOM / Order Flow Checks

重点观察：

- 穿越后是否没有继续 trade through
- 是否很快出现 opposite defense
- 突破方向挂单是否迅速撤退
- 是否出现 trapped response
- 原方向是否缺乏后续跟进

---

## 7.10 Entry Style

更稳的参与方式通常是：

1. 先等回收边界
2. 再等 rejection 或 opposite initiative 确认
3. 不提前无条件去猜“这一定是假突破”

---

## 7.11 Exit / Downgrade Logic

退出或降级逻辑重点看：

1. 回收边界后是否真的延续拒绝
2. 是否重新被突破方向夺回
3. 是否已经从失败突破转成真正接受

常见降级路径：

`failed_breakout_rejection -> mere_test_only`

常见接管路径：

`failed_breakout_rejection -> breakout_acceptance`

---

## 7.12 Common False Positive

常见误判：

1. 看见扫一下就立刻做反向
2. 把正常回踩误判成失败突破
3. 没等回收确认就提前赌反转
4. 忽略突破方向后来重新站稳

---

## 7.13 Review Questions

复盘时重点问：

1. 我当时看到的是“失败突破”，还是只是“突破后的正常测试”？
2. 回收边界是否足够明确？
3. 突破方向后来有没有重新组织？
4. 我是不是太早去反做突破？

---

## 8. 五类事件的简化对照表

| 事件 | 核心问题 | 主要确认 | 主要失效 | 最常见误判 |
|---|---|---|---|---|
| 动能延续 | 会不会重新发动 | 新 initiative、浅回、效率恢复 | 超时不发动、深回旧中心、反向位移 | 把拖延当酝酿 |
| 均值回归 | 是否在回归某个中心 | 向中心移动、中心有吸引、未被单边打断 | 新单边接管、中心失效、回归路径中断 | 把超涨超跌感受当回归 |
| 吸收 -> 反转准备 | 吸收是否正在变成反转条件 | 持续吸收、效率下降、opposite evidence 初现 | 原趋势重启、长期无确认、原方向接受突破 | 把吸收直接当反转 |
| 突破接受 | 突破后是否真正站稳新区域 | 新区域接受、回踩守住、未回旧平衡 | 快速回收、接受失败、假突破接管 | 把穿越一下当接受 |
| 失败突破 / 假突破拒绝 | 扫完后是否未被接受并被打回 | 回收边界、opposite rejection、被困盘显现 | 新区域重新接受、突破方向重组 | 把任何回踩都当假突破 |

---

## 9. 推荐的盘中速记模板

如果你想把五类模板压成极简盘中版本，建议用下面格式：

```text
[主事件]
动能延续 / 均值回归 / 吸收->反转准备 / 突破接受 / 失败突破

[背景]
当前 regime：
关键锚点：

[事件要兑现]
接下来应出现：

[时间窗]
应在多久内出现：

[事件失效]
若什么发生则降级或放弃：

[潜在接管]
最可能接管的下一个事件：
```

---

## 10. 如何继续扩展

目前已经整理了五类核心模板。

后续可继续补充：

1. `流动性扫取 -> 拒绝`
2. `旧平衡中心回访测试`
3. `库存转移 / 控制权切换`
4. `突破后的再测试`
5. `趋势衰竭 -> 平衡形成`

建议扩展原则：

- 一次只新增 1 类
- 新增前先保证旧模板已可稳定使用
- 每一类都必须保留相同字段结构

---

## 11. 一句话结尾

**可交易事件模板的目的，不是让你机械套公式，而是帮助你把“我觉得像”升级成“这个事件若为真，应该如何展开；若不展开，我该如何退出与切换”。**

