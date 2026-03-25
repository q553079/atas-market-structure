from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import textwrap

from openai import OpenAI

from atas_market_structure.config import AppConfig
from atas_market_structure.options_context_services import (
    OptionsStrategyContext,
    OptionsStrategyContextArtifacts,
)
from atas_market_structure.spx_gamma_map import GeneratedArtifacts, GammaMapSummary, StrikeMetrics


@dataclass(frozen=True, slots=True)
class OptionsMarkdownReportArtifacts:
    report_path: Path
    prompt_path: Path | None = None


@dataclass(frozen=True, slots=True)
class OptionsAiReportResult:
    provider: str
    model: str
    content: str
    prompt: str


def _format_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def _format_distance(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.2f}"


def _format_large_dollar(value: float | None) -> str:
    if value is None:
        return "-"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.2f}"


def _combined_open_interest(item: StrikeMetrics) -> int:
    return item.call_open_interest + item.put_open_interest


def _combined_volume(item: StrikeMetrics) -> int:
    return item.call_volume + item.put_volume


def _top_strikes(
    summary: GammaMapSummary,
    *,
    sort_key,
    top_n: int = 5,
) -> list[StrikeMetrics]:
    return sorted(summary.strike_metrics, key=sort_key, reverse=True)[:top_n]


def _environment_label_zh(label: str) -> str:
    mapping = {
        "range_harvest": "区间收割",
        "breakout_pressure": "破位压力",
        "downside_hedge_demand": "下行对冲需求",
        "upside_chase": "上行追涨",
        "mixed_environment": "混合环境",
    }
    return mapping.get(label, label)


def _build_prompt_input_payload(summary: GammaMapSummary, context: OptionsStrategyContext) -> dict[str, object]:
    structural = summary.structural_regime
    return {
        "source_file": summary.source_file,
        "quote_time": summary.quote_time,
        "spx_spot": summary.spx_spot,
        "regime": summary.regime,
        "zero_gamma_proxy": summary.zero_gamma_proxy,
        "total_net_gex_1pct": summary.total_net_gex_1pct,
        "support_levels": [
            {
                "strike": item.strike,
                "score": item.score,
                "put_open_interest": item.put_open_interest,
                "put_volume": item.put_volume,
            }
            for item in summary.support_levels
        ],
        "resistance_levels": [
            {
                "strike": item.strike,
                "score": item.score,
                "call_open_interest": item.call_open_interest,
                "call_volume": item.call_volume,
            }
            for item in summary.resistance_levels
        ],
        "front_expiration_metrics": (
            asdict(summary.expiration_metrics[0]) if summary.expiration_metrics else None
        ),
        "structural_regime": asdict(structural) if structural is not None else None,
        "strategy_context": {
            "environment_label": context.environment_label,
            "range_harvest_score": context.range_harvest_score,
            "breakout_pressure_score": context.breakout_pressure_score,
            "downside_hedge_demand_score": context.downside_hedge_demand_score,
            "upside_chase_score": context.upside_chase_score,
            "short_vol_friendliness": context.short_vol_friendliness,
            "long_gamma_friendliness": context.long_gamma_friendliness,
            "context_window_count": context.context_window_count,
            "structural_signals": context.structural_signals,
            "context_signals": context.context_signals,
            "strategy_candidates": [item.to_jsonable() for item in context.strategy_candidates],
        },
    }


