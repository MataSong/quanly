"""strategy-runner 容器入口。

拿到 RUN_TOKEN(非真实密钥),通过后端 strategy-api 与平台交互。
支持两种用户脚本:
  1) 填空式:脚本定义 on_tick(ctx) -> runner 每 INTERVAL 秒调用一次
  2) 文件式:脚本自带主循环 -> runner 直接 exec,并注入全局 ctx
"""
import os
import sys
import time

import requests

RUN_ID = os.environ.get("RUN_ID", "")
RUN_TOKEN = os.environ.get("RUN_TOKEN", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
SYMBOL = os.environ.get("SYMBOL", "BTC-USDT")
INTERVAL = int(os.environ.get("INTERVAL", "5"))
SCRIPT_PATH = os.environ.get("SCRIPT_PATH", "/scripts/strategy.py")

_HEADERS = {"X-Run-Token": RUN_TOKEN}


class Ctx:
    """注入策略脚本的上下文;所有操作经后端鉴权代理,拿不到真实密钥。"""

    symbol = SYMBOL
    interval = INTERVAL

    def price(self, symbol=None):
        r = requests.get(
            f"{BACKEND_URL}/api/strategy-api/market",
            params={"symbol": symbol or SYMBOL},
            headers=_HEADERS,
            timeout=10,
        )
        return float(r.json()["price"])

    def candles(self, symbol=None, bar="1m", limit=100):
        """拉取历史 K 线,返回 list[dict](ts/open/high/low/close/vol,时间升序)。
        策略可据此用 pandas 计算 MA/MACD 等指标。"""
        r = requests.get(
            f"{BACKEND_URL}/api/strategy-api/candles",
            params={"symbol": symbol or SYMBOL, "bar": bar, "limit": limit},
            headers=_HEADERS,
            timeout=15,
        )
        return r.json().get("candles", [])

    def positions(self):
        return requests.get(
            f"{BACKEND_URL}/api/strategy-api/positions", headers=_HEADERS, timeout=10
        ).json()

    def balances(self):
        return requests.get(
            f"{BACKEND_URL}/api/strategy-api/balances", headers=_HEADERS, timeout=10
        ).json()

    def _order(self, side, sz, symbol=None, ord_type="market", px=None, inst_type="SPOT", lever=1):
        body = {
            "side": side, "sz": str(sz), "symbol": symbol or SYMBOL,
            "ord_type": ord_type, "inst_type": inst_type, "lever": lever,
        }
        if px is not None:
            body["px"] = str(px)
        r = requests.post(
            f"{BACKEND_URL}/api/strategy-api/order", json=body, headers=_HEADERS, timeout=10
        )
        return r.json()

    def buy(self, symbol=None, sz=0.001, **kw):
        return self._order("buy", sz, symbol, **kw)

    def sell(self, symbol=None, sz=0.001, **kw):
        return self._order("sell", sz, symbol, **kw)

    def log(self, message):
        print(message, flush=True)
        try:
            requests.post(
                f"{BACKEND_URL}/api/strategy-api/log",
                json={"message": str(message)},
                headers=_HEADERS,
                timeout=5,
            )
        except Exception:
            pass


def main():
    ctx = Ctx()
    with open(SCRIPT_PATH) as f:
        code = f.read()

    namespace = {"ctx": ctx}
    exec(compile(code, SCRIPT_PATH, "exec"), namespace)

    on_tick = namespace.get("on_tick")
    if callable(on_tick):
        ctx.log("runner: on_tick 模式,每 %ds 轮询" % INTERVAL)
        while True:
            try:
                on_tick(ctx)
            except Exception as e:  # 单次 tick 出错不终止策略
                ctx.log("on_tick error: %s" % e)
            time.sleep(INTERVAL)
    else:
        # 文件式:脚本已在 exec 时执行(自带主循环)。若已返回则结束。
        ctx.log("runner: 脚本执行完毕")


if __name__ == "__main__":
    sys.exit(main())
