from apps.credentials.crypto import decrypt
from apps.exchanges.base import ExchangeAdapter
from apps.exchanges.errors import ExchangeError
from apps.exchanges.types import Balance, Candle, Capability, Env, Order, Position, Ticker


class OKXAdapter(ExchangeAdapter):
    capabilities = {
        Capability.SPOT,
        Capability.SWAP,
        Capability.FUTURES,
        Capability.OPTION,
        Capability.EARN,
        Capability.LOAN,
    }

    @staticmethod
    def _flag_for(env: Env) -> str:
        return "1" if env == Env.SIM else "0"

    def __init__(self, credential, env: Env):
        super().__init__(credential, env)
        flag = self._flag_for(env)
        from okx import Account, Funding, MarketData, PublicData, Trade
        from okx.Finance import Savings

        if credential is not None:
            key = credential.api_key
            secret = decrypt(credential.secret_enc)
            pph = decrypt(credential.passphrase_enc)
        else:
            key = secret = pph = ""

        self._market = MarketData.MarketAPI(flag=flag)
        self._public = PublicData.PublicAPI(flag=flag)
        self._funding = Funding.FundingAPI(key, secret, pph, False, flag) if credential else None
        self._finance = Savings.SavingsAPI(key, secret, pph, False, flag) if credential else None
        self._account = (
            Account.AccountAPI(key, secret, pph, False, flag) if credential else None
        )
        self._trade = (
            Trade.TradeAPI(key, secret, pph, False, flag) if credential else None
        )

    def _decrypt_keys(self):
        """返回 (api_key, secret, passphrase);无凭证时返回空串。"""
        cred = self.credential
        if cred is None:
            return "", "", ""
        return (
            cred.api_key,
            decrypt(cred.secret_enc),
            decrypt(cred.passphrase_enc),
        )

    def parse_ws_balances(self, msg):
        """OKX account 频道推送 → 标准 Balance 列表(与 REST 同形)。"""
        out = []
        for d in (msg or {}).get("data", []) or []:
            for c in d.get("details", []) or []:
                out.append(
                    Balance(
                        ccy=c.get("ccy", ""),
                        total=float(c.get("eq") or 0),
                        available=float(c.get("availBal") or 0),
                        frozen=float(c.get("frozenBal") or 0),
                    )
                )
        return out

    def parse_ws_positions(self, msg):
        """OKX positions 频道推送 → 标准 Position 列表。"""
        out = []
        for p in (msg or {}).get("data", []) or []:
            out.append(
                Position(
                    symbol=p.get("instId", ""),
                    side=p.get("posSide", "net"),
                    qty=float(p.get("pos") or 0),
                    avg_price=float(p.get("avgPx") or 0),
                    upl=float(p.get("upl") or 0),
                    liq_price=float(p.get("liqPx") or 0),
                )
            )
        return out

    def parse_ws_orders(self, msg):
        """OKX orders 频道推送 → 标准 Order 列表。"""
        out = []
        for o in (msg or {}).get("data", []) or []:
            out.append(
                Order(
                    order_id=o.get("ordId", ""),
                    symbol=o.get("instId", ""),
                    state=o.get("state", ""),
                    filled_sz=float(o.get("accFillSz") or 0),
                    avg_px=float(o.get("avgPx") or 0),
                )
            )
        return out

    def get_ticker(self, symbol):
        d = self._market.get_ticker(instId=symbol)["data"][0]
        return Ticker(symbol=symbol, last=float(d["last"]), ts=int(d["ts"]))

    def get_instruments(self, inst_type="SPOT"):
        """拉取该品类全部可交易 instrument,返回完整元数据列表。

        每项含:instId(交易对)、instType(品类)、lever(最大杠杆,现货为1)、
        baseCcy/quoteCcy/settleCcy、ctVal/ctMult(合约面值)、lotSz/minSz/tickSz。
        供行情下拉、杠杆上限、下单精度校验共用。
        """
        # 期权:OKX 要求按标的(uly)分别拉取,不带 uly 返回空。
        # 覆盖主流标的,合并去重。
        if inst_type == "OPTION":
            rows = []
            for uly in ("BTC-USD", "ETH-USD", "SOL-USD"):
                try:
                    r = self._public.get_instruments(instType="OPTION", uly=uly)
                    rows.extend(r.get("data", []))
                except Exception:
                    continue
        else:
            rows = self._public.get_instruments(instType=inst_type).get("data", [])
        out = []
        for i in rows:
            if i.get("state") != "live":
                continue
            out.append(
                {
                    "instId": i.get("instId", ""),
                    "instType": inst_type,
                    "lever": int(float(i.get("lever") or 1)),
                    "baseCcy": i.get("baseCcy", ""),
                    "quoteCcy": i.get("quoteCcy", ""),
                    "settleCcy": i.get("settleCcy", ""),
                    "ctVal": i.get("ctVal", ""),
                    "minSz": i.get("minSz", ""),
                    "lotSz": i.get("lotSz", ""),
                    "tickSz": i.get("tickSz", ""),
                }
            )
        return out

    def get_instrument_ids(self, inst_type="SPOT"):
        """仅返回 instId 列表(兼容旧调用方)。"""
        return [i["instId"] for i in self.get_instruments(inst_type)]

    # 以下方法由后续分期(P1 行情 / P2 交易 / P3 资产)实现,
    # 抽象契约已在 base.ExchangeAdapter 定义,此处为骨架占位。
    def get_candles(self, symbol, timeframe, limit=100):
        # OKX 返回时间倒序,每行 [ts, o, h, l, c, vol, ...];翻转为升序返回标准 Candle
        # OKX 单次上限 300;超限会返回空,故这里夹取。
        limit = min(int(limit), 300)
        resp = self._market.get_candlesticks(instId=symbol, bar=timeframe, limit=str(limit))
        rows = resp.get("data") or []
        if not rows and resp.get("code") not in ("0", 0, None):
            raise ExchangeError(f"OKX 获取K线失败: {resp.get('msg')}")
        candles = [
            Candle(
                ts=int(r[0]),
                open=float(r[1]),
                high=float(r[2]),
                low=float(r[3]),
                close=float(r[4]),
                vol=float(r[5]),
            )
            for r in rows
        ]
        candles.reverse()
        return candles

    def get_balances(self):
        # OKX 统一账户余额;返回标准 Balance 列表
        resp = self._account.get_account_balance()
        out = []
        for d in resp.get("data", []):
            for c in d.get("details", []):
                out.append(
                    Balance(
                        ccy=c["ccy"],
                        total=float(c.get("eq") or 0),
                        available=float(c.get("availBal") or 0),
                        frozen=float(c.get("frozenBal") or 0),
                    )
                )
        return out

    def get_positions(self):
        resp = self._account.get_positions()
        out = []
        for p in resp.get("data", []):
            out.append(
                Position(
                    symbol=p["instId"],
                    side=p.get("posSide", "net"),
                    qty=float(p.get("pos") or 0),
                    avg_price=float(p.get("avgPx") or 0),
                    upl=float(p.get("upl") or 0),
                    liq_price=float(p.get("liqPx") or 0),
                )
            )
        return out

    def place_order(self, req):
        # 平台标准 OrderRequest → OKX 下单参数
        params = {
            "instId": req.symbol,
            "tdMode": req.td_mode,
            "side": req.side,
            "ordType": req.ord_type,
            "sz": str(req.sz),
        }
        if req.px is not None:
            params["px"] = str(req.px)
        if req.pos_side:
            params["posSide"] = req.pos_side
        # 杠杆类订单先设置杠杆倍数(现货 cash 模式无需设置)
        if req.lever and req.td_mode in ("cross", "isolated"):
            try:
                self._account.set_leverage(
                    instId=req.symbol, lever=str(req.lever), mgnMode=req.td_mode
                )
            except Exception:  # noqa: BLE001 —— 设杠杆失败不阻断,由下单侧报错
                pass
        resp = self._trade.place_order(**params)
        data = resp.get("data", [{}])[0]
        if data.get("sCode") not in ("0", 0, None):
            raise ExchangeError(f"OKX 下单失败: {data.get('sMsg')}")
        return Order(order_id=data.get("ordId", ""), symbol=req.symbol, state="live")

    def cancel_order(self, order_id, symbol=None):
        resp = self._trade.cancel_order(instId=symbol or "", ordId=order_id)
        data = resp.get("data", [{}])[0]
        return Order(order_id=order_id, symbol=symbol or "", state="canceled")

    def close_position(self, symbol, pos_side="net", td_mode="cross"):
        """市价一键平仓(OKX Trade.close_positions)。"""
        return self._trade.close_positions(
            instId=symbol, mgnMode=td_mode, posSide=pos_side
        )

    def transfer(self, ccy, amount, from_acct="18", to_acct="6"):
        """资金划转(OKX Funding.funds_transfer)。账户编码:6=资金,18=交易/统一。"""
        return self._funding.funds_transfer(
            ccy=ccy, amt=str(amount), type="0", from_=from_acct, to=to_acct
        )

    def get_savings(self):
        """活期理财持仓(OKX Finance Savings)。"""
        return self._finance.get_saving_balance().get("data", [])

    def get_savings_products(self):
        """活期理财可申购币种及当前年化(OKX 公共借贷利率)。

        返回 dict 列表:{ccy, apr}。OKX 仅公开活期(flexible)借贷利率,
        无定期/双币等产品目录,故这里只列活期可赚币种。
        """
        resp = self._finance.get_public_borrow_info() or {}
        out = []
        for r in resp.get("data", []):
            ccy = r.get("ccy")
            rate = r.get("estRate") or r.get("rate") or "0"
            if ccy:
                out.append({"ccy": ccy, "apr": float(rate or 0)})
        return out

    def subscribe_savings(self, ccy, amount):
        return self._finance.savings_purchase_redemption(
            ccy=ccy, amt=str(amount), side="purchase", rate="0"
        )

    def redeem_savings(self, ccy, amount):
        return self._finance.savings_purchase_redemption(
            ccy=ccy, amt=str(amount), side="redempt", rate="0"
        )
