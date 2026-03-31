from __future__ import annotations

from html import escape
from pathlib import Path
import subprocess
import sys

import fitz


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output" / "pdf"
HTML_PATH = OUTPUT_DIR / "orderflow_case_atlas_2026-03-29.html"
PDF_PATH = OUTPUT_DIR / "orderflow_case_atlas_2026-03-29.pdf"


SOURCES = [
    ("S1", "Cboe - Stagflation Fears Drive Widening Volatility Risk Premium", "https://www.cboe.com/insights/posts/stagflation-fears-drive-widening-volatility-risk-premium"),
    ("S2", "Cboe - Spot Down, Vol Down as Investors Monetized Hedges", "https://www.cboe.com/insights/posts/spot-down-vol-down-as-investors-monetized-hedges"),
    ("S3", "Cboe - Hedgers Capitulate as Bullish Sentiment Rises in Options", "https://www.cboe.com/insights/posts/hedgers-capitulate-as-bullish-sentiment-rises-in-options/"),
    ("S4", "Cboe - Equity Volatility Finds a Floor Ahead of Key Trade Catalysts", "https://www.cboe.com/insights/posts/equity-volatility-finds-a-floor-ahead-of-key-trade-catalysts/"),
    ("S5", "Cboe - VIX Call Demand Near Record High Ahead of FOMC", "https://www.cboe.com/insights/posts/vix-call-demand-near-record-high-ahead-of-fomc-live"),
    ("S6", "Cboe - SPX Intraday Volatility Highest Since 2008 on Tariff U-Turn", "https://www.cboe.com/insights/posts/spx-intraday-volatility-highest-since-2008-on-tariff-u-turn"),
    ("S7", "Cboe - SPX Option Volumes Hit Record High as Volatility Picks Up", "https://www.cboe.com/insights/posts/spx-option-volumes-hit-record-high-as-volatility-picks-up/"),
    ("S8", "Cboe - March Volatility Brings Increased Risk and Opportunity", "https://www.cboe.com/insights/posts/march-volatility-brings-increased-risk-and-opportunity"),
    ("S9", "Cboe - Index Options Benefits: Cash Settlement", "https://www.cboe.com/tradable_products/index-options-benefits-cash-settlement/"),
    ("S10", "Cboe - A Tale of Two Markets: SPX Options’ Expanding Lead vs. Eminis", "https://www.cboe.com/insights/posts/a-tale-of-two-markets-spx-options-expanding-lead-vs-eminis-/"),
    ("S11", "CME Group - Submitting a Futures Order", "https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/submitting-a-futures-order"),
]


