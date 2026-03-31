from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output" / "pdf"
HTML_PATH = OUTPUT_DIR / "options_price_action_notes_revised.html"
PDF_PATH = OUTPUT_DIR / "options_price_action_notes_revised.pdf"


SECTIONS = [
    {
        "eyebrow": "0. 读前声明",
        "title": "这份手册在解决什么问题",
        "summary": "把原笔记里最重要的概念错误修正过来，再把期权地图和订单簿、足迹、价格行为放进同一套日内观察框架。",
        "cards": [
            {
                "title": "你要先接受的三个现实",
                "paragraphs": [
                    "第一，期权数据不是预言机。它提供的是头寸约束、对冲压力、风险转移方向，而不是一条必然发生的价格路径。",
                    "第二，所谓做市商行为，只能近似理解为 dealer inventory 在约束下的被动调整。真实市场里还有 CTA、被动资金、宏观事件、公司回购、套利盘和主动投机盘。",
                    "第三，order book 与 price action 依旧是执行层的最后裁判。期权地图回答的是哪里可能有冲突，盘口回答的是此刻谁在真正成交。",
                ],
            },
            {
                "title": "原笔记最需要先纠正的四个点",
                "bullets": [
                    "客户大量买入期权，不代表做市商天然 Long Gamma；交易对手往往更接近净卖方，dealer 可能因此是 Short Gamma。",
                    "Gamma 高不等于一定放大波动。真正决定对冲是否追涨杀跌的是净 gamma 的正负。",
                    "VIX 不是 0DTE 当日流的核心温度计。VIX 主要反映的是约 30 天期限的 SPX 预期波动。",
                    "Call Wall、Put Wall、Zero Gamma Flip 都只能当作条件性区域，不能当作天然有效的墙。",
                ],
            },
        ],
        "notes": [
            {
                "label": "给小白",
                "text": "先把时间尺度分清楚。盘口是秒到分钟，0DTE 是分钟到当天，VIX 是约 30 天。不同尺度的指标不能混着硬解释。",
            },
            {
                "label": "执行原则",
                "text": "先看位置，再看谁主动打单，再看价格是否真的走出来。不要从一个单一 greek 推导整个日内走势。",
            },
            {
                "label": "风险提醒",
                "text": "任何宏观事件日，期权结构的解释力都会下降。FOMC、CPI、非农和大权重财报日都要降杠杆。",
            },
        ],
    },
    {
        "eyebrow": "1. 核心希腊字母",
        "title": "只保留交易真正需要的定义",
        "summary": "不追求学院派完整性，只保留你做指数、期货、订单流执行时最常用的版本。",
        "cards": [
            {
                "title": "Delta 与 Gamma",
                "paragraphs": [
                    "Delta 可以先理解为期权对标的价格变化的一阶敏感度，也是 dealer 最先要对冲的方向暴露。若一本账总 delta 偏多，dealer 往往要卖期货或卖现货篮子做中和；若 delta 偏空，则相反。",
                    "Gamma 是 delta 对标的价格变化的变化率。Long Gamma 的头寸会让你在上涨时卖、下跌时买，更偏向逆向再平衡；Short Gamma 则相反，会让你上涨时追买、下跌时追卖。",
                    "因此，市场是被稳定还是被放大，关键不是 gamma 的大小本身，而是市场关键参与者净 gamma 的方向与分布。",
                ],
            },
            {
                "title": "Vega、Vanna、Charm",
                "paragraphs": [
                    "Vega 反映期权价格对隐含波动率变化的敏感度。它回答的是 vol 变了，期权值变多少。",
                    "Vanna 更适合被理解成 delta 对隐含波动率变化的敏感度，或者 vega 对标的价格变化的敏感度。实盘里它常用来解释 spot 与 vol 同时变化时，dealer 对冲需求为何跟着变。",
                    "Charm 可以理解成 delta 随时间流逝而自然变化。靠近到期日、尤其是 0DTE 附近平值期权时，Charm 和 Gamma 经常一起让盘面在某些时段变得更敏感。",
                ],
            },
            {
                "title": "一个最容易背错的符号关系",
                "bullets": [
                    "多头期权的 gamma 为正，空头期权的 gamma 为负。",
                    "所以，若客户净买期权，dealer 常见地会处在净卖期权的一侧，gamma 方向更容易偏负，而不是偏正。",
                    "真正的净头寸仍然取决于全链条库存、跨期对冲、结构单和历史累积仓位，不能只看单日主动买卖就下结论。",
                ],
            },
        ],
        "notes": [
            {
                "label": "知识注解",
                "text": "很多社媒内容把 Vanna 直接说成 IV 下降就涨、IV 上升就跌，这是偷懒说法。方向一定要连同持仓符号一起看。",
            },
            {
                "label": "盘口连接",
                "text": "若你看到价格上冲、盘口主动买单很多、但每次上冲都被被动卖单吸住，说明光有流入不够，Dealer 相关对冲也未必在同向帮忙。",
            },
            {
                "label": "记忆法",
                "text": "Long Gamma 更像做市回转，Short Gamma 更像被动追单。",
            },
        ],
    },
    {
        "eyebrow": "2. Dealer Gamma 环境",
        "title": "正 gamma 与负 gamma 要怎么真正理解",
        "summary": "把它当作日内微观结构偏好，而不是绝对行情预言。",
        "cards": [
            {
                "title": "正 gamma 环境",
                "paragraphs": [
                    "若关键 dealer 群体整体更接近 Long Gamma，那么标的每次偏离中枢，往往更容易引发逆向对冲。价格涨一点，他们卖一点；价格跌一点，他们买一点。这样做的副作用是波动被吸收，日内更容易表现为回归、震荡和假突破。",
                    "这类环境里，价格对已知结构位的反应更容易表现为试探、停顿、回拉，而不是连续失控地拉开。",
                ],
            },
            {
                "title": "负 gamma 环境",
                "paragraphs": [
                    "若 dealer 更接近 Short Gamma，那么对冲就更像顺势加码。价格往上，他们得继续买；价格往下，他们得继续卖。这样会让关键位置一旦失守，行情扩张速度变快。",
                    "这并不意味着全天必然单边，而是意味着突破一旦被点燃，更不容易被自然对冲立刻压住。",
                ],
            },
            {
                "title": "为什么不能只看一个总 GEX 数字",
                "bullets": [
                    "不同 strike 的 gamma 分布不一样。总量接近零，不代表局部没有强磁吸和强加速区。",
                    "不同到期日的头寸作用时间不同。0DTE、周度、月度和季度仓位混在一起时，盘中的主导权会变化。",
                    "事件前后 IV 和成交结构变化很快，同一个开盘前估算值，中午以后可能已经失效。",
                ],
            },
        ],
        "notes": [
            {
                "label": "新手常错",
                "text": "不要把正 gamma 理解成只会横盘，也不要把负 gamma 理解成只会单边。它们描述的是对冲偏好，不是价格必然形态。",
            },
            {
                "label": "价格行为提示",
                "text": "正 gamma 日更重视失败突破、回到区间、二次测试；负 gamma 日更重视开区间后延续、回踩不深、成交加速。",
            },
            {
                "label": "订单簿提示",
                "text": "真正的负 gamma 扩张，常伴随 best bid 或 best ask 快速撤单、跨档 sweep、成交后价格不回头。",
            },
        ],
    },
    {
        "eyebrow": "3. GEX 地图怎么用",
        "title": "Call Wall、Put Wall、Flip Point 的正确打开方式",
        "summary": "这些位置值得盯，但它们不是天然有效，更不是独立交易系统。",
        "cards": [
            {
                "title": "Call Wall 与 Put Wall",
                "paragraphs": [
                    "最常见的偷懒解释是 Call Wall 等于阻力、Put Wall 等于支撑。这个说法只有在若干条件同时成立时才有可用性，比如 OI 真的是存量、dealer 站在你假设的那一侧、且相关头寸仍有对冲需求。",
                    "更稳妥的用法是把它们视为高关注价格区。价格靠近时，你重点观察是否出现成交放大、盘口厚度变化、主动单被吸收、以及触碰后是否能快速离开。",
                ],
            },
            {
                "title": "Zero Gamma Flip",
                "paragraphs": [
                    "Flip Point 更适合作为环境切换的参考区，而不是一根精确的魔法线。市场可能围绕它反复穿越，因为真实净头寸会随价格、IV、时间和新成交而变化。",
                    "真正重要的是穿越之后，价格有没有被后续成交接受。若破位后立刻回到区间且成交跟不上，说明只是探测；若破位后持续放量、回踩守住，则环境切换的概率更高。",
                ],
            },
            {
                "title": "为什么单看 OI 不够",
                "bullets": [
                    "OI 不能告诉你这笔仓位是买入还是卖出，也不能告诉你它是新开仓还是平仓。",
                    "复杂期权结构会把同一价格附近的 greeks 抵消掉，表面大 OI 可能对应的是净暴露不大。",
                    "到期临近时，同一张图上的作用会迅速变化，上午有效的位置，下午可能就不再有效。",
                ],
            },
        ],
        "notes": [
            {
                "label": "执行模板",
                "text": "先画区，不画线。比如把 5600 这一档上下 5 到 10 个最小跳动看成交易区，再用盘口决定是否做反转或突破。",
            },
            {
                "label": "Order Book 观察",
                "text": "真正的墙不是挂单很多，而是挂单很多且被打之后还补回来。只会显示、不愿成交的挂单，价值有限。",
            },
            {
                "label": "风控提醒",
                "text": "结构位失效时，不要用“墙应该还在”去对抗真实成交。市场先看成交，再看叙事。",
            },
        ],
    },
    {
        "eyebrow": "4. 0DTE、Vanna 与 Charm",
        "title": "它们能解释什么，不能解释什么",
        "summary": "0DTE 很重要，但不能把任何分时波动都归因给它。",
        "cards": [
            {
                "title": "0DTE 不是天然的混乱制造机",
                "paragraphs": [
                    "0DTE 的确让 gamma 与时间衰减都压缩到当天，但这不等于它每天都会主导指数走势。是否主导，要看当天成交量、净头寸分布、事件驱动、以及其他资金是否同时发力。",
                    "比较稳健的说法是：0DTE 提高了盘中 greeks 变化的速度，让一些关键时段和关键 strike 更值得盯，而不是保证全天都出现极端 squeeze。",
                ],
            },
            {
                "title": "Vanna 的正确使用方式",
                "paragraphs": [
                    "Vanna 更适合拿来解释 spot 与 implied vol 同时变化时，delta 对冲需求为什么在加速或减弱。",
                    "若市场上涨且 IV 回落，在某些 dealer 持仓条件下，delta 需求会朝着支持上涨的方向变化，于是出现大家常说的 vanna rally。注意，这里的方向依赖于持仓符号，不是天然固定。",
                ],
            },
            {
                "title": "Charm 的正确使用方式",
                "paragraphs": [
                    "Charm 描述的是时间流逝带来的 delta 漂移。最常见的实际影响，是临近到期的期权在午后对冲需求变化更快，所以某些原本有效的支撑阻力会突然变脆。",
                    "Charm 不是天然的尾盘回落机制。它有时帮助价格回归，有时反而配合趋势延续，必须和当时的 gamma 符号、spot 所在 strike 区域、以及实时成交一起看。",
                ],
            },
        ],
        "notes": [
            {
                "label": "给小白",
                "text": "把 Vanna 理解成 vol 变化影响 delta，把 Charm 理解成时间流逝影响 delta，就够用。",
            },
            {
                "label": "时间窗口",
                "text": "早盘看建仓和开区间，中段看回归是否成立，尾盘看平值附近是否出现钉住或失控扩张。",
            },
            {
                "label": "常见误区",
                "text": "不要把任何下午 3 点后的急动都解释成 0DTE。指数再平衡、现金收盘、ETF 流和新闻也都能触发同类行为。",
            },
        ],
    },
    {
        "eyebrow": "5. VIX 与期限结构",
        "title": "把 VIX 放回它该在的时间尺度",
        "summary": "VIX 很重要，但它回答的是 30 天附近的预期波动，不是当下每一分钟的 0DTE 对冲流。",
        "cards": [
            {
                "title": "VIX 到底是什么",
                "paragraphs": [
                    "VIX 是基于一篮子近月 SPX 期权计算出的约 30 天预期波动率指标。它不是单纯的 put 指数，也不是只反映恐慌，而是对未来一个月左右波动定价的综合快照。",
                    "所以，当你研究 0DTE 和日内节奏时，VIX 可以提供宏观风险背景，但不能代替你去看当日期权链和更短期限的波动率结构。",
                ],
            },
            {
                "title": "Spot 与 Vol 的四种常见组合",
                "bullets": [
                    "Spot 跌、Vol 涨：最经典的风险厌恶组合，趋势做空更容易获得结构配合。",
                    "Spot 涨、Vol 跌：健康上涨中最常见，做多时更容易得到顺风。",
                    "Spot 跌、Vol 不涨：说明恐慌没有同步扩大，跌势质量需要打折扣。",
                    "Spot 涨、Vol 也涨：这是风险提示，不是自动做空信号。要进一步判断是事件前对冲、上冲式 squeeze，还是指数内部结构分化。",
                ],
            },
            {
                "title": "比单看 VIX 更有用的补充项",
                "paragraphs": [
                    "第一，看期限结构。前端波动率是否抬升、曲线是否从 contango 转向 backwardation，往往比一个单独的 VIX 数字更有信息量。",
                    "第二，看当日期权链在 ATM 附近的 IV 变化。若前端 vol 抬得快，而价格又停在关键位置不走，说明市场正在为剧烈波动定价。",
                ],
            },
        ],
        "notes": [
            {
                "label": "知识注解",
                "text": "若你的数据源有 VIX1D 或前端期限结构，研究日内时通常比只看 VIX 更贴近问题本身。",
            },
            {
                "label": "盘口连接",
                "text": "同样是 Spot Up / Vol Up，若盘口一路出现主动买单延续和回踩承接，那更像 squeeze；若每次上冲都缺乏接力，更像脆弱上涨。",
            },
            {
                "label": "风险提醒",
                "text": "事件日前，VIX 上行与指数不跌并不罕见。这种背离不能直接当顶部确认。",
            },
        ],
    },
    {
        "eyebrow": "6. 订单簿与价格行为",
        "title": "把期权地图转成可执行的盘中观察",
        "summary": "地图只负责告诉你哪里重要，真正下单靠的是成交、承接和失败。",
        "cards": [
            {
                "title": "反转场景：结构位吸收",
                "paragraphs": [
                    "典型配置是价格打到 Put Wall 或前低附近，主动卖单明显增加，Footprint 出现大负 delta，但价格不再有效创新低，随后出现回收前一根 K 线实体、DOM 上 bid 反复补单、低点不再延伸。",
                    "这时你不是因为 Put Wall 做多，而是因为 Put Wall 附近出现了吸收和拒绝下行。位置给了你关注理由，成交才给了你执行许可。",
                ],
            },
            {
                "title": "突破场景：墙位失效",
                "paragraphs": [
                    "若价格靠近结构位后，原本的被动挂单突然撤走，主动 sweep 连续跨档，破位后的回踩时间很短且无法回到结构区内，这种才更接近真正的突破。",
                    "负 gamma 倾向下，这类突破更容易得到后续追单配合；正 gamma 倾向下，则更要防第一次破位只是探测。",
                ],
            },
            {
                "title": "价格行为三联确认",
                "bullets": [
                    "位置：是否来到你盘前就标好的高关注区。",
                    "行为：是否出现吸收、扫单、失败拍卖、回收前高前低、单边延续等可重复识别的形态。",
                    "结果：行为之后价格有没有真的走出位移。没有位移的形态，交易价值很低。",
                ],
            },
            {
                "title": "一条非常实用的过滤规则",
                "paragraphs": [
                    "如果你只能看到挂单很多，却看不到成交后价格被推开，那通常还不值得出手。对 order book 交易者而言，真正有用的是成交之后谁控制了后续价格，而不是屏幕上谁挂得更厚。",
                ],
            },
        ],
        "notes": [
            {
                "label": "执行句式",
                "text": "不是“这里有 Put Wall，所以我要买”。而是“这里有 Put Wall，若出现吸收加回收加低点不再延伸，我才买”。",
            },
            {
                "label": "Footprint 提醒",
                "text": "大负 delta 不一定代表要跌，关键是这些主动卖盘打下去后，价格有没有真的走低。",
            },
            {
                "label": "止损设计",
                "text": "反转单的止损应放在拒绝形态失效的地方，不是只放在你主观觉得便宜的位置。",
            },
        ],
    },
    {
        "eyebrow": "7. 日内标准作业流程",
        "title": "给小白的可执行 SOP",
        "summary": "把盘前、开盘、盘中、尾盘拆开，各阶段只做与该阶段匹配的判断。",
        "cards": [
            {
                "title": "盘前准备",
                "bullets": [
                    "记录前一日高低点、隔夜高低点、前周高低点和关键成交密集区。",
                    "标出主要 Call Wall、Put Wall、Flip 区以及当天 ATM 附近最活跃 strike。",
                    "记录当日事件风险：数据、央行、财报、再平衡。",
                    "观察 VIX、前端期限结构和 overnight 是否已有明显风险抬升。",
                ],
            },
            {
                "title": "开盘前 30 分钟到开盘后 15 分钟",
                "paragraphs": [
                    "先看谁在建立开盘方向，不急着证明自己的盘前剧本。开盘前后最重要的是形成初始平衡区间，确认市场是接受隔夜方向，还是要先做相反校正。",
                    "若盘口非常快、新闻还在流、结构位尚未测试，不必急着开第一笔单。开盘最容易被错误叙事诱导。",
                ],
            },
            {
                "title": "中段执行",
                "paragraphs": [
                    "若市场处在更偏正 gamma 的环境，中段更重视回归类交易：回到区间、测试结构位失败、吸收后回拉。",
                    "若市场处在更偏负 gamma 的环境，中段更重视延续类交易：开区间后保持单边、回踩不深、每次回撤都有主动单接力。",
                ],
            },
            {
                "title": "尾盘管理",
                "paragraphs": [
                    "尾盘不要机械地赌钉住，也不要机械地赌 squeeze。你要看平值附近的成交是否正在集中、盘口是否开始失去深度、以及回踩后是否还愿意回到区间。",
                    "若你没有明显优势，尾盘减少频繁试单通常优于为了抓最后一段硬做。",
                ],
            },
        ],
        "notes": [
            {
                "label": "新手优先级",
                "text": "先做好一套稳定的开盘观察和一套稳定的结构位执行，不要一开始就把所有 greek 都塞进决策里。",
            },
            {
                "label": "记录习惯",
                "text": "每天复盘时，截图保留三个画面：结构地图、Footprint、DOM。把入场前后 2 到 3 分钟的证据留存下来。",
            },
            {
                "label": "纪律",
                "text": "开盘前若没有画好关键区和无效点，不交易通常比临场即兴更好。",
            },
        ],
    },
    {
        "eyebrow": "8. 风险管理",
        "title": "不要用期权叙事为亏损找理由",
        "summary": "结构观点可以错，错了就必须退场。风险管理是交易系统，不是情绪安慰。",
        "cards": [
            {
                "title": "两类典型错误",
                "bullets": [
                    "第一，用墙位叙事替代止损。明明结构已经被成交击穿，还执着认为 dealer 会把价格拉回来。",
                    "第二，用宏观叙事替代执行。明明盘口已经转弱，还坚持“VIX 没这么危险”或“这是正常 charm 回落”。",
                ],
            },
            {
                "title": "止损应该放在哪里",
                "paragraphs": [
                    "反转单的止损，放在吸收失败的位置；突破单的止损，放在突破失效的位置。不要只因为某个 strike 名气大，就把止损放得很远。",
                    "宽止损只能配合更小仓位。结构位外的宽止损不是更聪明，只是给市场更多空间，因此必须用更轻的头寸去换。",
                ],
            },
            {
                "title": "什么时候应该直接降频",
                "paragraphs": [
                    "事件前、数据前、午后流动性突然抽空、或你已经连续两次被同一结构模式打脸时，都应该降频。",
                    "真正成熟的 order book 交易者，不是每一段都要抓，而是知道什么时候市场暂时不再提供清晰优势。",
                ],
            },
        ],
        "notes": [
            {
                "label": "底线",
                "text": "市场可以不尊重你的理论，但你必须尊重自己的无效点。",
            },
            {
                "label": "仓位提醒",
                "text": "若你想把结构位放宽，就必须同步缩小仓位；否则你只是把同样的风险包装成更高级的说法。",
            },
            {
                "label": "复盘重点",
                "text": "每次亏损后问三个问题：我错在位置、错在行为判断，还是错在结果确认不够。",
            },
        ],
    },
    {
        "eyebrow": "9. 常见误区",
        "title": "把最容易误导初学者的话一次说清楚",
        "summary": "下面这些句子听起来顺口，但直接拿来交易，代价很高。",
        "cards": [
            {
                "title": "不要再这样说",
                "bullets": [
                    "客户买了很多 call，所以 dealer 一定 Long Gamma。",
                    "Gamma 很高，所以波动一定会变大。",
                    "VIX 涨了，所以指数一定马上见顶。",
                    "Spot Up / Vol Up 一定是做空信号。",
                    "Put Wall 一定撑得住，Call Wall 一定压得住。",
                    "尾盘回落都是 Charm，尾盘拉升都是 Squeeze。",
                    "看到大负 delta 就说明空头强，看到大正 delta 就说明多头强。",
                    "盘口挂单很厚，就说明这里一定有大资金真实防守。",
                ],
            },
            {
                "title": "更稳妥的替代说法",
                "bullets": [
                    "先确认 dealer 可能站在哪一侧，再谈 gamma 方向。",
                    "先确认净 gamma 的方向，再谈它对波动是抑制还是放大。",
                    "先确认时间尺度，再决定 VIX 是否和你的交易问题匹配。",
                    "先确认位置、行为和结果，再决定这是不是一个可执行的 setup。",
                ],
            },
        ],
        "notes": [
            {
                "label": "给小白",
                "text": "如果一句市场解释听起来特别整齐、特别万能，通常就太简单了。",
            },
            {
                "label": "实操心法",
                "text": "交易里最值钱的不是故事，而是条件。把每个故事都改写成“如果 X、且 Y、并且 Z，我才做”。",
            },
            {
                "label": "学习顺序",
                "text": "先学 delta、gamma、结构位和盘口确认，再去学更复杂的 skew、calendar、dispersion。",
            },
        ],
    },
    {
        "eyebrow": "10. 参考与修正摘要",
        "title": "如何继续学，以及这份修正版改了什么",
        "summary": "最后给你一个可持续学习方向，而不是一次性背完所有术语。",
        "cards": [
            {
                "title": "建议的学习顺序",
                "bullets": [
                    "先理解 delta 与 gamma 对对冲行为的影响。",
                    "再学关键结构位为什么只能作为高关注区。",
                    "然后把 Footprint、DOM、价格行为和这些结构位联动起来。",
                    "最后再引入 Vanna、Charm、期限结构和事件日前后的 vol 变化。",
                ],
            },
            {
                "title": "本次修正摘要",
                "bullets": [
                    "把 dealer gamma 的基本符号关系纠正过来。",
                    "把高 gamma 与波动放大的错误因果拆开。",
                    "把 VIX 从 0DTE 即时流解释中剥离，改回 30 天风险背景定位。",
                    "把墙位与 flip point 从绝对结论改成条件性区域。",
                    "新增了面向盘口交易者的执行模板、确认链条和风险控制语言。",
                ],
            },
            {
                "title": "继续阅读",
                "paragraphs": [
                    "官方和半官方材料优先看 Cboe、CME、OIC/Options Education 等基础资料，再回头看市场评论。先建立定义，再吸收叙事，顺序不要反过来。",
                ],
            },
        ],
        "notes": [
            {
                "label": "一句话总结",
                "text": "期权地图负责给你上下文，盘口负责给你证据，价格位移负责给你确认。",
            },
            {
                "label": "复习法",
                "text": "把这份手册当作交易前检查单，不要当作万能剧本。每天只挑一条去复盘，学习效率更高。",
            },
            {
                "label": "适用范围",
                "text": "这套框架更适合指数、股指期货和高流动性 ETF，不适合流动性稀薄、单票事件驱动极强的小票期权。",
            },
        ],
    },
]


