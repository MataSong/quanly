"""可视化策略的 Python 源码骨架(str.format 填参)。生成的源码即普通 on_tick(ctx)。"""

MA_CROSS = '''\
# 可视化生成:均线交叉(short={short} long={long})
_p = []
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    _p.append(px)
    if len(_p) > {long}:
        _p.pop(0)
    if len(_p) < {long}:
        ctx.log("warming up %d/{long}" % len(_p)); return
    short = sum(_p[-{short}:]) / {short}
    long = sum(_p[-{long}:]) / {long}
    ctx.log("px=%.2f s=%.2f l=%.2f" % (px, short, long))
    if short > long:
        ctx.buy(ctx.symbol, {size})
    elif short < long:
        ctx.sell(ctx.symbol, {size})
'''

GRID = '''\
# 可视化生成:网格({lower}-{upper} {grids} 格)
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    lo, up, n = {lower}, {upper}, {grids}
    step = (up - lo) / n
    if step <= 0:
        ctx.log("invalid grid range"); return
    level = int((px - lo) / step) if px > lo else -1
    ctx.log("px=%.2f level=%d" % (px, level))
    if px < lo:
        ctx.buy(ctx.symbol, {size})
    elif px > up:
        ctx.sell(ctx.symbol, {size})
'''

DCA = '''\
# 可视化生成:定投(每 {period} tick 买入 {amount})
_n = [0]
def on_tick(ctx):
    _n[0] += 1
    if _n[0] % {period} == 0:
        px = ctx.price(ctx.symbol)
        sz = {amount} / px if px > 0 else 0
        ctx.log("DCA buy %.6f @ %.2f" % (sz, px))
        ctx.buy(ctx.symbol, round(sz, 6))
'''

TP_SL = '''\
# 可视化生成:止盈{tp_pct}/止损{sl_pct}
_entry = [None]
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    if _entry[0] is None:
        _entry[0] = px
        ctx.buy(ctx.symbol, {size})
        ctx.log("entry @ %.2f" % px); return
    pnl = (px - _entry[0]) / _entry[0]
    ctx.log("px=%.2f pnl=%.4f" % (px, pnl))
    if pnl >= {tp_pct}:
        ctx.log("TAKE-PROFIT"); ctx.sell(ctx.symbol, {size}); _entry[0] = None
    elif pnl <= -{sl_pct}:
        ctx.log("STOP-LOSS"); ctx.sell(ctx.symbol, {size}); _entry[0] = None
'''

SKELETONS = {"ma_cross": MA_CROSS, "grid": GRID, "dca": DCA, "tp_sl": TP_SL}