CASES = [
    {
        "code": "A1",
        "title": "Spot Down / Vol Up",
        "subtitle": "防守性下跌与保险费同步扩张",
        "regime": "延续优先，逆势反转必须等更强吸收",
        "spot_vol": "Spot Down / Vol Up",
        "bands": [{"y0": 120, "y1": 160, "label": "失守后回踩失败区", "color": "#f7dfda"}],
        "points": [(40, 60), (90, 80), (140, 105), (190, 132), (250, 150), (310, 178), (390, 215), (480, 236)],
        "markers": [(250, 150, "pulling"), (395, 214, "sweep"), (175, 128, "failed retest")],
        "chain": ["前端期限结构继续抬升", "put 保险费继续变贵", "下行 strike 更受关注"],
        "dom": ["卖盘跨档更频繁", "bid 撤得快，回补慢", "回踩旧支撑时承接差"],
        "footprint": ["大负 Delta 后仍能继续破低", "回收实体弱", "每轮反弹成交跟不上"],
        "entry": ["只在回踩失败后跟空", "不在第一根急跌末端追最差价", "若要反转，必须看到大卖盘打不动"],
        "invalid": ["VIX 不再抬升", "破位区被快速收回并接受", "低点不再延伸"],
        "drill": ["回放 3 个下跌日，区分“衰竭下跌”和“防守性下跌”", "每次只标记一个回踩失败位"],
        "refs": ["S1"],
    },
    {
        "code": "A2",
        "title": "Spot Down / Vol Down",
        "subtitle": "下跌但保险费未继续扩张",
        "regime": "回归优先，但要等主动卖盘失效",
        "spot_vol": "Spot Down / Vol Down",
        "bands": [{"y0": 180, "y1": 220, "label": "衰竭吸收区", "color": "#dff0e5"}],
        "points": [(40, 70), (95, 92), (140, 118), (200, 150), (250, 196), (290, 212), (340, 210), (395, 190), (470, 155)],
        "markers": [(287, 210, "absorption"), (360, 196, "reclaim"), (205, 150, "delta surge")],
        "chain": ["保险费没有继续抬升", "skew 回落或至少不再陡化", "下跌质量开始打折"],
        "dom": ["低位被打后仍反复补 bid", "新低难以走开", "回到失守区后开始成交"],
        "footprint": ["大负 Delta 不再推动新低", "低点成交大但位移小", "回收前一段实体"],
        "entry": ["做失败下破后的回归", "先等回收，不要猜底", "目标优先看回中枢"],
        "invalid": ["重新跌回吸收区下方并被接受", "卖盘重新扩张且 vol 同步抬升", "回收后没有跟进买盘"],
        "drill": ["找 3 个 Spot Down / Vol Down 日，练习只做回收后的第一笔回归"],
        "refs": ["S2"],
    },
    {
        "code": "A3",
        "title": "Spot Up / Vol Up",
        "subtitle": "健康 squeeze 与脆弱上涨的分界",
        "regime": "先分辨版本，再决定跟随还是做失败",
        "spot_vol": "Spot Up / Vol Up",
        "bands": [{"y0": 75, "y1": 110, "label": "突破接受区", "color": "#dff0e5"}],
        "points": [(40, 210), (100, 196), (155, 180), (220, 142), (275, 118), (330, 100), (390, 78), (470, 68)],
        "markers": [(214, 145, "accept"), (332, 98, "lift"), (118, 196, "retest holds")],
        "chain": ["上涨时波动溢价未退", "可能是事件前保险与上涨 convexity 同时被买", "不能天然当顶部"],
        "dom": ["ask 持续被 lift", "回踩 bid 愿意继续补", "若是脆弱上涨，则上冲后深度很快消失"],
        "footprint": ["主动买盘有连续性", "回踩时卖盘打不下去", "若是假突破则跟进成交不足"],
        "entry": ["只在接受成立时顺势跟随", "若站不住再做失败反手", "不要因为 vol 上涨就先做空"],
        "invalid": ["突破区被跌回并持续成交", "回踩出现连续大正 Delta 但价格不再上行", "上方开始出现重复失败拍卖"],
        "drill": ["回放 2 个 squeeze 日和 2 个失败上破日，对比回踩表现"],
        "refs": ["S3", "S4"],
    },
    {
        "code": "A4",
        "title": "Gap-and-Go",
        "subtitle": "跳空后被新价格接受",
        "regime": "先判定是否接受新价格，不急着猜回补",
        "spot_vol": "Gap Up or Gap Down",
        "bands": [{"y0": 110, "y1": 140, "label": "开盘回踩守住区", "color": "#dff0e5"}],
        "points": [(40, 210), (80, 155), (120, 115), (180, 118), (250, 105), (320, 85), (390, 72), (470, 64)],
        "markers": [(82, 156, "open gap"), (178, 118, "hold"), (324, 85, "continuation")],
        "chain": ["隔夜已先做 price discovery", "关键不是 gap 大小，而是开盘后是否接受", "期权链给你的是高关注区，不是方向命令"],
        "dom": ["开盘第一轮回踩守住", "旧区间难以重新进入", "趋势方向前方深度变薄"],
        "footprint": ["回踩时卖盘打不回旧区", "重新向趋势方向时主动单接力", "开盘后很快出现 follow-through"],
        "entry": ["等第一轮回踩守住再跟", "不追开盘第一根", "若重新回到旧区间就暂停趋势假设"],
        "invalid": ["回到跳空前旧区间并接受", "回踩后没有接力成交", "开盘冲击只是单次 sweep"],
        "drill": ["每周挑一个 gap day，只做“是否接受新价格”的分类"],
        "refs": ["S6"],
    },
    {
        "code": "A5",
        "title": "Gap-and-Fail",
        "subtitle": "跳空但无法维持新平衡",
        "regime": "开盘后若无接受，优先回补逻辑",
        "spot_vol": "Gap Failure",
        "bands": [{"y0": 138, "y1": 170, "label": "回补确认区", "color": "#f7dfda"}],
        "points": [(40, 80), (90, 58), (135, 74), (190, 106), (245, 132), (305, 158), (380, 176), (470, 182)],
        "markers": [(88, 58, "open gap"), (145, 78, "no follow"), (308, 158, "back in range")],
        "chain": ["消息冲击先推开价格", "但后续没有足够参与者承认新价格", "链上高关注区若与旧平衡重合，回补概率更高"],
        "dom": ["开盘冲高/冲低后迅速失去深度优势", "反向流动性补回更快", "回到旧区间后成交增多"],
        "footprint": ["第一波主动单强，但续航不足", "回到旧区间后出现反向主动单接管", "假突破段位移小于成交量"],
        "entry": ["只在回到旧区间后做回补", "不在 gap 还未失效时抢反向", "优先看回中枢和缺口下沿/上沿"],
        "invalid": ["重新站回 gap 方向新区间", "回补后没有接受旧平衡", "事件后新消息再次强化原方向"],
        "drill": ["对比 A4 与 A5：同样的 gap，哪一步开始分叉"],
        "refs": ["S6"],
    },
    {
        "code": "A6",
        "title": "Trend Day",
        "subtitle": "旧平衡失效后的浅回踩单边",
        "regime": "不要用震荡日思路抓来回顶底",
        "spot_vol": "Trend Expansion",
        "bands": [{"y0": 88, "y1": 120, "label": "浅回踩跟随区", "color": "#dff0e5"}],
        "points": [(40, 230), (95, 188), (150, 150), (205, 126), (255, 116), (320, 90), (385, 78), (470, 56)],
        "markers": [(205, 126, "shallow pullback"), (322, 88, "trend add"), (148, 150, "leave range")],
        "chain": ["vol 抬起且成交放大", "旧平衡失效", "更可能离开中枢而非回归"],
        "dom": ["趋势方向前方深度更薄", "每次回踩都浅", "逆向尝试很难持续"],
        "footprint": ["顺势主动单更连续", "回踩时对手盘打不回旧区", "新高/新低后仍愿继续成交"],
        "entry": ["等第一次浅回踩后顺势", "若回到旧区间，先放弃趋势假设", "不要在中段反复摸顶摸底"],
        "invalid": ["价格反复回到中枢", "每次离开都缺乏 acceptance", "回踩深且恢复慢"],
        "drill": ["挑 2 个趋势日与 2 个假趋势日，对比回踩深度与旧区间回收"],
        "refs": ["S7", "S8"],
    },
    {
        "code": "A7",
        "title": "Failed Auction",
        "subtitle": "摸到位但没有被市场接受",
        "regime": "到位不是信号，失败拍卖才是信号",
        "spot_vol": "Acceptance / Rejection",
        "bands": [{"y0": 72, "y1": 108, "label": "探高失败区", "color": "#f7dfda"}],
        "points": [(40, 190), (95, 164), (150, 140), (205, 102), (250, 82), (298, 100), (350, 136), (420, 164), (470, 176)],
        "markers": [(248, 82, "probe"), (297, 100, "reject"), (352, 136, "back in value")],
        "chain": ["若发生在高关注 strike 邻近区，价值更高", "重点不是摸到位，而是新价格没有被接受", "适合结合结构区做失败反手"],
        "dom": ["第一下冲击快", "冲完后成交续航不足", "回到旧区间后成交重新变多"],
        "footprint": ["冲击腿有明显主动单", "但后续没有持续位移", "回收探测段后反向主动单接管"],
        "entry": ["回收探测段后再反手", "先等失败拍卖成立", "目标优先看旧价值区中部"],
        "invalid": ["重新回到探测高低点并被接受", "回收后没有反向跟进成交", "探测段其实是等待再平衡而非失败"],
        "drill": ["只练一种句式：到位后若 failed auction 成立，我才做"],
        "refs": ["S10", "S11"],
    },
    {
        "code": "A8",
        "title": "NY Midday Fake Break",
        "subtitle": "纽约午盘轻量破位与假延续",
        "regime": "午盘突破要比开盘和尾盘更苛刻地要求 acceptance",
        "spot_vol": "Midday Thin Liquidity",
        "bands": [{"y0": 102, "y1": 132, "label": "轻量破位区", "color": "#f7dfda"}],
        "points": [(40, 168), (110, 166), (180, 164), (250, 128), (305, 134), (360, 156), (420, 168), (470, 170)],
        "markers": [(250, 128, "break"), (305, 134, "no accept"), (358, 156, "back inside")],
        "chain": ["午盘流动性更薄", "欧洲退场后参与者不足", "轻量破位更常见但续航更弱"],
        "dom": ["破位发生时挂单薄", "对手方很快补回", "回到区间后成交重新增加"],
        "footprint": ["有第一下主动单", "但没有持续 follow-through", "重新回区后反向主动单更稳"],
        "entry": ["午盘只做被确认的突破", "若站不住，则做回区间的失败单", "避免把轻量破位误当趋势日"],
        "invalid": ["破位后迟迟不回区间", "回踩不深且二次上破成功", "事件驱动在午盘后重新放量"],
        "drill": ["对比 A6 趋势日：趋势日的回踩浅，午盘假突破的回收快"],
        "refs": ["S8"],
    },
    {
        "code": "A9",
        "title": "Pinning vs Squeeze",
        "subtitle": "尾盘到底是被吸回，还是被继续推开",
        "regime": "时间点不是信号，接受与否才是",
        "spot_vol": "Into Close",
        "bands": [{"y0": 112, "y1": 150, "label": "pin 区 / ATM 邻近区", "color": "#f3efcf"}],
        "points": [(40, 130), (95, 118), (145, 132), (205, 116), (255, 138), (315, 120), (375, 142), (470, 124)],
        "markers": [(145, 132, "back"), (256, 138, "back"), (376, 142, "back")],
        "chain": ["接近 PM 结算时平值附近更受关注", "但不能机械预设钉住", "要看离开后是否被拉回"],
        "dom": ["pin 更像离开无接受、回到有成交", "squeeze 更像离开有接受、回踩无承接", "尾盘深度往往整体变薄"],
        "footprint": ["pin 的位移小于成交反复", "squeeze 的位移效率更高", "尾盘尤其要盯回踩后的反应"],
        "entry": ["先判断是 pin 还是 squeeze", "不要用下午 3 点代替证据", "没优势时尾盘少试单"],
        "invalid": ["离开后持续被接受", "回踩不回 ATM 邻近区", "市场开始真实扩张而非回吸"],
        "drill": ["把 3 个尾盘分类：pin、squeeze、无优势"],
        "refs": ["S9"],
    },
    {
        "code": "A10",
        "title": "Event Day First Acceptance",
        "subtitle": "数据或 FOMC 后第一轮真实接受",
        "regime": "消息后一脚不重要，能否留在新区间才重要",
        "spot_vol": "FOMC / CPI / Major Catalyst",
        "bands": [{"y0": 86, "y1": 116, "label": "消息后新接受区", "color": "#dff0e5"}],
        "points": [(40, 170), (120, 168), (180, 170), (240, 82), (285, 98), (340, 92), (395, 88), (470, 84)],
        "markers": [(238, 82, "release"), (286, 98, "hold"), (390, 88, "accept")],
        "chain": ["前端期限结构往往先抬升", "消息落地前容易来回洗", "真正重要的是消息后第一轮接受"],
        "dom": ["公布时 sweep 很常见", "关键看 sweep 后是否还能继续成交", "若马上回旧区，多半只是噪音释放"],
        "footprint": ["消息腿主动单极大", "但只有被接受时位移才延续", "回踩后仍守新区说明 regime 切换更可信"],
        "entry": ["不重仓赌消息前方向", "等第一轮接受后再跟", "若马上回旧区则暂停趋势判断"],
        "invalid": ["消息后迅速回旧区并接受", "第一波过后成交断裂", "价差与深度恢复但价格不留在新区"],
        "drill": ["回放一场数据日：只回答“消息后第一轮是否被接受”"],
        "refs": ["S5"],
    },
]


