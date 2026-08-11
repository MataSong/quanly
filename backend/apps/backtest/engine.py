"""事件驱动回测引擎:复用策略 on_tick(ctx),逐历史 bar 喂入,模拟成交。

回测 ctx 与实盘 ctx 接口一致(price/symbol/buy/sell/log),但用历史价 + 模拟
成交,不落真实订单表。数据源为真实 OKX 历史 K 线(REST)。
"""


class BacktestError(Exception):
    """回测可预期错误(策略脚本问题、数据缺失等),对外返回可读信息而非 500。"""


def _fetch_candles(symbol, bar, limit):
    """拉取真实历史 K 线(OKX REST,公共接口无需密钥),返回时间升序列表。

    每根为 dict:含 ts/open/high/low/close/vol,与引擎消费格式一致。
    """
    from apps.credentials.models import Env
    from apps.exchanges.factory import AdapterFactory

    adapter = AdapterFactory.create("okx", Env.SIM, credential=None)
    candles = adapter.get_candles(symbol, bar, int(limit))  # 升序 Candle 列表
    return [
        {
            "ts": c.ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "vol": c.vol,
        }
        for c in candles
    ]


class BacktestContext:
    def __init__(self, symbol, initial_capital, fee_rate):
        self.symbol = symbol
        self.interval = 0
        self.cash = float(initial_capital)
        self.position = 0.0  # 持有基础币数量(现货多头模型)
        self.avg_cost = 0.0
        self.fee_rate = float(fee_rate)
        self._cur_price = 0.0
        self.trades = []
        self.logs = []

    # —— 策略调用的接口 ——
    def price(self, symbol=None):
        return self._cur_price

    def buy(self, symbol=None, sz=0.001, **kw):
        sz = float(sz)
        cost = self._cur_price * sz
        fee = cost * self.fee_rate
        if self.cash < cost + fee:
            return
        self.cash -= cost + fee
        new_pos = self.position + sz
        self.avg_cost = (
            (self.avg_cost * self.position + cost) / new_pos if new_pos > 0 else 0.0
        )
        self.position = new_pos
        self.trades.append({"side": "buy", "price": self._cur_price, "sz": sz, "fee": fee})

    def sell(self, symbol=None, sz=0.001, **kw):
        sz = min(float(sz), self.position)
        if sz <= 0:
            return
        proceeds = self._cur_price * sz
        fee = proceeds * self.fee_rate
        pnl = (self._cur_price - self.avg_cost) * sz - fee
        self.cash += proceeds - fee
        self.position -= sz
        self.trades.append(
            {"side": "sell", "price": self._cur_price, "sz": sz, "fee": fee, "pnl": pnl}
        )

    def log(self, message):
        if len(self.logs) < 1000:
            self.logs.append(str(message))

    # —— 引擎内部 ——
    def equity(self):
        return self.cash + self.position * self._cur_price


def run_backtest(source, symbol="BTC-USDT", bar="1m", bars=500,
                 initial_capital=10000, fee_rate=0.0005):
    candles = _fetch_candles(symbol, bar, int(bars))
    ctx = BacktestContext(symbol, initial_capital, fee_rate)

    namespace = {"ctx": ctx}
    try:
        exec(compile(source, "<strategy>", "exec"), namespace)
    except SyntaxError as e:
        raise BacktestError(f"策略脚本语法错误(第 {e.lineno} 行):{e.msg}") from e
    except ModuleNotFoundError as e:
        raise BacktestError(
            f"策略脚本依赖的模块未安装:{e.name}。请仅使用平台已支持的库。"
        ) from e
    except Exception as e:  # noqa: BLE001
        raise BacktestError(f"策略脚本加载失败:{e}") from e

    on_tick = namespace.get("on_tick")
    if not callable(on_tick):
        raise BacktestError("策略脚本必须定义 on_tick(ctx) 函数")

    equity_curve = []
    for c in candles:
        ctx._cur_price = c["close"]
        try:
            on_tick(ctx)
        except Exception as e:  # noqa: BLE001
            ctx.log("on_tick error: %s" % e)
        equity_curve.append({"ts": c["ts"], "equity": round(ctx.equity(), 2)})

    # 收尾:按最后价平掉剩余持仓估值(不产生额外 trade,只体现在最终 equity)
    final_equity = ctx.equity()

    return {
        "symbol": symbol,
        "bar": bar,
        "bars": int(bars),
        "initial_capital": float(initial_capital),
        "final_equity": round(final_equity, 2),
        "equity_curve": equity_curve,
        "trades": ctx.trades,
        "logs": ctx.logs[-50:],
    }
