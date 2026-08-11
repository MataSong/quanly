"""OKX 凭证连通性校验:用给定 Key/Secret/Passphrase 临时构造 adapter 调私有接口,
验证凭证有效性。保存前校验 + 已存凭证「测试连通性」按钮共用。"""
from apps.exchanges.factory import AdapterFactory
from apps.exchanges.types import Env

from .crypto import encrypt
from .models import ExchangeCredential


def check_okx(env, api_key, secret, passphrase):
    """返回 (ok: bool, message: str)。用明文凭证临时构造 adapter,调 get_balances。

    不落库:构造未保存的 ExchangeCredential 内存实例(secret/passphrase 即时加密,
    因为 adapter 内部会 decrypt)。
    """
    x_env = Env.SIM if str(env) == "sim" else Env.LIVE
    cred = ExchangeCredential(
        exchange="okx",
        env=str(env),
        api_key=api_key,
        secret_enc=encrypt(secret),
        passphrase_enc=encrypt(passphrase),
    )
    try:
        adapter = AdapterFactory.create("okx", x_env, cred)
        adapter.get_balances()  # 私有接口:凭证/权限错误会抛异常
        return True, "OK"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