def source_key(label: str) -> str:
    return f"<span class='src'>[{label}]</span>"


def polyline(points: list[tuple[int, int]]) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def chart_svg(case: dict[str, object]) -> str:
    bands = []
    for band in case["bands"]:
        bands.append(
            f"<rect x='32' y='{band['y0']}' width='455' height='{band['y1'] - band['y0']}' rx='8' fill='{band['color']}' opacity='0.72'/>"
        )
        bands.append(
            f"<text x='40' y='{band['y0'] - 6}' class='band-label'>{escape(band['label'])}</text>"
        )
    markers = []
    for x, y, text in case["markers"]:
        markers.append(f"<circle cx='{x}' cy='{y}' r='5' fill='#0f5462'/>")
        markers.append(f"<text x='{x + 8}' y='{y - 8}' class='marker'>{escape(text)}</text>")
    return f"""
    <svg viewBox="0 0 520 280" class="chart" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="520" height="280" rx="16" fill="#fffdf8"/>
      <g stroke="#e6ddce" stroke-width="1">
        <line x1="32" y1="40" x2="488" y2="40"/>
        <line x1="32" y1="90" x2="488" y2="90"/>
        <line x1="32" y1="140" x2="488" y2="140"/>
        <line x1="32" y1="190" x2="488" y2="190"/>
        <line x1="32" y1="240" x2="488" y2="240"/>
        <line x1="32" y1="40" x2="32" y2="240"/>
        <line x1="122" y1="40" x2="122" y2="240"/>
        <line x1="212" y1="40" x2="212" y2="240"/>
        <line x1="302" y1="40" x2="302" y2="240"/>
        <line x1="392" y1="40" x2="392" y2="240"/>
        <line x1="488" y1="40" x2="488" y2="240"/>
      </g>
      {''.join(bands)}
      <polyline points="{polyline(case['points'])}" fill="none" stroke="#191919" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
      {''.join(markers)}
      <text x="32" y="264" class="axis">Open</text>
      <text x="435" y="264" class="axis">Close</text>
      <text x="32" y="22" class="axis">{escape(case['spot_vol'])}</text>
    </svg>
    """


