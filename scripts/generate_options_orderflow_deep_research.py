from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import fitz


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output" / "pdf"
HTML_PATH = OUTPUT_DIR / "options_orderflow_deep_research_2026-03-29.html"
PDF_PATH = OUTPUT_DIR / "options_orderflow_deep_research_2026-03-29.pdf"


SOURCES = [
    (
        "S1",
        "Cboe - 0DTEs Decoded: Positioning, Trends, and Market Impact (2025-05-02)",
        "https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact",
    ),
    (
        "S2",
        "Cboe - Much Ado About 0DTEs: Evaluating the Market Impact of SPX 0DTE Options (2023-09-08)",
        "https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options",
    ),
    (
        "S3",
        "Cboe - What the VIX and VIX1D Indices Attempt to Measure and How They Differ",
        "https://www.cboe.com/insights/posts/what-the-vix-and-vix-1-d-indices-attempt-to-measure-and-how-they-differ/",
    ),
    ("S4", "Cboe - VIX Term Structure", "https://www.cboe.com/tradable_products/vix/term-structure"),
    (
        "S5",
        "Cboe - U.S. Options Current Market Statistics",
        "https://www.cboe.com/us/options/market_statistics/market/",
    ),
    (
        "S6",
        "Cboe - Historical Data / SPX Put-Call Archives",
        "https://www.cboe.com/us/options/market_statistics/historical_data/",
    ),
    (
        "S7",
        "Cboe - The VIX Index Decomposition (2025-08-01)",
        "https://www.cboe.com/insights/posts/the-vix-index-decomposition-a-heuristic-framework-to-unravel-unexpected-behaviors-in-the-vix-index/",
    ),
    (
        "S8",
        "Cboe - SPX Skew Steepens to 1Y High as Tariff Uncertainty Rises (2026-02-23)",
        "https://www.cboe.com/insights/posts/spx-skew-steepens-to-1-y-high-as-tariff-uncertainty-rises",
    ),
    (
        "S9",
        "Cboe - Cross-Asset Vols Spike on Iran Risk as Oil Surges (2026-03-02)",
        "https://www.cboe.com/insights/posts/cross-asset-vols-spike-on-iran-risk-as-oil-surges",
    ),
    (
        "S10",
        "Cboe - Stagflation Fears Drive Widening Volatility Risk Premium (2026-03-09)",
        "https://www.cboe.com/insights/posts/stagflation-fears-drive-widening-volatility-risk-premium",
    ),
    (
        "S11",
        "Cboe - Spot Down, Vol Down as Investors Monetized Hedges (2026-03-16)",
        "https://www.cboe.com/insights/posts/spot-down-vol-down-as-investors-monetized-hedges",
    ),
    (
        "S12",
        "Options Education / OCC - Options Quotes & Calculators",
        "https://www.optionseducation.org/options-quotes-calculators",
    ),
    ("S13", "Options Education / OCC - Delta", "https://www.optionseducation.org/advancedconcepts/delta"),
    ("S14", "Options Education / OCC - Gamma", "https://www.optionseducation.org/advancedconcepts/gamma"),
    ("S15", "Options Education / OCC - Vega", "https://www.optionseducation.org/advancedconcepts/vega"),
    ("S16", "Options Education / OCC - Theta", "https://www.optionseducation.org/advancedconcepts/theta"),
    (
        "S17",
        "CME Group - Micro E-mini S&P 500 Quotes",
        "https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.quotes.html",
    ),
    (
        "S18",
        "CME Group - Options Gamma: The Greeks",
        "https://www.cmegroup.com/education/courses/option-greeks/options-gamma-the-greeks.html",
    ),
    (
        "S19",
        "AP - How major US stock indexes fared Friday 3/27/2026",
        "https://apnews.com/article/9e3adcd79943cedce8f20b4c779297e3",
    ),
    (
        "S20",
        "Cboe - Delayed Quotes / SPX Quote Table",
        "https://www.cboe.com/delayed_quotes/_spx/quote_table/",
    ),
    (
        "S21",
        "Cboe - Hedgers Capitulate as Bullish Sentiment Rises in Options (2025-11-03)",
        "https://www.cboe.com/insights/posts/hedgers-capitulate-as-bullish-sentiment-rises-in-options/",
    ),
    (
        "S22",
        "Cboe - Equity Volatility Finds a Floor Ahead of Key Trade Catalysts (2025-07-07)",
        "https://www.cboe.com/insights/posts/equity-volatility-finds-a-floor-ahead-of-key-trade-catalysts/",
    ),
    (
        "S23",
        "Cboe - A Fresh Look at Short-Dated Options and 0DTE SPX (2025-04-01)",
        "https://www.cboe.com/insights/posts/a-fresh-look-at-short-dated-options-and-0-dte-spx",
    ),
    (
        "S24",
        "Cboe - A Tale of Two Markets: SPX Options’ Expanding Lead vs. Eminis",
        "https://www.cboe.com/insights/posts/a-tale-of-two-markets-spx-options-expanding-lead-vs-eminis-/",
    ),
    (
        "S25",
        "Cboe - VIX Call Demand Near Record High Ahead of FOMC (2025-01-27)",
        "https://www.cboe.com/insights/posts/vix-call-demand-near-record-high-ahead-of-fomc-live",
    ),
    (
        "S26",
        "CME Group - Submitting a Futures Order",
        "https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/submitting-a-futures-order",
    ),
    (
        "S27",
        "CME Group - Hedging Weekend Event Risk with Monday Weekly Treasury Options",
        "https://www.cmegroup.com/education/articles-and-reports/hedging-weekend-event-risk",
    ),
    (
        "S28",
        "Cboe - Index Options Benefits: Cash Settlement",
        "https://www.cboe.com/tradable_products/index-options-benefits-cash-settlement/",
    ),
    (
        "S29",
        "Cboe - SPX Intraday Volatility Highest Since 2008 on Tariff U-Turn",
        "https://www.cboe.com/insights/posts/spx-intraday-volatility-highest-since-2008-on-tariff-u-turn",
    ),
    (
        "S30",
        "Cboe - SPX Option Volumes Hit Record High as Volatility Picks Up",
        "https://www.cboe.com/insights/posts/spx-option-volumes-hit-record-high-as-volatility-picks-up/",
    ),
    (
        "S31",
        "Cboe - March Volatility Brings Increased Risk and Opportunity",
        "https://www.cboe.com/insights/posts/march-volatility-brings-increased-risk-and-opportunity",
    ),
]


def source(label: str) -> str:
    return f"<span class='src'>[{label}]</span>"


