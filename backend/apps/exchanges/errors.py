class ExchangeError(Exception):
    """交易所适配器层统一基础异常。上层业务只 catch 本类及其子类。"""


class AuthError(ExchangeError):
    pass


class RateLimitError(ExchangeError):
    pass


class InsufficientBalanceError(ExchangeError):
    pass


class InvalidParamError(ExchangeError):
    pass