def bullet_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def case_page(case: dict[str, object]) -> str:
    refs = " ".join(source_key(ref) for ref in case["refs"])
    return f"""
    <section class="case-page">
      <div class="case-head">
        <div class="pill">{case['code']}</div>
        <div class="eyebrow">盘口案例图卡</div>
        <h2>{escape(case['title'])}</h2>
        <p class="summary">{escape(case['subtitle'])}</p>
      </div>
      <div class="case-grid">
        <div class="visual">
          {chart_svg(case)}
          <div class="regime-box">
            <div class="label">交易状态</div>
            <p>{escape(case['regime'])}</p>
          </div>
        </div>
        <div class="info">
          <div class="note-card">
            <div class="label">期权链 / 背景</div>
            <ul>{bullet_list(case['chain'])}</ul>
          </div>
          <div class="note-card">
            <div class="label">DOM 观察</div>
            <ul>{bullet_list(case['dom'])}</ul>
          </div>
          <div class="note-card">
            <div class="label">Footprint 观察</div>
            <ul>{bullet_list(case['footprint'])}</ul>
          </div>
        </div>
      </div>
      <div class="action-grid">
        <div class="action-card good">
          <div class="label">入场条件</div>
          <ul>{bullet_list(case['entry'])}</ul>
        </div>
        <div class="action-card bad">
          <div class="label">失效点</div>
          <ul>{bullet_list(case['invalid'])}</ul>
        </div>
        <div class="action-card">
          <div class="label">复盘训练</div>
          <ul>{bullet_list(case['drill'])}</ul>
        </div>
      </div>
      <div class="case-foot">来源 {refs} · 图为标准化示意，不是历史原始截图</div>
    </section>
    """