def glossary_rows() -> str:
    rows = [
        ("Underlying", "标的资产", "期权真正对应的东西，比如 SPX、SPY、ES、MES。", "先分清你分析的是现金指数、ETF 还是期货。订单簿通常看 ES/MES，期权地图通常看 SPX。"),
        ("Strike", "行权价", "期权生效的价格刻度。", "把它当作潜在冲突区，不要当作绝对墙。"),
        ("Expiration / Expiry", "到期日", "期权失去时间价值并结算的日期。", "同一天不同到期的行为完全不同；0DTE 和月度仓位不要混看。"),
        ("ATM / ITM / OTM", "平值 / 实值 / 虚值", "相对当前价格的位置。", "平值附近对短线 gamma 最敏感。"),
        ("Implied Volatility (IV)", "隐含波动率", "市场把未来波动价格化后的结果。", "IV 上升不等于一定下跌，它先表示可选权更贵。"),
        ("Realized Volatility (RV)", "已实现波动率", "过去真实走出来的波动。", "IV 明显高于 RV，说明市场在买保险或买不确定性。"),
        ("Skew", "偏斜", "不同执行价的 IV 不是一条平线。", "股指里通常 put wing 比 call wing 贵，说明左尾更值钱。"),
        ("Smile", "波动率微笑", "不同执行价 IV 的整体形状。", "不要只盯 ATM；尾部往往决定风控。"),
        ("Term Structure", "期限结构", "不同到期日的波动率曲线。", "前端抬升通常意味着近端风险事件或恐慌。"),
        ("Open Interest (OI)", "未平仓量", "尚未了结的合约存量。", "OI 不告诉你多空方向，也不告诉你开仓还是平仓。"),
        ("Volume", "成交量", "当天成交过多少合约。", "高成交不等于高净暴露。"),
        ("Market Maker / Dealer", "做市商 / dealer", "双边报价并管理库存风险的参与者。", "外部只能近似估计他们净头寸，别把估算当真相。"),
        ("Delta", "Delta / 方向敏感度", "标的变动 1 单位时，期权价格理论上变多少。", "交易里它是对冲最直接的一阶暴露。"),
        ("Gamma", "Gamma / Delta 的斜率", "标的变动时 Delta 改变多快。", "Long Gamma 倾向高卖低买；Short Gamma 倾向追涨杀跌。"),
        ("Theta", "Theta / 时间衰减", "时间经过 1 天，期权理论上损失多少价值。", "临近到期时最敏感，且不是线性衰减。"),
        ("Vega", "Vega / 波动率敏感度", "IV 变化 1% 时，期权理论价值变化多少。", "长天期 Vega 更大。"),
        ("Vanna", "Vanna / vol 改变对 Delta 的影响", "IV 变化会改变 Delta，因此影响对冲需求。", "它解释的是 spot 与 vol 同时动时，对冲为何改变。"),
        ("Charm", "Charm / 时间对 Delta 的影响", "时间流逝会改变 Delta。", "午后、尤其 0DTE 平值附近，会明显影响对冲节奏。"),
        ("Pinning", "钉住", "价格靠近某个执行价并被反复吸附。", "尾盘常见，但不能机械预设。"),
        ("Squeeze", "挤压", "某一侧被迫追价，导致单边加速。", "订单簿上常见撤单、扫盘、回踩无承接。"),
        ("Risk Reversal", "风险反转", "常用 25Δ put 和 25Δ call 的相对定价表示偏向。", "看左尾保险需求是否变贵。"),
        ("Contango / Backwardation", "升水 / 倒挂", "期货或波动曲线的正斜率或负斜率。", "VIX 前端倒挂常对应风险厌恶抬升。"),
        ("Dispersion", "离散度", "个股波动与指数波动之间的差。", "个股故事热、指数不一定同步热。"),
        ("Vol-of-Vol / VVIX", "波动率的波动", "VIX 本身的波动率。", "VVIX 上升说明尾部保险和 convexity 更抢手。"),
        ("Absorption", "吸收", "主动单打进去，价格却不再延伸。", "这是 order flow 交易者最重要的反转证据之一。"),
        ("Sweep", "扫盘", "市价单连续跨多个价位成交。", "配合撤单时，突破更可信。"),
        ("Iceberg", "冰山单", "看得见的挂单不大，但持续补出来。", "重在成交后还能补，而不是屏幕看起来厚。"),
        ("Pulling / Stacking", "撤单 / 叠单", "挂单撤走或继续加码挂出。", "突破时更重视 pulling；防守时更重视 stacking。"),
        ("Acceptance / Rejection", "接受 / 拒绝", "市场是否愿意在新价格继续成交。", "价格摸到位不重要，能否被接受最重要。"),
    ]
    html = []
    for eng, zh, meaning, use in rows:
        html.append("<tr>" f"<td>{eng}</td><td>{zh}</td><td>{meaning}</td><td>{use}</td>" "</tr>")
    return "".join(html)


def data_source_rows() -> str:
    rows = [
        (
            "Cboe SPX Delayed Quote Table",
            "SPX 延迟期权链、执行价、到期日、OI、报价",
            "手工输入 ticker，看近端到期、ATM 附近、极端 OI 聚集的 strike。",
            "该页面明确禁止自动抽取表格；应人工查看。 " + source("S20"),
        ),
        (
            "Cboe VIX Term Structure",
            "9 天到 1 年的 S&P 500 波动期限结构",
            "盘前先看前端是否抬升、曲线是平、陡还是倒挂。",
            "用来区分低波动稳态、事件稳态和恐慌稳态。 " + source("S4"),
        ),
        (
            "Cboe Market Statistics",
            "总量、指数/股票期权 Put/Call、分时成交",
            "看当天防守需求是否显著抬升。",
            "2026-03-27 指数期权 P/C 比到 15:15 CT 为 1.13，总匹配量 76.4M。 " + source("S5"),
        ),
        (
            "Cboe Historical Data",
            "历史 Put/Call、SPX 比率归档",
            "做背景分位和 regime 对比。",
            "把今天的数据放回历史区间里看，而不是只盯绝对值。 " + source("S6"),
        ),
        (
            "Cboe VIX Decomposition",
            "把 VIX 变化拆成可选权需求、偏斜、定位变化等成分",
            "用来判断 Spot Up / Vol Up 或 Spot Down / Vol Down 的性质。",
            "避免把 VIX 简化成恐慌指数。 " + source("S7"),
        ),
        (
            "OIC Options Monitor / Calculator",
            "Greeks、IV、概率、盈亏模拟",
            "给小白做练习、校验 Greeks 和到期结构。",
            "官方教育工具，数据 20 分钟延迟。 " + source("S12"),
        ),
        (
            "CME MES Quotes",
            "MES/ES 价格与成交环境",
            "若你的执行在期货上，期权地图看 SPX，订单流执行看 ES/MES。",
            "MES 合约更适合小仓位练习。 " + source("S17"),
        ),
    ]
    html = []
    for name, info, use_case, remark in rows:
        html.append("<tr>" f"<td>{name}</td><td>{info}</td><td>{use_case}</td><td>{remark}</td>" "</tr>")
    return "".join(html)