REFERENCES = [
    ("CME Group - Options Gamma: The Greeks", "https://www.cmegroup.com/education/courses/option-greeks/options-gamma-the-greeks.html"),
    ("Cboe - What the VIX and VIX1D Indices Attempt to Measure and How They Differ", "https://www.cboe.com/insights/posts/what-the-vix-and-vix-1-d-indices-attempt-to-measure-and-how-they-differ/"),
    ("Cboe - 0DTEs Decoded: Positioning, Trends, and Market Impact", "https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact"),
    ("Options Education - Gamma", "https://www.optionseducation.org/advancedconcepts/gamma"),
]


def build_card(card: dict[str, object]) -> str:
    parts = [f"<article class='card'><h3>{card['title']}</h3>"]
    for paragraph in card.get("paragraphs", []):
        parts.append(f"<p>{paragraph}</p>")
    bullets = card.get("bullets", [])
    if bullets:
        parts.append("<ul>")
        for bullet in bullets:
            parts.append(f"<li>{bullet}</li>")
        parts.append("</ul>")
    parts.append("</article>")
    return "".join(parts)


def build_note(note: dict[str, str]) -> str:
    return (
        "<article class='note-card'>"
        f"<div class='note-label'>{note['label']}</div>"
        f"<p>{note['text']}</p>"
        "</article>"
    )


