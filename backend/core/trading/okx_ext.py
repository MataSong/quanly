"""OKX Trade/Account API factory helpers for the trading app.

Flag follows credential.env — NOT the global OKX_FLAG env var:
  sim  (simulated/demo) → flag="1"
  live (production)     → flag="0"

Zero mock: all functions connect to real OKX via python-okx.
OKX imports are deferred to function bodies to avoid import-time side-effects.
"""
import logging
from typing import Any

from core.credentials.crypto import decrypt
from core.credentials.models import Credential

logger = logging.getLogger("quanly.trading")


def _flag(cred: Credential) -> str:
    """Return OKX flag string based on credential environment."""
    return "1" if cred.env == Credential.ENV_SIM else "0"


def _trade_api(cred: Credential):
    """Return a python-okx TradeAPI instance authenticated with the credential."""
    from okx import Trade  # type: ignore[import]
    api_key = decrypt(cred.api_key_enc)
    secret = decrypt(cred.secret_enc)
    passphrase = decrypt(cred.passphrase_enc)
    return Trade.TradeAPI(
        api_key=api_key,
        api_secret_key=secret,
        passphrase=passphrase,
        flag=_flag(cred),
        use_server_time=False,
    )


def _account_api(cred: Credential):
    """Return a python-okx AccountAPI instance authenticated with the credential."""
    from okx import Account  # type: ignore[import]
    api_key = decrypt(cred.api_key_enc)
    secret = decrypt(cred.secret_enc)
    passphrase = decrypt(cred.passphrase_enc)
    return Account.AccountAPI(
        api_key=api_key,
        api_secret_key=secret,
        passphrase=passphrase,
        flag=_flag(cred),
        use_server_time=False,
    )


def place_order(
    cred: Credential,
    *,
    inst_type: str,
    inst_id: str,
    side: str,
    ord_type: str,
    sz: str,
    px: str | None = None,
    pos_side: str | None = None,
    td_mode: str | None = None,
    reduce_only: bool | None = None,
) -> dict[str, Any]:
    """Place an order on OKX.

    inst_type: "SPOT" or "SWAP"
    side: "buy" or "sell"
    ord_type: "market" or "limit"
    sz: order size as string
    px: price (required for limit orders)
    pos_side: "long"/"short"/"net" (required for SWAP)
    td_mode: trade mode override; defaults to "cash" for SPOT, "cross" for SWAP
    reduce_only: if True sets reduceOnly="true" on the order

    Returns the OKX data dict (contains ordId, clOrdId, etc.).
    Raises RuntimeError if OKX returns a non-zero code.
    """
    api = _trade_api(cred)

    # Determine tdMode
    if td_mode is None:
        resolved_td_mode = "cash" if inst_type.upper() == "SPOT" else "cross"
    else:
        resolved_td_mode = td_mode

    kwargs: dict[str, Any] = {
        "instId": inst_id,
        "tdMode": resolved_td_mode,
        "side": side,
        "ordType": ord_type,
        "sz": str(sz),
    }

    if px is not None:
        kwargs["px"] = str(px)

    if inst_type.upper() == "SWAP":
        if pos_side is not None:
            kwargs["posSide"] = pos_side

    if reduce_only is True:
        kwargs["reduceOnly"] = "true"

    logger.info(
        "place_order cred=%s env=%s instId=%s side=%s ordType=%s sz=%s",
        cred.id, cred.env, inst_id, side, ord_type, sz,
    )

    resp = api.place_order(**kwargs)
    if resp.get("code") != "0":
        msg = resp.get("msg") or resp.get("data", [{}])[0].get("sMsg", "unknown OKX error")
        raise RuntimeError(f"OKX place_order error [{resp.get('code')}]: {msg}")

    data_list = resp.get("data", [])
    if not data_list:
        raise RuntimeError("OKX place_order returned empty data")
    return data_list[0]


def cancel_order(cred: Credential, inst_id: str, ord_id: str) -> dict[str, Any]:
    """Cancel an order on OKX.

    Returns the OKX data dict.
    Raises RuntimeError if OKX returns a non-zero code.
    """
    api = _trade_api(cred)
    logger.info("cancel_order cred=%s instId=%s ordId=%s", cred.id, inst_id, ord_id)
    resp = api.cancel_order(instId=inst_id, ordId=ord_id)
    if resp.get("code") != "0":
        msg = resp.get("msg") or resp.get("data", [{}])[0].get("sMsg", "unknown OKX error")
        raise RuntimeError(f"OKX cancel_order error [{resp.get('code')}]: {msg}")
    data_list = resp.get("data", [])
    if not data_list:
        # OKX 撤单成功时 data 不应为空;为空视为异常,避免前端误判成功。
        raise RuntimeError("OKX cancel_order returned empty data")
    return data_list[0]


def get_orders(cred: Credential, inst_type: str | None = None) -> list[dict[str, Any]]:
    """Get list of open (pending) orders from OKX.

    Returns list of OKX order dicts.
    Raises RuntimeError on OKX error.
    """
    api = _trade_api(cred)
    kwargs: dict[str, str] = {}
    if inst_type:
        kwargs["instType"] = inst_type.upper()
    resp = api.get_order_list(**kwargs)
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_order_list error [{resp.get('code')}]: {msg}")
    return resp.get("data", [])


def get_positions(cred: Credential, inst_type: str | None = None) -> list[dict[str, Any]]:
    """Get account positions from OKX.

    Returns list of OKX position dicts.
    Raises RuntimeError on OKX error.
    """
    api = _account_api(cred)
    kwargs: dict[str, str] = {}
    if inst_type:
        kwargs["instType"] = inst_type.upper()
    resp = api.get_positions(**kwargs)
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_positions error [{resp.get('code')}]: {msg}")
    return resp.get("data", [])


def get_balance(cred: Credential) -> list[dict[str, Any]]:
    """Get account balance from OKX.

    Returns list of OKX balance dicts.
    Raises RuntimeError on OKX error.
    """
    api = _account_api(cred)
    resp = api.get_account_balance()
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_account_balance error [{resp.get('code')}]: {msg}")
    return resp.get("data", [])


def get_bills(cred: Credential, limit: int = 100) -> list[dict[str, Any]]:
    """拉取账户账单流水(充值/提现/成交/手续费/资金费等)。真连 OKX,无 mock。

    Returns list of OKX bill dicts.
    Raises RuntimeError on OKX error.
    """
    api = _account_api(cred)
    resp = api.get_account_bills(limit=str(limit))
    if resp.get("code") != "0":
        msg = resp.get("msg") or resp
        raise RuntimeError(f"OKX get_account_bills error [{resp.get('code')}]: {msg}")
    return resp.get("data", [])
