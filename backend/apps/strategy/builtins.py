"""内置示例策略源码(填空式 on_tick 与文件式主循环各一个)。

用户首次访问策略中心时,为其种子这些内置策略(kind=builtin)。
策略通过注入的 ctx / quanly SDK 与后端交互,拿不到真实密钥。
"""

MA_CROSS = '''\
# 均线策略(填空式):价格上穿短均线买入,下穿卖出。
# runner 每 interval 秒调用一次 on_tick(ctx)。
_prices = []

def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    _prices.append(px)
    if len(_prices) > 20:
        _prices.pop(0)
    if len(_prices) < 5:
        ctx.log("warming up: %d samples" % len(_prices))
        return
    short = sum(_prices[-3:]) / 3
    long = sum(_prices[-10:]) / min(len(_prices), 10)
    ctx.log("px=%.2f short=%.2f long=%.2f" % (px, short, long))
    if short > long:
        ctx.buy(ctx.symbol, 0.001)
    elif short < long:
        ctx.sell(ctx.symbol, 0.001)
'''

GRID = '''\
# 网格策略(填空式):偏离基准价一定比例就反向下单。
_base = [None]

def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    if _base[0] is None:
        _base[0] = px
        ctx.log("grid base = %.2f" % px)
        return
    change = (px - _base[0]) / _base[0]
    ctx.log("px=%.2f change=%.4f" % (px, change))
    if change > 0.005:
        ctx.sell(ctx.symbol, 0.001)
        _base[0] = px
    elif change < -0.005:
        ctx.buy(ctx.symbol, 0.001)
        _base[0] = px
'''

# 综合评分策略(移植自 vobot):三均线收敛+突破+量能+趋势+MACD 五因子加权评分,
# 总分 >= 阈值方开仓;带止损/止盈/移动止盈。用 pandas 计算指标。
COMPOSITE = '''\
import pandas as pd

CFG = dict(
    ma_short=5, ma_mid=15, ma_long=20,
    w_conv=30, w_break=20, w_vol=20, w_trend=15, w_macd=15,
    entry_threshold=70, break_offset_pct=0.1, trend_bars=5,
    vol_mult=1.5, stop_loss=0.02, take_profit=0.04, size=0.01,
)
_state = {"entry": None, "peak": None}

def _macd(close, f=12, s=26, sig=9):
    ema_f = close.ewm(span=f).mean(); ema_s = close.ewm(span=s).mean()
    dif = ema_f - ema_s; dea = dif.ewm(span=sig).mean()
    return (dif - dea) * 2

def _score(df, direction):
    last = df.iloc[-1]; c = CFG
    ma5, ma15, ma20, price = last.ma5, last.ma15, last.ma20, last.close
    conv = (ma5 + ma15 + ma20) / 3
    s = 0
    spread = max(ma5, ma15, ma20) - min(ma5, ma15, ma20)
    if spread / conv < 0.005: s += c["w_conv"]
    off = conv * c["break_offset_pct"] / 100
    if direction == "long" and price > conv + off: s += c["w_break"]
    if direction == "short" and price < conv - off: s += c["w_break"]
    if last.vol > df.vol.tail(20).mean() * c["vol_mult"]: s += c["w_vol"]
    trend = df.close.tail(c["trend_bars"])
    up = trend.iloc[-1] > trend.iloc[0]
    if (direction == "long" and up) or (direction == "short" and not up): s += c["w_trend"]
    if (direction == "long" and last.macd_hist > 0) or (direction == "short" and last.macd_hist < 0):
        s += c["w_macd"]
    return s

def on_tick(ctx):
    c = CFG
    rows = ctx.candles(ctx.symbol, "1m", 60)
    if len(rows) < c["ma_long"] + 5:
        ctx.log("warming up: %d bars" % len(rows)); return
    df = pd.DataFrame(rows)
    df["ma5"] = df.close.rolling(c["ma_short"]).mean()
    df["ma15"] = df.close.rolling(c["ma_mid"]).mean()
    df["ma20"] = df.close.rolling(c["ma_long"]).mean()
    df["macd_hist"] = _macd(df.close)
    df = df.dropna()
    if df.empty:
        return
    price = df.iloc[-1].close
    pos = _state["entry"]
    # 持仓中:止损/止盈/移动止盈
    if pos is not None:
        _state["peak"] = max(_state["peak"] or price, price)
        pnl = (price - pos) / pos
        if pnl <= -c["stop_loss"]:
            ctx.log("STOP-LOSS %.2f%% 平仓" % (pnl*100)); ctx.sell(ctx.symbol, c["size"]); _state["entry"]=None; return
        if pnl >= c["take_profit"]:
            ctx.log("TAKE-PROFIT %.2f%% 平仓" % (pnl*100)); ctx.sell(ctx.symbol, c["size"]); _state["entry"]=None; return
        if _state["peak"] and (price - _state["peak"]) / _state["peak"] <= -0.015:
            ctx.log("TRAILING 回撤平仓"); ctx.sell(ctx.symbol, c["size"]); _state["entry"]=None; return
        return
    # 空仓:评分开多
    long_s = _score(df, "long")
    ctx.log("price=%.2f long_score=%d/%d" % (price, long_s, c["entry_threshold"]))
    if long_s >= c["entry_threshold"]:
        ctx.log("BUY 评分达标 %d 开多" % long_s)
        ctx.buy(ctx.symbol, c["size"]); _state["entry"] = price; _state["peak"] = price
'''

BUILTINS = [
    {"name": "均线交叉 MA Cross", "source": MA_CROSS},
    {"name": "网格 Grid", "source": GRID},
    {"name": "综合评分 Composite", "source": COMPOSITE},
]
'''
文件式(自带主循环)示例——供用户参考,不默认种子:
import time
while True:
    px = ctx.price(ctx.symbol)
    ctx.log("tick %.2f" % px)
    ctx.buy(ctx.symbol, 0.001)
    time.sleep(ctx.interval)
'''