def build_section(section: dict[str, object]) -> str:
    cards_html = "".join(build_card(card) for card in section["cards"])
    notes_html = "".join(build_note(note) for note in section["notes"])
    return f"""
    <section class="section">
      <div class="section-header">
        <div class="eyebrow">{section['eyebrow']}</div>
        <h2>{section['title']}</h2>
        <p class="summary">{section['summary']}</p>
      </div>
      <div class="section-grid">
        <div class="main-column">{cards_html}</div>
        <aside class="notes-column">
          <div class="notes-sticky">
            <div class="notes-title">知识注解</div>
            {notes_html}
          </div>
        </aside>
      </div>
    </section>
    """


def build_html() -> str:
    sections_html = "".join(build_section(section) for section in SECTIONS)
    references_html = "".join(
        f"<li><a href='{url}'>{label}</a></li>" for label, url in REFERENCES
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>期权、订单簿与价格行为 - 修正版学习手册</title>
  <style>
    @page {{
      size: A4;
      margin: 11mm 11mm 12mm 11mm;
    }}

    :root {{
      --bg: #f6f1e8;
      --paper: #fffdf8;
      --ink: #151515;
      --muted: #5b5751;
      --line: #d9d0c1;
      --accent: #0e4a5a;
      --accent-soft: #d9ebef;
      --warn: #7a2f20;
      --warn-soft: #f4ddd7;
      --note: #f7f0c9;
    }}

    * {{
      box-sizing: border-box;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "SimSun", "Noto Serif CJK SC", serif;
      line-height: 1.6;
      font-size: 11.2pt;
    }}

    body {{
      padding: 0;
    }}

    .book {{
      width: 100%;
      max-width: 188mm;
      margin: 0 auto;
      padding: 0;
    }}

    .cover {{
      min-height: 265mm;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background:
        radial-gradient(circle at top right, rgba(14, 74, 90, 0.18), transparent 32%),
        linear-gradient(180deg, #fffdf8 0%, #f7f3ea 100%);
      border: 1px solid var(--line);
      padding: 18mm 16mm 16mm;
      break-after: page;
    }}

    .cover-tag {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10pt;
      letter-spacing: 0.04em;
    }}

    h1, h2, h3 {{
      margin: 0;
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      line-height: 1.22;
    }}

    .cover h1 {{
      margin-top: 10mm;
      font-size: 26pt;
      max-width: 120mm;
    }}

    .cover-subtitle {{
      margin-top: 6mm;
      max-width: 120mm;
      color: var(--muted);
      font-size: 13pt;
    }}

    .cover-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 10mm;
      align-items: start;
      margin-top: 12mm;
    }}

    .cover-card, .cover-note {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.8);
      padding: 6mm;
      break-inside: avoid;
    }}

    .cover-card h3, .cover-note h3 {{
      margin-bottom: 3mm;
      font-size: 12.5pt;
    }}

    .cover-card ul, .cover-note ul {{
      margin: 0;
      padding-left: 5mm;
    }}

    .meta {{
      display: flex;
      justify-content: space-between;
      gap: 8mm;
      margin-top: 10mm;
      color: var(--muted);
      font-size: 10pt;
      border-top: 1px solid var(--line);
      padding-top: 4mm;
    }}

    .section {{
      background: var(--paper);
      border: 1px solid var(--line);
      margin-bottom: 7mm;
      padding: 7mm 7mm 8mm;
      break-inside: avoid;
    }}

    .section-header {{
      margin-bottom: 5mm;
      border-bottom: 1px solid var(--line);
      padding-bottom: 4mm;
    }}

    .eyebrow {{
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10pt;
      letter-spacing: 0.03em;
      margin-bottom: 2mm;
    }}

    .section-header h2 {{
      font-size: 17pt;
      margin-bottom: 2mm;
    }}

    .summary {{
      margin: 0;
      color: var(--muted);
    }}

    .section-grid {{
      display: grid;
      grid-template-columns: 2.15fr 1fr;
      gap: 6mm;
      align-items: start;
    }}

    .main-column, .notes-column {{
      min-width: 0;
    }}

    .card {{
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 5mm;
      margin-bottom: 4mm;
      break-inside: avoid;
    }}

    .card h3 {{
      font-size: 12pt;
      margin-bottom: 2.5mm;
    }}

    .card p {{
      margin: 0 0 2.8mm;
    }}

    .card p:last-child {{
      margin-bottom: 0;
    }}

    .card ul {{
      margin: 0;
      padding-left: 5mm;
    }}

    .card li {{
      margin-bottom: 2mm;
    }}

    .notes-title {{
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 11pt;
      margin-bottom: 3mm;
    }}

    .note-card {{
      background: var(--note);
      border: 1px solid #ddce82;
      padding: 4mm;
      margin-bottom: 3mm;
      break-inside: avoid;
    }}

    .note-label {{
      display: inline-block;
      background: rgba(21, 21, 21, 0.08);
      padding: 1px 7px;
      border-radius: 999px;
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9.5pt;
      margin-bottom: 2mm;
    }}

    .note-card p {{
      margin: 0;
      font-size: 10.2pt;
      line-height: 1.55;
    }}

    .references {{
      background: #fffdf8;
      border: 1px solid var(--line);
      padding: 7mm;
    }}

    .references h2 {{
      font-size: 16pt;
      margin-bottom: 3mm;
    }}

    .references p {{
      margin-top: 0;
      color: var(--muted);
    }}

    .references ul {{
      margin: 0;
      padding-left: 5mm;
    }}

    .references li {{
      margin-bottom: 2mm;
      word-break: break-word;
    }}

    a {{
      color: var(--accent);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main class="book">
    <section class="cover">
      <div>
        <div class="cover-tag">修正版学习手册</div>
        <h1>期权、订单簿与价格行为</h1>
        <p class="cover-subtitle">面向 order book / footprint / price action 爱好者的入门到执行框架</p>
        <div class="cover-grid">
          <article class="cover-card">
            <h3>这份材料适合谁</h3>
            <ul>
              <li>已经在看盘口、足迹、价格行为，但对期权结构理解不牢的人。</li>
              <li>经常听到 dealer gamma、Vanna、Charm、0DTE，却不知道哪些能交易、哪些只是叙事的人。</li>
              <li>想把期权地图变成盘中执行工具，而不是把它当成神秘指标的人。</li>
            </ul>
          </article>
          <article class="cover-note">
            <h3>使用方法</h3>
            <ul>
              <li>先读正文，建立正确概念。</li>
              <li>再读右侧知识注解，把概念翻译成盘中语言。</li>
              <li>最后把第 6 到第 8 节当作你的交易前检查单。</li>
            </ul>
          </article>
        </div>
      </div>
      <div class="meta">
        <div>基于用户提供原稿重写并纠错</div>
        <div>重点修正：dealer gamma、VIX 时间尺度、墙位误用、Vanna/Charm 方向性</div>
      </div>
    </section>
    {sections_html}
    <section class="references">
      <h2>参考资料</h2>
      <p>以下链接用于校正定义和时间尺度，不替代你自己的实盘观察。</p>
      <ul>{references_html}</ul>
    </section>
  </main>
</body>
</html>
"""


def locate_chrome() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def render_pdf(chrome_path: Path) -> None:
    cmd = [
        str(chrome_path),
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={PDF_PATH}",
        HTML_PATH.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Chrome PDF render failed")


def cleanup_pdf_margins() -> None:
    doc = fitz.open(PDF_PATH)
    try:
        for page in doc:
            rect = page.rect
            page.add_redact_annot(
                fitz.Rect(0, 0, rect.width, 24),
                fill=(1, 1, 1),
            )
            page.add_redact_annot(
                fitz.Rect(0, rect.height - 26, rect.width, rect.height),
                fill=(1, 1, 1),
            )
            page.apply_redactions()
        doc.save(PDF_PATH.with_name(PDF_PATH.stem + "_clean.pdf"))
    finally:
        doc.close()
    PDF_PATH.with_name(PDF_PATH.stem + "_clean.pdf").replace(PDF_PATH)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(build_html(), encoding="utf-8")

    chrome_path = locate_chrome()
    if chrome_path is None:
        print(f"HTML written to {HTML_PATH}")
        print("Chrome/Edge not found; skipped PDF render.")
        return 0

    render_pdf(chrome_path)
    cleanup_pdf_margins()
    print(f"HTML written to {HTML_PATH}")
    print(f"PDF written to {PDF_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