def build_html() -> str:
    source_list = "".join(
        f"<li><span class='ref-key'>{k}</span><a href='{u}'>{n}</a></li>" for k, n, u in SOURCES
    )
    pages = "".join(case_page(case) for case in CASES)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>盘口案例图册</title>
  <style>
    @page {{
      size: A4;
      margin: 11mm;
    }}
    :root {{
      --bg: #f4efe7;
      --paper: #fffdf8;
      --ink: #171717;
      --muted: #5c5954;
      --line: #d8cfbe;
      --accent: #0f5462;
      --accent-soft: #dcebef;
      --good: #e4f1e7;
      --good-line: #a4c5aa;
      --bad: #f4dfd9;
      --bad-line: #d0a092;
      --note: #f3efcf;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "SimSun", "Noto Serif CJK SC", serif;
      font-size: 10.8pt;
      line-height: 1.58;
    }}
    .book {{ max-width: 188mm; margin: 0 auto; }}
    h1, h2, h3 {{
      margin: 0;
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      line-height: 1.22;
    }}
    .cover, .guide, .refs, .case-page {{
      border: 1px solid var(--line);
      background: var(--paper);
      margin-bottom: 6mm;
      break-after: page;
    }}
    .cover {{
      min-height: 264mm;
      padding: 18mm 15mm 14mm;
      background:
        radial-gradient(circle at top right, rgba(15, 84, 98, 0.18), transparent 32%),
        linear-gradient(180deg, #fffdf8 0%, #f5f0e8 100%);
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
      font-size: 28pt;
      max-width: 132mm;
    }}
    .sub {{
      margin-top: 4mm;
      color: var(--muted);
      font-size: 13pt;
      max-width: 132mm;
    }}
    .cover-grid, .guide-grid, .action-grid, .case-grid {{
      display: grid;
      gap: 6mm;
      align-items: start;
    }}
    .cover-grid {{ grid-template-columns: 1.15fr 0.85fr; margin-top: 10mm; }}
    .guide-grid {{ grid-template-columns: 1fr 1fr; }}
    .case-grid {{ grid-template-columns: 1.15fr 0.85fr; }}
    .action-grid {{ grid-template-columns: 1fr 1fr 1fr; margin-top: 5mm; }}
    .panel, .note-card, .action-card, .regime-box {{
      border: 1px solid var(--line);
      background: #fff;
      padding: 4.5mm;
      break-inside: avoid;
    }}
    .guide, .refs {{ padding: 7mm; }}
    .guide h2, .refs h2 {{ font-size: 17pt; margin-bottom: 2mm; }}
    .guide p, .refs p, .summary {{ margin: 0 0 4mm; color: var(--muted); }}
    .panel ul, .note-card ul, .action-card ul, .guide ul, .refs ul {{
      margin: 0;
      padding-left: 5mm;
    }}
    .panel li, .note-card li, .action-card li, .guide li, .refs li {{
      margin-bottom: 1.8mm;
    }}
    .case-page {{ padding: 7mm; min-height: 264mm; }}
    .eyebrow {{
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10pt;
      margin-top: 2mm;
    }}
    .case-head h2 {{ font-size: 19pt; margin: 1.2mm 0 1.4mm; }}
    .chart {{ width: 100%; height: auto; display: block; border: 1px solid var(--line); background: #fff; }}
    .axis, .band-label, .marker {{
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 10px;
      fill: #4d4b47;
    }}
    .label {{
      display: inline-block;
      padding: 1px 8px;
      border-radius: 999px;
      background: rgba(0,0,0,0.08);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9.2pt;
      margin-bottom: 2mm;
    }}
    .regime-box {{ margin-top: 4mm; background: var(--note); }}
    .regime-box p {{ margin: 0; }}
    .good {{ background: var(--good); border-color: var(--good-line); }}
    .bad {{ background: var(--bad); border-color: var(--bad-line); }}
    .case-foot {{
      margin-top: 4mm;
      color: var(--muted);
      font-size: 9.4pt;
      border-top: 1px solid var(--line);
      padding-top: 2.5mm;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 10pt;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 2.2mm 2.4mm;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #f0ece4; font-family: "SimHei", "Microsoft YaHei", sans-serif; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .ref-key {{
      display: inline-block;
      min-width: 26px;
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
    }}
    .src {{
      color: var(--accent);
      font-family: "SimHei", "Microsoft YaHei", sans-serif;
      font-size: 9pt;
    }}
  </style>
</head>
<body>
  <main class="book">
    <section class="cover">
      <div class="pill">独立图册 / Order Flow Case Atlas</div>
      <h1>盘口案例图册</h1>
      <p class="sub">给 order book、footprint、price action 与 SPX 期权链使用者的一本标准化场景图卡</p>
      <div class="cover-grid">
        <article class="panel">
          <h3>这本图册的用途</h3>
          <ul>
            <li>把最常见的盘中场景变成一页一张的标准化卡片。</li>
            <li>让你复盘时不再只写“感觉像趋势日”，而是对照证据逐项打勾。</li>
            <li>把 SPX 期权链、VIX 背景和 ES/MES 盘口翻译成同一套执行语言。</li>
          </ul>
        </article>
        <article class="panel">
          <h3>重要边界</h3>
          <ul>
            <li>图卡是示意图，不是历史原始截图。</li>
            <li>它解决的是“怎么识别和复盘”，不是“保证怎么赚钱”。</li>
            <li>真正下单前，仍然要看当天的结构背景和实时成交证据。</li>
          </ul>
        </article>
      </div>
    </section>

    <section class="guide">
      <h2>怎么使用这本图册</h2>
      <p>最好的用法不是一次读完，而是每天只拿一张图卡对照当天盘面。盘前先选 1 张最可能出现的场景，盘后再验证你是否真的看到了对应证据。</p>
      <div class="guide-grid">
        <article class="panel">
          <h3>读图顺序</h3>
          <ul>
            <li>先看左侧价格路径示意，判断这张卡在描述哪类位移。</li>
            <li>再看右侧期权链、DOM、Footprint 三组证据。</li>
            <li>最后只看入场条件和失效点，不要先看结论。</li>
          </ul>
        </article>
        <article class="panel">
          <h3>复盘要求</h3>
          <ul>
            <li>每次至少截 3 张图：结构图、DOM、Footprint。</li>
            <li>记录你当时认为它最像哪一张图卡。</li>
            <li>盘后检查：你看到的是 acceptance，还是只是幅度大。</li>
          </ul>
        </article>
      </div>
    </section>

    {pages}

    <section class="refs">
      <h2>参考来源</h2>
      <p>本图册使用官方或半官方材料作为定义与背景来源，图形本身为研究示意图。</p>
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
            page.add_redact_annot(fitz.Rect(0, rect.height - 44, rect.width, rect.height), fill=(1, 1, 1))
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
