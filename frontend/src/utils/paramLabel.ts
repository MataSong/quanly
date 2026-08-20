import { t } from "@/locales";

/**
 * 策略参数 key(后端 snake_case)→ i18n key(strategy.* camelCase)映射。
 * 内置策略参数:
 *   dual_ma: fast_period, slow_period, sz
 *   rsi:     period, oversold, overbought, sz
 *   macd:    fast, slow, signal_period, sz
 */
const PARAM_I18N_KEY: Record<string, string> = {
  fast_period: "strategy.fastPeriod",
  slow_period: "strategy.slowPeriod",
  sz: "strategy.sz",
  period: "strategy.period",
  oversold: "strategy.oversold",
  overbought: "strategy.overbought",
  fast: "strategy.fast",
  slow: "strategy.slow",
  signal_period: "strategy.signalPeriod",
};

/**
 * 人类可读的参数标签:已知 key 走 i18n(中/英随 locale),未知 key 原样返回。
 * 复用全局 i18n 实例(与 formatApiError 同惯例),组件里直接 paramLabel(key) 即可。
 */
export function paramLabel(key: string): string {
  const i18nKey = PARAM_I18N_KEY[key];
  return i18nKey ? t(i18nKey) : key;
}

/**
 * 回测/参考业绩指标 key(后端 snake_case)→ backtest.metrics.* i18n。
 * 指标 key: total_return / annualized_return / max_drawdown / sharpe /
 *           win_rate / profit_factor / trade_count
 */
const METRIC_I18N_KEY: Record<string, string> = {
  total_return: "backtest.metrics.totalReturn",
  annualized_return: "backtest.metrics.annualizedReturn",
  max_drawdown: "backtest.metrics.maxDrawdown",
  sharpe: "backtest.metrics.sharpe",
  win_rate: "backtest.metrics.winRate",
  profit_factor: "backtest.metrics.profitFactor",
  trade_count: "backtest.metrics.tradeCount",
};

/** 指标标签:已知 key 走 i18n,未知原样返回。 */
export function metricLabel(key: string): string {
  const i18nKey = METRIC_I18N_KEY[key];
  return i18nKey ? t(i18nKey) : key;
}