def build_options_report_prompt(summary: GammaMapSummary, context: OptionsStrategyContext) -> str:
    payload = _build_prompt_input_payload(summary, context)
    template = textwrap.dedent(
        """
        你是 SPX 期权结构研究员，不是新闻评论员，不是自动交易引擎，也不是在猜测真实 dealer book。

        你的任务是根据给定的 delayed options chain 聚合结果与历史上下文，写一份研究型 Markdown 报告。

        边界要求：
        - 只能使用输入中的数据，不允许补充新闻、宏观事件、订单流、成交明细或主观故事。
        - 必须明确区分“观测事实”“结构推断”“策略环境拟合”“风险与反证”。
        - 不得断言市场一定在做某种策略；只能写“当前环境更像什么 payoff 结构更容易发挥”。
        - 如果 D0 IV、gamma 或 Greeks 看起来异常，必须主动降权并说明原因。
        - 如果历史上下文不足，必须明确写“样本不足”，不能伪造趋势。
        - AI 结论只能作为 review/reporting，不得冒充线上识别结果。

        输出格式：
        ## 1. 核心结论
        ## 2. 关键价位与触发条件
        ## 3. 期限结构、偏斜与 D0 噪声处理
        ## 4. 策略环境拟合
        ## 5. 历史上下文与变化
        ## 6. 风险、反证与下一个观察点

        写作要求：
        - 用中文。
        - 结论要具体到数字和价位。
        - 允许详细，但不要空话和套话。
        - 优先解释“为什么会震荡刷来刷去”或“为什么破位后更容易加速”。
        - 明确指出哪类策略更友好，哪类策略容易被反噬。

        输入数据 JSON：
        """
    ).strip()
    return f"{template}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def generate_ai_options_markdown_report(
    summary: GammaMapSummary,
    context: OptionsStrategyContext,
    *,
    config: AppConfig,
    question: str | None = None,
) -> OptionsAiReportResult:
    if not config.openai_api_key:
        raise ValueError("AI analysis is unavailable because OPENAI_API_KEY is not configured.")

    client = OpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url or None,
        timeout=config.ai_timeout_seconds,
    )
    prompt = build_options_report_prompt(summary, context)
    if question is not None and question.strip():
        prompt = f"{prompt}\n\n补充要求：\n{question.strip()}"

    response = client.chat.completions.create(
        model=config.ai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是严谨的 SPX 期权结构研究员。"
                    "你只能根据给定数据输出中文 Markdown 研究报告。"
                    "不要补充外部信息，不要把环境拟合写成确定事实。"
                    "如果数据不足，必须明确写样本不足。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.25,
        max_tokens=2400,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("AI markdown report returned an empty response.")
    return OptionsAiReportResult(
        provider=config.ai_provider,
        model=config.ai_model,
        content=content,
        prompt=prompt,
    )


def _render_level_lines(summary: GammaMapSummary) -> list[str]:
    lines = []
    for item in summary.support_levels:
        lines.append(
            f"- 支撑参考 `{_format_price(item.strike)}`，支撑代理 `{_format_large_dollar(item.score)}`，"
            f"put OI `{item.put_open_interest:,}`，put volume `{item.put_volume:,}`。"
        )
    for item in summary.resistance_levels:
        lines.append(
            f"- 阻力参考 `{_format_price(item.strike)}`，压力代理 `{_format_large_dollar(item.score)}`，"
            f"call OI `{item.call_open_interest:,}`，call volume `{item.call_volume:,}`。"
        )
    return lines


def _render_top_strike_lines(summary: GammaMapSummary) -> list[str]:
    top_open_interest = _top_strikes(summary, sort_key=_combined_open_interest)
    top_volume = _top_strikes(summary, sort_key=_combined_volume)
    lines = ["- 按总持仓最重的执行价："]
    for item in top_open_interest:
        lines.append(
            f"  - `{_format_price(item.strike)}`，总 OI `{_combined_open_interest(item):,}`，"
            f"call/put OI = `{item.call_open_interest:,}` / `{item.put_open_interest:,}`。"
        )
    lines.append("- 按总成交量最活跃的执行价：")
    for item in top_volume:
        lines.append(
            f"  - `{_format_price(item.strike)}`，总 volume `{_combined_volume(item):,}`，"
            f"call/put volume = `{item.call_volume:,}` / `{item.put_volume:,}`。"
        )
    return lines


def _render_expiration_lines(summary: GammaMapSummary) -> list[str]:
    if not summary.expiration_metrics:
        return ["- 没有可用的到期结构摘要。"]

    lines = []
    for item in summary.expiration_metrics:
        atm_iv = f"{item.atm_iv * 100:.1f}%" if item.atm_iv is not None else "-"
        iv_ratio = f"{item.put_call_iv_ratio_25d:.2f}x" if item.put_call_iv_ratio_25d is not None else "-"
        rr = f"{item.risk_reversal_25d * 100:.1f}%" if item.risk_reversal_25d is not None else "-"
        lines.append(
            f"- `{item.expiration}` (DTE {item.dte})：ATM IV `{atm_iv}`，25Δ put/call `{iv_ratio}`，"
            f"RR25Δ `{rr}`，净 GEX `{_format_large_dollar(item.net_gex_1pct)}`，"
            f"put wall `{_format_price(item.dominant_put_oi_strike)}`，call wall `{_format_price(item.dominant_call_oi_strike)}`。"
        )
    return lines


def _render_strategy_candidates(context: OptionsStrategyContext) -> list[str]:
    if not context.strategy_candidates:
        return ["- 当前没有足够信号给出策略环境候选。"]

    lines = []
    for item in context.strategy_candidates:
        rationale = "；".join(item.rationale)
        caution = "；".join(item.cautions[:1]) if item.cautions else ""
        lines.append(
            f"- `{item.label}`，环境匹配度 `{item.environment_fit}`。"
            f"{item.thesis} 依据：{rationale}"
            + (f" 注意：{caution}" if caution else "")
        )
    return lines


def render_options_markdown_report(
    summary: GammaMapSummary,
    context: OptionsStrategyContext,
    artifacts: GeneratedArtifacts,
    *,
    strategy_context_artifacts: OptionsStrategyContextArtifacts | None = None,
    ai_report: OptionsAiReportResult | None = None,
    include_prompt_appendix: bool = False,
) -> str:
    if ai_report is not None:
        lines = [
            "# SPX 期权结构分析报告",
            "",
            f"- 来源文件：`{summary.source_file}`",
            f"- 报价时间：`{summary.quote_time or '-'}`",
            f"- 图文件：`{artifacts.svg_path}`",
            f"- Gamma JSON：`{artifacts.json_path}`",
            f"- Gamma 文本摘要：`{artifacts.report_path}`",
        ]
        if strategy_context_artifacts is not None:
            lines.extend(
                [
                    f"- 策略上下文 JSON：`{strategy_context_artifacts.json_path}`",
                    f"- 策略上下文文本：`{strategy_context_artifacts.report_path}`",
                ]
            )
        lines.extend(
            [
                "",
                "## 图表",
                "",
                f"![SPX Gamma Map](./{artifacts.svg_path.name})",
                "",
                "## AI 报告元数据",
                "",
                f"- Provider: `{ai_report.provider}`",
                f"- Model: `{ai_report.model}`",
                "",
                ai_report.content.strip(),
                "",
                "## 结构化附件",
                "",
                f"- Gamma SVG：`{artifacts.svg_path}`",
                f"- Gamma JSON：`{artifacts.json_path}`",
                f"- Gamma 文本：`{artifacts.report_path}`",
            ]
        )
        if strategy_context_artifacts is not None:
            lines.extend(
                [
                    f"- Strategy Context JSON：`{strategy_context_artifacts.json_path}`",
                    f"- Strategy Context 文本：`{strategy_context_artifacts.report_path}`",
                ]
            )
        if include_prompt_appendix:
            lines.extend(
                [
                    "",
                    "## AI Prompt 附录",
                    "",
                    "```text",
                    ai_report.prompt,
                    "```",
                ]
            )
        return "\n".join(lines) + "\n"

    structural = summary.structural_regime
    strike_low = min((item.strike for item in summary.strike_metrics), default=None)
    strike_high = max((item.strike for item in summary.strike_metrics), default=None)
    total_rows = sum(item.rows for item in summary.expiration_metrics)
    report_relative_svg = f"./{artifacts.svg_path.name}"

    lines = [
        "# SPX 期权结构分析报告",
        "",
        f"- 来源文件：`{summary.source_file}`",
        f"- 报价时间：`{summary.quote_time or '-'}`",
        f"- 图文件：`{artifacts.svg_path}`",
        f"- Gamma JSON：`{artifacts.json_path}`",
        f"- Gamma 文本摘要：`{artifacts.report_path}`",
    ]
    if strategy_context_artifacts is not None:
        lines.extend(
            [
                f"- 策略上下文 JSON：`{strategy_context_artifacts.json_path}`",
                f"- 策略上下文文本：`{strategy_context_artifacts.report_path}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 图表",
            "",
            f"![SPX Gamma Map]({report_relative_svg})",
            "",
            "## 核心结论",
            "",
            (
                f"- 当前样本是一个典型的“墙内反复拉扯，但一旦破位更容易放大”的混合环境。"
                f"总净 Gamma 约 `{_format_large_dollar(summary.total_net_gex_1pct)}`，"
                f"局部结构仍偏负 Gamma，说明盘面并不是稳定的纯钉仓。"
            ),
            (
                f"- 现价 `{_format_price(summary.spx_spot)}` 仍在 put wall 与 call wall 之间。"
                + (
                    f"当前 put wall 在 `{_format_price(structural.dominant_put_wall.strike)}`，"
                    f"距离现价 `{_format_distance(-structural.dominant_put_wall.distance_from_spot)}`；"
                    f"call wall 在 `{_format_price(structural.dominant_call_wall.strike)}`，"
                    f"距离现价 `{_format_distance(structural.dominant_call_wall.distance_from_spot)}`。"
                    if structural is not None
                    and structural.dominant_put_wall is not None
                    and structural.dominant_call_wall is not None
                    else "墙位信息不足。"
                )
            ),
            (
                f"- Zero Gamma 参考位在 `{_format_price(summary.zero_gamma_proxy)}`，低于现价。"
                "这意味着盘面虽然仍被墙位夹住，但并不处在最舒适的中性区，"
                "更像是带有破位风险的脏震荡。"
            ),
            (
                f"- Gap&Chop 结构分数是 `{structural.gap_chop_score}` / 100。"
                f"这不是“全天单边”或“全天稳态”二选一，而是更接近"
                "“先刷、再选方向；一旦触发关键位，负 Gamma 放大”的节奏。"
                if structural is not None and structural.gap_chop_score is not None
                else "- 当前缺少 Gap&Chop 分数。"
            ),
            (
                f"- 前端 25Δ put/call IV ratio 为 `{structural.front_put_call_iv_ratio_25d:.2f}x`，"
                f"RR25Δ 为 `{structural.front_risk_reversal_25d * 100:.1f}%`。"
                "说明下行尾部保护比上行追涨更贵，市场对 downside risk 的付费意愿更强。"
                if structural is not None
                and structural.front_put_call_iv_ratio_25d is not None
                and structural.front_risk_reversal_25d is not None
                else "- 当前缺少前端 skew 数据。"
            ),
            "",
            "## 数据快照",
            "",
            f"- 覆盖到期日数量：`{len(summary.included_expirations)}`",
            f"- 汇总行数：`{total_rows}`",
            f"- 执行价范围：`{_format_price(strike_low)}` 到 `{_format_price(strike_high)}`",
            f"- 执行价步长：`{summary.strike_step:.2f}`",
            f"- 结构标签：`{summary.regime}`",
            f"- 环境标签：`{_environment_label_zh(context.environment_label)}` (`{context.environment_label}`)",
            f"- Range Harvest / Breakout Pressure：`{context.range_harvest_score}` / `{context.breakout_pressure_score}`",
            f"- Short Vol / Long Gamma Friendliness：`{context.short_vol_friendliness}` / `{context.long_gamma_friendliness}`",
            "",
            "## 关键价位与结构解读",
            "",
            "- 先看支撑、阻力和破位触发，而不是直接把样本翻译成单一方向。",
        ]
    )
    lines.extend(_render_level_lines(summary))
    lines.extend(
        [
            "",
            "- 这组数据更像“区间里刷来刷去，但下沿一旦被打穿更危险”。原因有三点：",
            "  - put wall 更靠近现价，说明下方保护和防守仓位更密集。",
            "  - total/local net gamma 都偏负，说明一旦越过关键位，对冲不一定会自然减震。",
            "  - front skew 明显向 put 侧倾斜，说明市场为下行尾部付费更多。",
            "- 对盘中理解来说，`6550` 到 `6560` 一带更像短线争夺区，`6600` 更像上方远端墙位；",
            "  如果始终留在墙内，容易出现上下刷；如果失守近端 put wall，下行放大更值得警惕。",
            "",
            "## 成交与持仓最集中的执行价",
            "",
        ]
    )
    lines.extend(_render_top_strike_lines(summary))
    lines.extend(
        [
            "",
            "## 期限结构、偏斜与 D0 噪声处理",
            "",
        ]
    )
    lines.extend(_render_expiration_lines(summary))
    lines.extend(
        [
            "",
            "- D0 样本的 ATM IV 明显异常偏高时，不能把它机械理解成真实全天可交易波动率，",
            "  更合理的做法是把它看成“事件/收盘风险 + 数据噪声”的混合层，然后把 D1 到 D7 当成更稳的参考层。",
            "- 如果后面每小时补 6 到 8 次样本，这个期限结构段落会明显更有用，因为可以直接观察前端 skew 和墙位是否持续迁移。",
            "",
            "## 策略环境拟合",
            "",
            (
                f"- 当前环境标签是 `{_environment_label_zh(context.environment_label)}`，"
                f"但分数并不是一边倒：Range Harvest `{context.range_harvest_score}`，"
                f"Breakout Pressure `{context.breakout_pressure_score}`。这意味着它更像混合环境，"
                "而不是无脑做铁鹰或无脑追单边。"
            ),
            "- 更准确的解读是：墙内仍有 theta harvest 质感，墙外则要尊重负 Gamma 放大。",
            "- 所以更合理的表述不是“市场一定在做铁鹰”，而是“当前 payoff 更偏向哪类结构更容易发挥”。",
        ]
    )
    lines.extend(_render_strategy_candidates(context))
    lines.extend(
        [
            "",
            "- 如果你把这组样本翻译成盘感，大概就是：",
            "  - 墙内：更像 iron condor / iron fly 友好的时间价值环境，但仓位不能钝，离 put wall 太近时要更谨慎。",
            "  - 下破：更像 put debit spread 或其他定义风险的下行结构开始变得合理。",
            "  - 上行：当前 upside chase 分数低，不支持把它说成强烈的上冲追涨环境。",
            "",
            "## 历史上下文与下一步增强",
            "",
            f"- 当前上下文窗口数：`{context.context_window_count}`。",
        ]
    )
    if context.context_signals:
        lines.extend([f"- {item}" for item in context.context_signals])
    else:
        lines.append("- 历史上下文不足，所以这次报告更偏“当前快照解读”，还不能写成稳定趋势结论。")
    lines.extend(
        [
            "- 你前面提到每天只下载 6 到 8 次，这个频率是够用的。关键不是每分钟都抓，而是要固定到 UTC 整点或接近整点的桶，然后对比：",
            "  - zero gamma 是否迁移",
            "  - put/call wall 是否迁移",
            "  - 前端 skew 是否继续抬升或回落",
            "  - 近端最活跃 strike 是否轮动",
            "- 如果再接数据库里的合约明细，下一步可以补这些增强：",
            "  - 按 `quote_hour_utc + expiration + strike` 追踪 OI、volume、IV、gamma 的小时变化",
            "  - 区分“新增兴趣”与“旧仓挤压”",
            "  - 看关键执行价是否从单点集中，转成带状迁移",
            "  - 把历史报告串起来，形成连续的期权上下文",
        ]
    )
    if include_prompt_appendix:
        prompt = build_options_report_prompt(summary, context)
        lines.extend(
            [
                "",
                "## Prompt 优化建议",
                "",
                "- 现有仓库里的 AI prompt 目标是“6 行盘中口播”，适合快速提示，不适合研究报告。",
                "- 主要问题：",
                "  - 输出被压成 6 行，无法展开结构推断、策略环境和历史上下文。",
                "  - 没有强制区分“观测事实”和“环境拟合”，容易让读者误以为在断言真实持仓。",
                "  - 没有要求主动降权 D0 噪声层。",
                "  - 没有要求把之前的报告和当前报告串起来。",
                "",
                "建议改成下面这个 prompt 模板：",
                "",
                "```text",
                prompt,
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def write_options_markdown_report(
    summary: GammaMapSummary,
    context: OptionsStrategyContext,
    artifacts: GeneratedArtifacts,
    *,
    strategy_context_artifacts: OptionsStrategyContextArtifacts | None = None,
    ai_report: OptionsAiReportResult | None = None,
    include_prompt_appendix: bool = False,
) -> OptionsMarkdownReportArtifacts:
    report_path = artifacts.report_path.with_name(
        artifacts.report_path.stem.replace("_gamma_map", "_options_report") + ".md"
    )
    report_text = render_options_markdown_report(
        summary,
        context,
        artifacts,
        strategy_context_artifacts=strategy_context_artifacts,
        ai_report=ai_report,
        include_prompt_appendix=include_prompt_appendix,
    )
    report_path.write_text(report_text, encoding="utf-8")
    prompt_path: Path | None = None
    if ai_report is not None:
        prompt_path = report_path.with_name(report_path.stem + "_prompt.txt")
        prompt_path.write_text(ai_report.prompt, encoding="utf-8")
    return OptionsMarkdownReportArtifacts(
        report_path=report_path,
        prompt_path=prompt_path,
    )