def build_html() -> str:
    source_list = "".join(
        f"<li><span class='ref-key'>{key}</span><a href='{url}'>{name}</a></li>"
        for key, name, url in SOURCES
    )
    part1 = f"""
    <section class="cover">
      <div class="pill">深入研究手册 / Research Deep Dive</div>
      <h1>期权、订单流与日内交易</h1>
      <p class="cover-sub">把 SPX 期权结构、VIX 期限结构、订单簿、足迹图与价格行为放进同一个执行框架里</p>
      <div class="cover-grid">
        <article class="hero-card">
          <h3>这份手册重点解决什么</h3>
          <ul>
            <li>把社媒上最常见的 dealer gamma、Vanna、Charm、0DTE 误解逐个拆开。</li>
            <li>把英文术语尽量改写成小白能执行的中文语言。</li>
            <li>把免费官方数据源整合成盘前到尾盘的研究流程。</li>
            <li>把“当前市场状态、未来可能状态、以及对应打法”说清楚，而不是只讲静态概念。</li>
          </ul>
        </article>
        <article class="hero-note">
          <h3>阅读顺序</h3>
          <ul>
            <li>先看第 1 到第 4 节，打牢词汇、Greeks、曲面和数据源。</li>
            <li>再看第 5 到第 8 节，把概念翻译成 intraday playbook。</li>
            <li>最后看第 9 到第 11 节，用当前市场状态与案例训练判断。</li>
          </ul>
        </article>
      </div>
      <div class="meta-strip">
        <div class="meta-box">编制日期：2026-03-29（周日）<br>美国现金股市当日休市，因此“当前市场状态”统一写到 2026-03-27。</div>
        <div class="meta-box">研究边界：本手册用于研究、复盘、执行框架与风险识别，不构成投资建议。</div>
        <div class="meta-box">核心方法：期权地图给上下文，盘口给证据，价格位移给确认。</div>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">1. 定义层</div>
      <h2>中英术语速查表</h2>
      <p class="summary">把英语术语翻成能在盘中真正用上的中文。最重要的不是背定义，而是知道该看什么证据。</p>
      <table>
        <thead>
          <tr>
            <th>English</th>
            <th>中文</th>
            <th>直白含义</th>
            <th>盘中怎么用</th>
          </tr>
        </thead>
        <tbody>
          {glossary_rows()}
        </tbody>
      </table>
    </section>

    <section class="section">
      <div class="eyebrow">2. 结构层</div>
      <h2>把期权语言翻译成订单流语言</h2>
      <p class="summary">期权结构不会替你下单。它负责告诉你“哪里值得高度警惕”，盘口和价格行为才负责给出执行许可。</p>
      <div class="grid-2">
        <article class="card">
          <h3>市场参与者的最简分工</h3>
          <ul>
            <li><b>客户 / customer</b>：买保险、卖波动、做方向、做事件或做系统化再平衡。</li>
            <li><b>做市商 / dealer</b>：提供双边流动性，事后管理 Delta、Gamma、Vega 等库存。</li>
            <li><b>期货主动盘 / initiative flow</b>：在 ES/MES 上用真实成交推动价格离开当前平衡。</li>
            <li><b>被动防守盘 / passive liquidity</b>：在 DOM 上承接、吸收、补单或撤单。</li>
          </ul>
          <p>所以，期权研究不是为了预测“谁一定会买或卖”，而是为了判断：如果价格来到某一区域，哪一类约束更可能主导接下来的流动性反应。</p>
        </article>
        <article class="card">
          <h3>一张最重要的翻译表</h3>
          <ul>
            <li>IV 上升：不是马上跌，而是“可选权更贵，不确定性更贵”。</li>
            <li>Skew 变陡：不是立刻崩，而是“左尾保险需求更贵”。</li>
            <li>前端期限结构抬升：不是马上单边，而是“近期事件或跳空风险被重新定价”。</li>
            <li>客户净买期权：不是 dealer 天然 long gamma，常见地反而更接近 short gamma 一侧。</li>
            <li>大成交量 / 大 OI：不是天然墙，只表示你应该把那里纳入重点观察。</li>
          </ul>
        </article>
      </div>
      <div class="warn">
        <div class="label">常见误区</div>
        把 “Call Wall = 强阻力” 或 “Put Wall = 强支撑” 当作天然定律，是最容易亏钱的简化。真正有用的结论只能写成条件句：如果价格来到这个高关注区，并且出现吸收、拒绝延伸、重新接受旧区间，那这个位置才值得做反转。
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">3. Greeks 层</div>
      <h2>Delta、Gamma、Theta、Vega、Vanna、Charm 的实战翻译</h2>
      <p class="summary">Greeks 不是数学装饰，它们会影响对冲、挂单、回补与尾盘节奏。</p>
      <div class="grid-2">
        <article class="card">
          <h3>Delta 与 Gamma</h3>
          <p><b>Delta</b> 可以先理解为方向敞口的第一层刻度。若一本账 Delta 偏多，做市商更可能卖出期货或卖出相关现货篮子来中和；若 Delta 偏空，则相反 {source('S13')}。</p>
          <p><b>Gamma</b> 是 Delta 对价格变动的斜率。Long Gamma 的对冲更像“高卖低买”；Short Gamma 的对冲更像“涨了再追买，跌了再追卖” {source('S14')} {source('S18')}。</p>
          <p>因此，“高 gamma 会放大市场”是错误句子。正确句子是：<b>高绝对 gamma 会让对冲更敏感；至于波动被抑制还是放大，关键取决于净 gamma 的方向。</b></p>
        </article>
        <article class="card">
          <h3>Theta、Vega、Vanna、Charm</h3>
          <p><b>Theta</b> 是时间衰减，它会在临近到期时加速，而不是线性下降 {source('S16')}。</p>
          <p><b>Vega</b> 是 IV 对期权价格的影响，通常长天期更敏感 {source('S15')}。</p>
          <p><b>Vanna</b> 更适合翻译成“IV 变化会改变 Delta，因此改变对冲需求”。</p>
          <p><b>Charm</b> 更适合翻译成“时间流逝会改变 Delta，因此午后、尤其 0DTE 平值附近，对冲节奏会变快”。</p>
          <p>很多社媒把 Vanna 写成“IV 跌就涨、IV 涨就跌”，这过度简化了方向。方向一定要连同持仓符号、当前位置和时间一起看。</p>
        </article>
      </div>
      <div class="good">
        <div class="label">记忆法</div>
        Long Gamma 更像做市回转，Short Gamma 更像被动追单。Vanna 是“vol 改 Delta”，Charm 是“time 改 Delta”。
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">4. 曲面层</div>
      <h2>Skew、Smile、Term Structure、VIX、VIX1D 如何组合看</h2>
      <p class="summary">不要让一个指标代替整个波动曲面。真正有用的是“位置 + 期限 + 方向”三件事一起看。</p>
      <div class="grid-2">
        <article class="card">
          <h3>VIX 与 VIX1D 的正确时间尺度</h3>
          <p>VIX 是基于 23 到 37 天 SPX 期权构造出来的 30 天预期波动率，不是当天 0DTE 的即时体温计 {source('S3')}。</p>
          <p>VIX1D 试图度量更短、接近“当前交易日”的波动风险，因此更适合配合 intraday 研究 {source('S3')}。</p>
          <p>结论：<b>用 VIX 看宏观风险背景，用前端数据和 0DTE 链看当天的微观波动约束。</b></p>
        </article>
        <article class="card">
          <h3>Skew 与期限结构的联动</h3>
          <ul>
            <li>Skew 变陡：左尾更贵，说明 downside protection 更值钱。</li>
            <li>前端期限结构抬升：市场开始为近端事件或跳空付更高的保险费。</li>
            <li>Skew 变平而 spot 仍弱：可能是对冲被平掉、恐慌没继续加剧。</li>
            <li>Spot Up / Vol Up：不能自动当顶部，可能是 FOMO，也可能是事件前保险与 upside convexity 同时被买。</li>
          </ul>
        </article>
      </div>
      <div class="metric-grid">
        <div class="metric"><div class="k">VIX 的本质</div><div class="v">30 天预期波动</div></div>
        <div class="metric"><div class="k">VIX1D 的本质</div><div class="v">1 天预期波动</div></div>
        <div class="metric"><div class="k">Skew 的本质</div><div class="v">左右尾定价差</div></div>
        <div class="metric"><div class="k">Term Structure 的本质</div><div class="v">不同期限的风险曲线</div></div>
      </div>
      <div class="note">
        <div class="label">研究提示</div>
        Cboe 的 VIX Decomposition 直接指出：VIX 更准确地说是 <b>bid for optionality</b>，也就是“市场愿意为可选权支付多高的价格”，而不是永远等于恐慌 {source('S7')}。
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">5. 数据层</div>
      <h2>免费数据源组合拳</h2>
      <p class="summary">这部分不是让你一次看 20 个页面，而是告诉你什么页面解决什么问题。</p>
      <table>
        <thead>
          <tr>
            <th>数据源</th>
            <th>能看什么</th>
            <th>怎么用</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          {data_source_rows()}
        </tbody>
      </table>
      <div class="warn">
        <div class="label">重要说明</div>
        用户提到的 Cboe SPX delayed quote 页面是很好的免费入口，但其站点条款明确禁止使用程序自动抽取 delayed quote 表格。我在本研究里把它当作“人工查链工具”，不会把它当作可批量抓取的数据接口 {source('S20')}。
      </div>
    </section>
    """
    part2 = f"""
    <section class="section">
      <div class="eyebrow">6. 工作流层</div>
      <h2>盘前到尾盘的实操流程</h2>
      <p class="summary">小白最容易输给信息过载。先固定流程，再逐步增加维度。</p>
      <div class="grid-3">
        <article class="card">
          <h3>盘前</h3>
          <ul>
            <li>打开 SPX 延迟期权链，记下近端最活跃执行价与明显 OI 聚集区。</li>
            <li>打开 VIX term structure，看前端是否明显高于后端。</li>
            <li>看前一日高低点、隔夜高低点、上周高低点、初始关键成交密集区。</li>
            <li>记录是否有 CPI、FOMC、PCE、非农、财报、结算日。</li>
          </ul>
        </article>
        <article class="card">
          <h3>开盘</h3>
          <ul>
            <li>先看市场接受隔夜方向还是回补隔夜方向。</li>
            <li>不要在第一分钟就用“墙位叙事”抢单。</li>
            <li>先等初始平衡区间，观察 ES/MES 是否在关键 strike 对应价格附近被吸收或扫穿。</li>
            <li>确认 Spot 与 Vol 的关系：是 Spot Down / Vol Up，还是 Spot Down / Vol Down？</li>
          </ul>
        </article>
        <article class="card">
          <h3>尾盘</h3>
          <ul>
            <li>看平值附近成交是否集中，盘口是否开始变薄。</li>
            <li>若价格反复回到某个 strike 邻近区，要考虑 pinning；若不断离开且回踩不回，要考虑 squeeze。</li>
            <li>没有明显优势时，尾盘减少频繁试单通常优于强行抓最后一段。</li>
          </ul>
        </article>
      </div>
      <div class="card">
        <h3>一条可执行的盘前清单</h3>
        <table>
          <thead>
            <tr>
              <th>检查项</th>
              <th>你要记录什么</th>
              <th>若异常，交易含义是什么</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>近端执行价聚集</td><td>ATM 上下最活跃 strike、近端 OI 聚集区</td><td>这些是优先观察区，不是自动挂反转单的理由</td></tr>
            <tr><td>VIX 曲线</td><td>前端是否抬升、是否平坦、是否倒挂</td><td>前端抬升时更尊重跳空与突破，不轻易预设回归</td></tr>
            <tr><td>Index Put/Call</td><td>当天分时 P/C 是否迅速升高</td><td>P/C 走高通常说明防守需求与下行保护增强</td></tr>
            <tr><td>Spot 与 Vol</td><td>价格方向与 vol 是否同步</td><td>同步与背离经常决定你做回归还是做延续</td></tr>
            <tr><td>订单簿</td><td>关键区有无吸收、撤单、扫盘、回踩承接</td><td>只有位置没有成交证据，通常不够下单</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">7. 执行层</div>
      <h2>最常用的五个 intraday playbook</h2>
      <p class="summary">下面这几类 setup 都要写成条件句，而不是故事句。</p>
      <div class="scenario">
        <h3>Playbook A: 正 gamma 倾向下的结构反转</h3>
        <p><b>前提</b>：前端 vol 不继续抬升，关键结构位附近出现重复试探。</p>
        <p><b>证据</b>：Footprint 出现大负 Delta，但低点不再延伸；DOM 上 bid 被打后继续补；回收前一根实体或重新站回结构区。</p>
        <p><b>做法</b>：只在拒绝形态成立后做，止损放在拒绝失效处，不放在“我觉得这里很便宜”的位置。</p>
        <p><b>失效</b>：挂单明显撤离、连续 sweep 继续压穿、回踩回不去。</p>
      </div>
      <div class="scenario">
        <h3>Playbook B: 负 gamma 倾向下的突破延续</h3>
        <p><b>前提</b>：前端 vol 高、盘面薄、关键位反复被测试。</p>
        <p><b>证据</b>：关键位附近的被动流动性撤走，主动单连续跨档，破位后回踩时间短且无法回到旧区间。</p>
        <p><b>做法</b>：等破位被接受后跟随，不要在第一下假突破里提前预判。</p>
        <p><b>失效</b>：破位后被快速拉回，且回到旧区间内部持续成交。</p>
      </div>
      <div class="scenario">
        <h3>Playbook C: Spot Down / Vol Down 的反身性回归</h3>
        <p><b>前提</b>：价格继续弱，但 VIX / put skew 没有同步扩张。</p>
        <p><b>证据</b>：下跌有主动卖盘，但价差不再扩、低点延伸效率变差，回收型 K 线增多。</p>
        <p><b>做法</b>：优先做失败下破后的回归，不抢第一个下跌末端。</p>
        <p><b>含义</b>：说明市场没有继续为下行支付更高保险，跌势质量需要打折。</p>
      </div>
      <div class="scenario">
        <h3>Playbook D: Spot Up / Vol Up 的脆弱上行</h3>
        <p><b>前提</b>：价格上涨，但 vol 也在抬升。</p>
        <p><b>证据</b>：上冲过程中盘口追价明显，但每次回踩又承接不足，或者存在事件前保险需求。</p>
        <p><b>做法</b>：不把它自动当顶部，先区分这是 squeeze 还是脆弱反弹。若突破后没有接受，反手做失败才更合理。</p>
      </div>
      <div class="scenario">
        <h3>Playbook E: 尾盘 pin / squeeze 选择题</h3>
        <p><b>Pinning</b>：价格不断回到某个 strike 邻近区，离开后很快被吸回。</p>
        <p><b>Squeeze</b>：价格离开后不愿回来，回踩不深，盘口深度持续变差。</p>
        <p><b>做法</b>：不要用时间点代替证据。下午 3 点后是观察窗口，不是交易信号。</p>
      </div>
      <div class="note">
        <div class="label">一句执行心法</div>
        不是“这里有 Put Wall，所以我要买”，而是“这里有高关注区；如果出现吸收 + 回收 + 不再延伸，我才买。”
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">8. 当前市场状态</div>
      <h2>截至 2026-03-27 的市场状态画像</h2>
      <p class="summary">今天是 2026-03-29（周日），因此这里统一采用截至 2026-03-27 美国收盘附近能够核验的官方/公开数据。</p>
      <div class="metric-grid">
        <div class="metric"><div class="k">S&P 500 收盘</div><div class="v">6,368.85</div></div>
        <div class="metric"><div class="k">单日变化</div><div class="v">-1.7%</div></div>
        <div class="metric"><div class="k">Cboe 总匹配量</div><div class="v">76.43M</div></div>
        <div class="metric"><div class="k">指数期权 P/C</div><div class="v">1.13</div></div>
      </div>
      <p class="small">S&P 500 收盘取自 AP 的 2026-03-27 市场收盘摘要；Cboe 总匹配量与指数期权 Put/Call 比取自 2026-03-27 当日市场统计 {source('S5')} {source('S19')}。</p>
      <div class="card">
        <h3>当前波动状态</h3>
        <p>截至 2026-03-27 15:14 CT，Cboe 的 VIX term structure 页面显示标准 SPX 到期对应的隐含波动期限结构大致为：2026-04-17 到期 31.17、2026-05-15 到期 30.84、2026-06-18 到期 30.46，随后缓慢下行至 2027-01-15 的 28.93 {source('S4')}。</p>
        <p><b>推断</b>：前端明显高于远端，说明市场仍在给近端不确定性付较高保险费，当前并不属于低波动、低防守需求的平静稳态。</p>
      </div>
      <div class="grid-2">
        <article class="good">
          <div class="label">我对当前状态的判断</div>
          <p><b>推断</b>：当前更像“高波动风险溢价仍在、但并非全面失序”的防守型环境。它不是 2020 式恐慌，但也远没回到低波动稳态。</p>
          <p>为什么这样判断：前端波动高、指数期权 Put/Call 比偏高、且 2 月下旬到 3 月中旬的官方材料持续强调 skew 抬升、对冲需求加重以及宏观/地缘不确定性。</p>
        </article>
        <article class="warn">
          <div class="label">交易含义</div>
          <p>这类环境里，反转单可以做，但必须等吸收和拒绝证据；突破单也可以做，但更需要确认“被接受”。两边都不能只靠故事下单。</p>
        </article>
      </div>
    </section>
    """

    part3 = f"""
    <section class="section">
      <div class="eyebrow">9. 状态演化</div>
      <h2>这轮市场是如何发展到现在的</h2>
      <p class="summary">把“过去状态 -> 当前状态”的路径看清楚，未来状态才有判断基础。</p>
      <div class="timeline">
        <div class="timeline-item">
          <div class="timeline-date">2026-02-23</div>
          <p>Cboe 指出 SPX 1M skew 升至 1 年高位，而且不是只发生在前月，而是整个期限结构都偏贵，说明保护需求在向更长时间维度扩散 {source('S8')}。</p>
        </div>
        <div class="timeline-item">
          <div class="timeline-date">2026-03-02</div>
          <p>在伊朗风险与油价冲击下，Cboe 写到 VIX 当天早盘上升近 4 点，而 S&P 期货仅跌约 1.1%，并且强调 skew 今年以来明显变陡，接近 2024 年 8 月日元套息平仓时的极端水平 {source('S9')}。</p>
        </div>
        <div class="timeline-item">
          <div class="timeline-date">2026-03-09</div>
          <p>Cboe 记录到：SPX 上周仅跌约 2%，但 VIX 却跳升近 10 点至 29；其解释不是单纯 realized vol 抬升，而是可选权需求抬价与“卖 call 买 put”式周末对冲一起推高了 VIX {source('S10')}。</p>
        </div>
        <div class="timeline-item">
          <div class="timeline-date">2026-03-16</div>
          <p>随后又出现一个很重要的 regime clue：Spot Down / Vol Down。SPX 跌 1.6%，但 VIX 反而周跌 2.3 点到 27，put skew 也从 1 年高位快速回落到 35 分位，说明有一部分对冲被兑现了 {source('S11')}。</p>
        </div>
        <div class="timeline-item">
          <div class="timeline-date">2026-03-27</div>
          <p>到 3 月 27 日，前端 VIX 期限结构仍高于远端，指数期权 Put/Call 比收在 1.13，总匹配量 76.4M。说明“市场虽有过对冲平仓，但近端风险溢价仍未明显回归常态” {source('S4')} {source('S5')}。</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">10. 未来情景</div>
      <h2>未来状态不要预测点位，要预测状态迁移</h2>
      <p class="summary">下面不是预测，而是情景树。你每天只需要判断市场更接近哪一枝。</p>
      <div class="scenario">
        <h3>情景 A：风险溢价压缩 / Vol Compression</h3>
        <p><b>触发征兆</b>：前端期限结构显著回落、skew 继续变平、Spot Down / Vol Down 更常见、订单簿不再轻易抽空。</p>
        <p><b>价格影响</b>：失败突破增多、区间回归和双向来回更常见。</p>
        <p><b>实操</b>：提高对吸收、假突破、二次测试的重视；缩短突破单目标。</p>
      </div>
      <div class="scenario">
        <h3>情景 B：高波动但可交易 / Sticky Elevated Vol</h3>
        <p><b>触发征兆</b>：前端 vol 仍高，但不继续暴冲；市场反复在防守与反弹间切换。</p>
        <p><b>价格影响</b>：日内振幅大、方向切换快，反转与突破都能成立，但必须等待确认。</p>
        <p><b>实操</b>：盘前地图更重要，仓位更轻，执行更慢，看到 acceptance/rejection 再出手。</p>
      </div>
      <div class="scenario">
        <h3>情景 C：风险再加速 / Stress Re-Expansion</h3>
        <p><b>触发征兆</b>：前端 vol 再次急抬、spot 下跌同时 skew 再变陡、盘口撤单和扫盘明显增多。</p>
        <p><b>价格影响</b>：跳空、延续、单边趋势和 liquidity vacuum 更常见。</p>
        <p><b>实操</b>：减少逆势抄底；若做突破，等回踩无法回收旧区间再跟；若做反转，必须看到更强的吸收证据。</p>
      </div>
      <div class="note">
        <div class="label">重点</div>
        你不需要知道明天涨还是跌。你更需要知道：明天是更像“可压缩的波动”，还是“会自我放大的波动”。
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">11. 案例层</div>
      <h2>三个值得反复读的案例</h2>
      <p class="summary">案例比口号有用，因为案例能告诉你哪些数据能解释，哪些数据不能乱解释。</p>
      <div class="grid-2">
        <article class="card">
          <h3>案例 1：Gross Volume 不等于 Net Risk</h3>
          <p>Cboe 在 2023 年 0DTE 研究里举了一个非常经典的例子：2023-08-15 的 4440 put 一天交易量超过 100k 张，但如果看做市商的净仓位变化，最终只留下约 3k 张净空头，约等于总成交量的 3% {source('S2')}。</p>
          <p><b>实战教训</b>：不要看到某个 strike 巨量成交，就直接认定“dealer 被迫怎样对冲”。Gross volume 很大，不代表净对冲量很大。</p>
        </article>
        <article class="card">
          <h3>案例 2：2026-03-09 的 Spot Down / Vol Up</h3>
          <p>按 Cboe 的拆解，SPX 只跌约 2%，但 VIX 上涨近 10 点到 29，超出“按价格应有的波动反应”。驱动因素包括更高的可选权需求和投资者卖出 calls 为 downside protection 融资 {source('S10')}。</p>
          <p><b>实战教训</b>：当 VIX 的上涨远快于 spot 跌幅时，市场真正交易的不是当下跌了多少，而是“未来出事的概率被重新定价了多少”。这类环境里，反弹更脆，追多必须更挑剔。</p>
        </article>
        <article class="card">
          <h3>案例 3：2026-03-16 的 Spot Down / Vol Down</h3>
          <p>Cboe 记录到 SPX 跌 1.6%，但 VIX 却周跌 2.3 点至 27，而且 put skew 从极高位快速回落，解释为投资者在兑现对冲 {source('S11')}。</p>
          <p><b>实战教训</b>：价格下跌时，若保险费没有继续抬升，说明下跌质量在变差。对 order flow 交易者来说，这正是“等主动卖盘打不动再做回归”的好背景。</p>
        </article>
        <article class="card">
          <h3>补充案例：0DTE 不等于市场操纵杆</h3>
          <p>Cboe 2025 报告指出，SPX 0DTE 交易虽然大，但客户活动相当平衡，净 market maker gamma hedging 在最好情况下也只占 SPX 每日流动性的约 0.2%；而且超过 95% 的客户开仓是有限风险结构 {source('S1')}。</p>
          <p><b>实战教训</b>：不要把所有盘中剧烈波动都甩锅给 0DTE。真正的结论应该是：0DTE 提高了对冲敏感度，但是否足以主导行情，要看当天成交结构是否失衡。</p>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">12. 日志层</div>
      <h2>把研究变成能进步的复盘</h2>
      <p class="summary">如果你不留证据，所有“我觉得今天 dealer 在这样做”的说法，第二天都会变成空话。</p>
      <div class="grid-2">
        <article class="card">
          <h3>每天至少记录这 6 件事</h3>
          <ul>
            <li>盘前你标了哪些高关注 strike / zone。</li>
            <li>VIX / 前端期限结构 / Put-Call 比处于什么状态。</li>
            <li>开盘后最重要的一次 acceptance 或 rejection 发生在哪里。</li>
            <li>你看到的最关键订单簿证据：吸收、扫盘、撤单还是回收。</li>
            <li>你入场时真正依据的条件句是什么。</li>
            <li>交易失效时，是位置错了、节奏错了，还是状态判断错了。</li>
          </ul>
        </article>
        <article class="card">
          <h3>推荐的截图组合</h3>
          <ul>
            <li>一张结构图：SPX / ES 标出前高前低、隔夜区、关键 strike。</li>
            <li>一张 Footprint：展示主动买卖盘是否真的推动价格。</li>
            <li>一张 DOM：展示关键位是吸收、补单，还是撤单、扫穿。</li>
            <li>若有条件，再留一张 VIX 或前端期限结构的当日截图。</li>
          </ul>
        </article>
      </div>
      <div class="good">
        <div class="label">复盘三问</div>
        1. 我在看“位置”还是在看“故事”？<br>
        2. 我在看“成交后是否被接受”，还是只在看挂单厚不厚？<br>
        3. 我的无效点是客观失效点，还是情绪止损点？
      </div>
    </section>
    """

    part4 = f"""
    <section class="section">
      <div class="eyebrow">13. 专项案例库</div>
      <h2>四类必须单独训练的难点场景</h2>
      <p class="summary">这部分不是概念复述，而是把容易误判的场景拆成“背景、证据、打法、无效点”。</p>
      <div class="scenario">
        <h3>案例模块 A：Spot Up / Vol Up 不是自动做空信号</h3>
        <p><b>背景</b>：Cboe 在 2025 年多篇周报里都提示过，市场可以在上涨时同时保留较高波动溢价，尤其是在重大催化剂前、对冲需求未完全撤退、或者 upside convexity 被追逐的时候 {source('S21')} {source('S22')}。</p>
        <p><b>你真正要区分的两种版本</b>：一种是“健康 squeeze”，表现为上涨伴随追价、回踩承接和持续 acceptance；另一种是“脆弱上涨”，表现为价格涨、vol 也涨，但每次上冲后都缺乏后续成交确认。</p>
        <p><b>订单簿证据</b>：若上涨过程中 ask 被持续 lift，回踩后 bid 继续补、低点不再扩张，更像 squeeze；若上冲后 DOM 深度迅速消失、回踩承接差、价格重新掉回原平衡区，更像失败上破。</p>
        <p><b>打法</b>：先做区分，再决定做跟随还是做失败。不要看到 Spot Up / Vol Up 就先入为主地猜顶。</p>
      </div>
      <div class="scenario">
        <h3>案例模块 B：事件日前的 FOMC / CPI 模式</h3>
        <p><b>背景</b>：Cboe 在 2025-01-27 记录到 VIX call demand 接近纪录高位，原因之一就是市场在 FOMC 前买远端 convexity；CME 关于周末事件风险的文章也说明，短期限权经常被用来精确覆盖事件窗口 {source('S25')} {source('S27')}。</p>
        <p><b>事件日前常见特征</b>：前端期限结构抬升、盘口在数据前收缩、价格在消息落地前容易来回洗而不愿真实扩张。</p>
        <p><b>实操</b>：事件前不重仓赌方向，更适合等待“消息后第一轮真实接受”。如果公布后第一下是 sweep，但后续没有 acceptance，经常只是噪音释放；如果 sweep 后持续站稳新区间，才更像 regime 真切换。</p>
        <p><b>无效点</b>：你若在事件前做方向单，必须把“事件后立刻回到旧区间”视作快速减仓或离场信号。</p>
      </div>
      <div class="scenario">
        <h3>案例模块 C：Pinning Into Close 与结算机制</h3>
        <p><b>背景</b>：SPX 周度期权多为 PM 结算，而且现金结算机制意味着接近收盘时，平值附近的定位会被市场高度关注 {source('S28')}。这正是尾盘 pinning 容易被过度讨论的原因。</p>
        <p><b>你要看的不是时间，而是行为</b>：真正的 pinning 是价格多次离开某个执行价附近后又被吸回，且每次离开都缺乏 follow-through；真正的 squeeze 则是价格离开后不愿回来，回踩幅度浅，且盘口深度变薄。</p>
        <p><b>DOM / Footprint 观察</b>：pinning 更像“离开无接受，回到有成交”；squeeze 更像“离开有接受，回踩无承接”。</p>
        <p><b>打法</b>：尾盘优先做“是否被接受”的判断，而不是提前押时间点。下午 3 点不是信号，只是你必须提高警惕的观察窗口。</p>
      </div>
      <div class="scenario">
        <h3>案例模块 D：SPX 期权链 + ES/MES 订单簿联动</h3>
        <p><b>背景</b>：Cboe 强调 SPX 期权已经成为指数波动表达的核心场所，而 CME 的 ES/MES 则提供了更直接的盘中执行和深度观察窗口 {source('S24')} {source('S26')}。</p>
        <p><b>一个可执行的联动框架</b>：</p>
        <p>1. 盘前在 SPX 链上标记 ATM 附近最活跃 strike、近端 OI 聚集区和前一日最敏感位置。</p>
        <p>2. 把这些 strike 映射成 ES/MES 的价格区，而不是幻想它们是单点精度。</p>
        <p>3. 盘中只在这些区附近提高注意力，观察 ES/MES 的 DOM 是否出现吸收、撤单、扫盘、回收。</p>
        <p>4. 若价格到了区里没有任何特殊成交证据，就当普通价格看待，不交易。</p>
        <p><b>核心思想</b>：SPX 期权链负责告诉你“哪里值得看”，ES/MES 盘口负责告诉你“现在能不能做”。</p>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">14. 逐步拆解</div>
      <h2>一个标准的 ES DOM + SPX 期权链研究模板</h2>
      <p class="summary">这部分给你一个可复制的模板。以后每天只要照表打勾，就能逐步把案例库做厚。</p>
      <table>
        <thead>
          <tr>
            <th>步骤</th>
            <th>要做什么</th>
            <th>看什么证据</th>
            <th>常见错误</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>1. 画地图</td><td>从 SPX 链上记录近端到期、ATM、极端 OI 聚集区、前一日关键结构位</td><td>高关注 strike 是否密集，是否靠近隔夜高低点或前日高低点</td><td>把 OI 直接当支撑阻力，不画区只画线</td></tr>
          <tr><td>2. 定背景</td><td>看 VIX term structure、Index Put/Call、Spot 与 Vol 关系</td><td>前端 vol 是否抬升，P/C 是否显著偏高，Spot 与 Vol 是同步还是背离</td><td>只看一个 VIX 数字，不看期限和结构</td></tr>
          <tr><td>3. 等触发</td><td>等 ES/MES 触碰高关注区</td><td>是否出现 sweep、pulling、stacking、absorption、failed auction</td><td>没到关键区就到处试单</td></tr>
          <tr><td>4. 看接受</td><td>判断突破或反转后是否被市场接受</td><td>离开后是否回不来，回踩是否被承接，还是立刻回到旧区间</td><td>只看第一下冲击，不看后续成交</td></tr>
          <tr><td>5. 做记录</td><td>保存结构图、Footprint、DOM 截图，写下条件句</td><td>你入场时真正的证据是否能被事后复盘复现</td><td>只记结论，不记证据</td></tr>
        </tbody>
      </table>
      <div class="good">
        <div class="label">模板句式</div>
        “若价格进入 `某 strike 映射区`，并出现 `吸收/扫盘/回收/接受`，则执行 `反转/突破`；若随后 `回到旧区间/失去承接`，则视为无效。”
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">15. 训练建议</div>
      <h2>把这份案例库变成你的周复盘作业</h2>
      <p class="summary">不要试图一天吸收全部。最有效的方法，是一周只专项训练一种场景。</p>
      <div class="grid-2">
        <article class="card">
          <h3>四周训练法</h3>
          <ul>
            <li>第 1 周：只做 Spot Down / Vol Down 的回归识别。</li>
            <li>第 2 周：只做 Spot Up / Vol Up 的“健康 squeeze vs 脆弱上涨”区分。</li>
            <li>第 3 周：只做事件日前后第一轮 acceptance / rejection 的复盘。</li>
            <li>第 4 周：只做尾盘 pinning / squeeze 的分类，不急着交易。</li>
          </ul>
        </article>
        <article class="card">
          <h3>每次复盘只问四个问题</h3>
          <ul>
            <li>我看的是 strike 区，还是只看一个价格点？</li>
            <li>我看到的是成交后的 acceptance，还是只看到挂单厚？</li>
            <li>这天是更像压缩波动，还是更像放大波动？</li>
            <li>我把事件、0DTE、dealer flow 哪一项过度神化了？</li>
          </ul>
        </article>
      </div>
      <div class="note">
        <div class="label">最后一句话</div>
        真正的优势不是“我知道 dealer 在想什么”，而是“我知道在什么背景下，什么成交证据值得我下注，什么不值得”。
      </div>
    </section>
    """

    part5 = f"""
    <section class="section">
      <div class="eyebrow">16. 案例手册 v2</div>
      <h2>再补五类高价值场景</h2>
      <p class="summary">下面这五类场景更贴近真实盘中亏钱点。你会发现，最难的不是看懂，而是等证据齐全再做。</p>
      <div class="scenario">
        <h3>场景 E：Spot Down / Vol Up 的防守性下跌</h3>
        <p><b>背景</b>：这是最经典的“价格跌、保险费更贵”的组合。Cboe 在 2026-03-09 的复盘里明确写到，SPX 只跌约 2%，但 VIX 却跳升近 10 点到 29，说明市场交易的不是已经跌了多少，而是未来继续出问题的概率有多高 {source('S10')}。</p>
        <p><b>盘口特征</b>：下跌过程更容易伴随 DOM 撤单、价差扩大、主动卖盘跨档，回踩承接弱，旧支撑被跌破后不愿立刻收回。</p>
        <p><b>打法</b>：优先做延续，不急着抄底。若要做反转，必须看到更高强度的吸收证据，例如大负 Delta 打不动、连续低点不再扩张、以及回收前一段破位区域。</p>
        <p><b>无效点</b>：若下跌后 VIX 不再继续走高，且价格开始频繁收回破位区域，这时要考虑从“防守性下跌”切换到“衰竭式下跌”。</p>
      </div>
      <div class="scenario">
        <h3>场景 F：Gap Day / 跳空日</h3>
        <p><b>背景</b>：跳空日最容易让人误判，因为开盘前市场已经用 overnight 或消息流做了一部分 price discovery。Cboe 在“tariff u-turn”那篇文章里强调，单日 SPX intraday volatility 可突然飙到极端水平，盘中来回幅度极大 {source('S29')}。</p>
        <p><b>你首先要分的两类</b>：一类是 gap-and-go，开盘后继续接受新价格；另一类是 gap-and-fail，开盘后很快回补跳空并重新进入旧平衡。</p>
        <p><b>证据</b>：gap-and-go 通常表现为开盘后第一轮回踩守住、主动单接力、旧区间难以重新进入；gap-and-fail 则表现为开盘冲击后无 follow-through，且很快回到跳空前区间。</p>
        <p><b>打法</b>：先定义 gap 是否被接受，再谈跟随还是回补。不要把“开很高/很低”误当作天然延续或天然回补理由。</p>
      </div>
      <div class="scenario">
        <h3>场景 G：Trend Day / 趋势日</h3>
        <p><b>背景</b>：趋势日常常伴随波动抬升、期权成交激增和关键位失效。Cboe 在“SPX option volumes hit record high as volatility picks up”这类材料里强调过，当 vol 抬起、成交明显放大时，市场会更愿意离开旧平衡而不是来回均值回归 {source('S30')} {source('S31')}。</p>
        <p><b>盘口特征</b>：单边时段里每次回撤都浅，主动单方向一致，回踩旧高旧低后很快继续走，DOM 深度在趋势方向前方变薄。</p>
        <p><b>打法</b>：趋势日别用震荡日的思路到处抓反转。更合理的是等第一次回踩无法回到旧区间、或等一个失败反抽后顺势跟随。</p>
        <p><b>无效点</b>：如果一段看似趋势的行情开始反复回到中枢，且每次离开都缺乏延续，那它大概率正在从 trend day 退化成双向震荡。</p>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">17. 案例手册 v2</div>
      <h2>Failed Auction 与纽约午盘假突破</h2>
      <p class="summary">这两类场景很像，因为它们都要求你把“摸到位”与“被接受”区分开。</p>
      <div class="scenario">
        <h3>场景 H：Failed Auction / 失败拍卖</h3>
        <p><b>直白定义</b>：市场探到一个新价格，但没有吸引足够的后续成交，于是很快回到原先的价值区。</p>
        <p><b>订单簿证据</b>：你会看到第一下冲击很快，但冲完后无法继续成交，新的高点或低点没有形成持续 acceptance，随后价格回收探测段。</p>
        <p><b>期权结构怎么帮你</b>：若 failed auction 恰好发生在你盘前标记的高关注 strike 邻近区，它的交易价值更高，因为这说明结构位和实时流动性证据开始共振。</p>
        <p><b>打法</b>：不是“到位就反手”，而是“到位后如果 failed auction 成立，我才反手”。</p>
      </div>
      <div class="scenario">
        <h3>场景 I：纽约午盘假突破</h3>
        <p><b>背景</b>：午盘流动性通常更薄，欧洲资金已退场，美国下午的真正方向盘未必已经出现，因此最容易出现“看起来破了，但没有谁愿意继续做”的假突破。</p>
        <p><b>识别方法</b>：突破发生在低成交、低参与度时段；价格虽然过了关键位，但 Footprint 没有持续的主动单推动，DOM 上很快出现回补和对手方吸收，随后价格回到区间内部。</p>
        <p><b>实操</b>：午盘突破要比开盘和尾盘更苛刻地要求 acceptance。若只是轻量突破，不要把它当作趋势日确认。</p>
        <p><b>和 trend day 的区别</b>：趋势日的回踩通常很浅且很快继续；午盘假突破则更常见“突破后站不住、回到中枢、再次试探仍不过”。</p>
      </div>
      <div class="card">
        <h3>五类新增场景对照表</h3>
        <table>
          <thead>
            <tr>
              <th>场景</th>
              <th>最重要的背景信号</th>
              <th>盘口核心证据</th>
              <th>最容易犯的错</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Spot Down / Vol Up</td><td>前端 vol 抬升，保险费继续变贵</td><td>撤单、扫盘、回踩无承接</td><td>过早抄底</td></tr>
            <tr><td>Gap Day</td><td>隔夜已先做 price discovery</td><td>开盘后是否接受新价格</td><td>把 gap 大小当成方向信号</td></tr>
            <tr><td>Trend Day</td><td>成交放大、旧平衡失效</td><td>浅回踩、持续 acceptance</td><td>用震荡思路反复抓顶底</td></tr>
            <tr><td>Failed Auction</td><td>关键位探测失败</td><td>离开无接受、迅速回收</td><td>一摸到位就提前反手</td></tr>
            <tr><td>午盘假突破</td><td>低流动性时段、参与者不足</td><td>破位后站不住、回到区间</td><td>把轻量破位当趋势确认</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">18. 执行提醒</div>
      <h2>把 v2 案例库真正用起来</h2>
      <p class="summary">最好的用法不是背下来，而是每天挑一个场景，只训练它。</p>
      <div class="grid-2">
        <article class="card">
          <h3>建议的专项训练顺序</h3>
          <ul>
            <li>先训练 Failed Auction，因为它最能帮你理解 acceptance / rejection。</li>
            <li>再训练 Gap Day，因为它能帮你戒掉“开盘就预判”的习惯。</li>
            <li>然后训练 Trend Day 与午盘假突破的区分。</li>
            <li>最后训练 Spot Down / Vol Up，因为这类环境的情绪干扰最大。</li>
          </ul>
        </article>
        <article class="card">
          <h3>每天复盘新增四问</h3>
          <ul>
            <li>今天最像的是哪一种场景，而不是我最希望它是哪一种？</li>
            <li>如果我说这是趋势日，证据是 acceptance 还是只是幅度大？</li>
            <li>如果我说这是午盘假突破，证据是站不住还是只是我怕追单？</li>
            <li>如果我说这是 Spot Down / Vol Up，保险费真的在抬升，还是我只是看见价格跌？</li>
          </ul>
        </article>
      </div>
      <div class="warn">
        <div class="label">一句警告</div>
        大多数亏损不是因为你不懂 greek，而是因为你在没有 acceptance 证据时，过早把某个故事当成事实。
      </div>
    </section>
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>期权、订单流与日内交易深入研究手册</title>
  <style>
    @page {{
      size: A4;
      margin: 11mm 11mm 12mm 11mm;
    }}
    :root {{
      --bg: #f4efe7;
      --paper: #fffdf8;
      --ink: #141414;
      --muted: #5d5a55;
      --line: #d7cfbf;
      --accent: #0f5462;
      --accent-soft: #dbeaf0;
      --warn-soft: #f4ddd7;
      --note: #f6efc6;
      --note-line: #ddcd80;
      --good: #e2f0e7;
      --good-line: #9fc2a7;
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
      font-size: 11pt;
      line-height: 1.62;
    }}
    .book {{
      max-width: 188mm;
      margin: 0 auto;
    }}
    h1, h2, h3, h4 {{
      margin: 0;
      line-height: 1.24;
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
    }}
    .cover {{
      min-height: 264mm;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top right, rgba(15, 84, 98, 0.18), transparent 33%),
        linear-gradient(180deg, #fffdf8 0%, #f6f1e8 100%);
      padding: 18mm 15mm 14mm;
      break-after: page;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10pt;
    }}
    .cover h1 {{
      margin-top: 8mm;
      font-size: 26pt;
      max-width: 132mm;
    }}
    .cover-sub {{
      margin-top: 4mm;
      max-width: 132mm;
      color: var(--muted);
      font-size: 13pt;
    }}
    .cover-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 8mm;
      margin-top: 10mm;
    }}
    .hero-card, .hero-note {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.8);
      padding: 5mm;
      break-inside: avoid;
    }}
    .hero-card h3, .hero-note h3 {{
      font-size: 12pt;
      margin-bottom: 2.5mm;
    }}
    .hero-card ul, .hero-note ul {{
      margin: 0;
      padding-left: 5mm;
    }}
    .hero-card li, .hero-note li {{
      margin-bottom: 2mm;
    }}
    .meta-strip {{
      margin-top: 10mm;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 5mm;
    }}
    .meta-box {{
      border-top: 1px solid var(--line);
      padding-top: 3mm;
      color: var(--muted);
      font-size: 9.8pt;
    }}
    .section {{
      margin-bottom: 6mm;
      padding: 7mm;
      border: 1px solid var(--line);
      background: var(--paper);
      break-inside: avoid;
    }}
    .eyebrow {{
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10pt;
      margin-bottom: 2mm;
    }}
    .section h2 {{
      font-size: 17pt;
      margin-bottom: 2mm;
    }}
    .summary {{
      margin: 0 0 4mm;
      color: var(--muted);
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 5mm;
      align-items: start;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 4mm;
      align-items: start;
    }}
    .card {{
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 5mm;
      margin-bottom: 4mm;
      break-inside: avoid;
    }}
    .card h3 {{
      font-size: 12.2pt;
      margin-bottom: 2mm;
    }}
    .card p {{
      margin: 0 0 2.4mm;
    }}
    .card ul {{
      margin: 0;
      padding-left: 5mm;
    }}
    .card li {{
      margin-bottom: 1.8mm;
    }}
    .note {{
      border: 1px solid var(--note-line);
      background: var(--note);
      padding: 4mm;
      margin-bottom: 3mm;
      break-inside: avoid;
    }}
    .good {{
      border: 1px solid var(--good-line);
      background: var(--good);
      padding: 4mm;
      margin-bottom: 3mm;
      break-inside: avoid;
    }}
    .warn {{
      border: 1px solid #d7a896;
      background: var(--warn-soft);
      padding: 4mm;
      margin-bottom: 3mm;
      break-inside: avoid;
    }}
    .label {{
      display: inline-block;
      margin-bottom: 2mm;
      padding: 1px 8px;
      border-radius: 999px;
      background: rgba(0, 0, 0, 0.08);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9.3pt;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 4mm;
      margin-top: 3mm;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 4mm;
      break-inside: avoid;
    }}
    .metric .k {{
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9pt;
      color: var(--muted);
      margin-bottom: 1mm;
    }}
    .metric .v {{
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 13pt;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 2mm;
      font-size: 10pt;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 2.2mm 2.4mm;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: #f0ece4;
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
    }}
    .small {{
      font-size: 9.5pt;
      color: var(--muted);
    }}
    .timeline {{
      border-left: 3px solid var(--accent);
      padding-left: 5mm;
      margin-left: 2mm;
    }}
    .timeline-item {{
      margin-bottom: 4mm;
      break-inside: avoid;
    }}
    .timeline-date {{
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      color: var(--accent);
      margin-bottom: 1mm;
    }}
    .scenario {{
      border: 1px solid var(--line);
      padding: 4mm;
      background: #fff;
      margin-bottom: 4mm;
      break-inside: avoid;
    }}
    .scenario h3 {{
      font-size: 12pt;
      margin-bottom: 2mm;
    }}
    .src {{
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9pt;
    }}
    .refs {{
      border: 1px solid var(--line);
      background: #fffdf8;
      padding: 7mm;
    }}
    .refs h2 {{
      font-size: 16pt;
      margin-bottom: 3mm;
    }}
    .refs ul {{
      margin: 0;
      padding-left: 5mm;
    }}
    .refs li {{
      margin-bottom: 2mm;
      word-break: break-word;
    }}
    .ref-key {{
      display: inline-block;
      min-width: 26px;
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main class="book">
    {part1}
    {part2}
    {part3}
    {part4}
    {part5}
    <section class="refs">
      <h2>参考资料</h2>
      <p class="summary">优先使用官方或半官方来源。若将来要继续扩展，建议先补 VIX1D、VVIX、SKEW、dispersion 的单独案例库。</p>
      <ul>{source_list}</ul>
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
            page.add_redact_annot(fitz.Rect(0, 0, rect.width, 34), fill=(1, 1, 1))
            page.add_redact_annot(
                fitz.Rect(0, rect.height - 48, rect.width, rect.height),
                fill=(1, 1, 1),
            )
            page.apply_redactions()
        cleaned = PDF_PATH.with_name(PDF_PATH.stem + "_clean.pdf")
        doc.save(cleaned)
    finally:
        doc.close()
    cleaned.replace(PDF_PATH)


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
