# Quanly P0 骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **本项目严禁任何 git 操作** —— 计划中每个 Task 末尾用「验证并勾选完成」代替 commit,不写 git 命令。

**Goal:** 搭起 Quanly 可运行骨架:Docker Compose 全家桶能起来,多用户注册/登录,OKX API 密钥加密管理,交易所抽象层 + OKXAdapter 骨架能连通 OKX demo 环境。

**Architecture:** Django+DRF 后端分层(网关层 / 领域层 / 交易所抽象层),SimpleJWT 鉴权,Fernet 加密密钥;Vue3 前端毛玻璃壳 + 登录/密钥页;适配器层定义 `ExchangeAdapter` 抽象基类 + `OKXAdapter` 实现,工厂按 env 注入 flag;Docker Compose 编排 postgres/redis/influxdb/backend/前端。

**Tech Stack:** Python 3.11 / Django 5 / DRF / djangorestframework-simplejwt / cryptography(Fernet) / python-okx / Vue3 + Vite + TS + Pinia + vue-i18n / PostgreSQL / Redis / InfluxDB / Docker Compose。

## Global Constraints

- 依赖安装一律用 `uv pip install --python .venv/bin/python --index-url https://pypi.tuna.tsinghua.edu.cn/simple`(直连 PyPI CDN 会挂起)。`.venv` 无 pip,不要用 `python -m pip`。
- **严禁手写 OKX HTTP 请求**,一律通过 `python-okx` SDK。
- **严禁上层业务代码直接 import okx**;OKX 细节只能出现在 `exchanges/okx/` 内。
- 所有交易/资产/策略数据带 `env`(SIM/LIVE)字段;所有业务数据带 `user` 外键。
- OKX 接入:模拟盘 flag='1',实盘 flag='0',按 env 注入。
- 密钥 secret/passphrase 加密落库,永不返回前端;api_key 仅回显后四位。
- 后端测试用 sqlite 即可(psycopg2 非测试必需)。
- **不执行 git 操作。**

---

### Task 1: 后端工程骨架 + 依赖

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config/__init__.py`, `backend/config/settings.py`, `backend/config/urls.py`, `backend/config/asgi.py`, `backend/config/wsgi.py`
- Create: `backend/manage.py`
- Create: `backend/pytest.ini`

**Interfaces:**
- Produces: 可 `python manage.py check` 通过的 Django 项目;`config.settings` 从环境变量读 DB/Redis/密钥配置。

- [ ] **Step 1: 写 requirements.txt**

```
Django>=5.0,<6.0
djangorestframework
djangorestframework-simplejwt
django-cors-headers
cryptography
python-okx
celery
redis
channels
daphne
influxdb-client
psycopg2-binary
pytest
pytest-django
```

- [ ] **Step 2: 建 venv 并安装(清华镜像)**

Run:
```bash
cd backend && uv venv .venv --python 3.11 && \
uv pip install --python .venv/bin/python \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```
Expected: 全部安装成功,无挂起。

- [ ] **Step 3: 写 settings.py(关键片段)**

```python
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "corsheaders",
    "apps.users", "apps.credentials", "apps.exchanges",
]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
AUTH_USER_MODEL = "users.User"
DATABASES = {"default": {
    "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
    "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
    "USER": os.environ.get("DB_USER", ""), "PASSWORD": os.environ.get("DB_PASSWORD", ""),
    "HOST": os.environ.get("DB_HOST", ""), "PORT": os.environ.get("DB_PORT", ""),
}}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}
SECRET_ENCRYPTION_KEY = os.environ.get("SECRET_ENCRYPTION_KEY", "")
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": [
    "django.template.context_processors.request","django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages"]}}]
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- [ ] **Step 4: 写 pytest.ini**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
```

- [ ] **Step 5: 验证 `python manage.py check` 通过并勾选完成**

Run: `cd backend && .venv/bin/python manage.py check`
Expected: System check identified no issues.

---

### Task 2: 用户模型 + 注册/登录 API

**Files:**
- Create: `backend/apps/__init__.py`, `backend/apps/users/__init__.py`, `backend/apps/users/models.py`, `backend/apps/users/serializers.py`, `backend/apps/users/views.py`, `backend/apps/users/urls.py`, `backend/apps/users/apps.py`
- Test: `backend/apps/users/test_auth.py`

**Interfaces:**
- Consumes: `AUTH_USER_MODEL="users.User"`(Task 1)。
- Produces: `User` 模型(字段 email、locale、theme);API `POST /api/auth/register`、`POST /api/auth/login`(返回 access/refresh JWT)、`GET /api/auth/me`。

- [ ] **Step 1: 写失败测试**

```python
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_register_then_login():
    c = APIClient()
    r = c.post("/api/auth/register", {"username":"u1","email":"u1@x.com","password":"pass12345"}, format="json")
    assert r.status_code == 201
    r = c.post("/api/auth/login", {"username":"u1","password":"pass12345"}, format="json")
    assert r.status_code == 200 and "access" in r.data
    token = r.data["access"]
    r = c.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 200 and r.data["username"] == "u1"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/pytest apps/users/test_auth.py -v`
Expected: FAIL(URL/模型未定义)。

- [ ] **Step 3: 写 User 模型**

```python
from django.contrib.auth.models import AbstractUser
from django.db import models
class User(AbstractUser):
    locale = models.CharField(max_length=8, default="zh-CN")
    theme = models.CharField(max_length=8, default="dark")
```

- [ ] **Step 4: 写 serializers + views + urls**

```python
# serializers.py
from rest_framework import serializers
from .models import User
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta: model = User; fields = ("id","username","email","password")
    def create(self, v): return User.objects.create_user(**v)
class UserSerializer(serializers.ModelSerializer):
    class Meta: model = User; fields = ("id","username","email","locale","theme")

# views.py
from rest_framework import generics, permissions
from rest_framework.response import Response
from .serializers import RegisterSerializer, UserSerializer
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer; permission_classes = [permissions.AllowAny]
class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    def get_object(self): return self.request.user

# urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegisterView, MeView
urlpatterns = [
    path("auth/register", RegisterView.as_view()),
    path("auth/login", TokenObtainPairView.as_view()),
    path("auth/refresh", TokenRefreshView.as_view()),
    path("auth/me", MeView.as_view()),
]
```
并在 `config/urls.py` 挂 `path("api/", include("apps.users.urls"))`。

- [ ] **Step 5: 迁移 + 运行测试通过**

Run: `cd backend && .venv/bin/python manage.py makemigrations && .venv/bin/pytest apps/users/test_auth.py -v`
Expected: PASS。勾选完成。

---

### Task 3: 加密工具 + 密钥模型/API

**Files:**
- Create: `backend/apps/credentials/__init__.py`, `models.py`, `crypto.py`, `serializers.py`, `views.py`, `urls.py`, `apps.py`
- Test: `backend/apps/credentials/test_crypto.py`, `backend/apps/credentials/test_api.py`

**Interfaces:**
- Consumes: `User`(Task 2)、`SECRET_ENCRYPTION_KEY`(Task 1)。
- Produces: `encrypt(s)->str` / `decrypt(s)->str`;`ExchangeCredential` 模型(user、exchange、env、api_key、secret_enc、passphrase_enc、label);API `GET/POST/DELETE /api/credentials`,响应中 secret/passphrase 不出现,api_key 仅后四位。

- [ ] **Step 1: 写加密失败测试**

```python
from apps.credentials.crypto import encrypt, decrypt
def test_encrypt_roundtrip(settings):
    from cryptography.fernet import Fernet
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    c = encrypt("secret-abc")
    assert c != "secret-abc" and decrypt(c) == "secret-abc"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/pytest apps/credentials/test_crypto.py -v`
Expected: FAIL(crypto 未定义)。

- [ ] **Step 3: 写 crypto.py**

```python
from cryptography.fernet import Fernet
from django.conf import settings
def _f(): return Fernet(settings.SECRET_ENCRYPTION_KEY.encode())
def encrypt(s: str) -> str: return _f().encrypt(s.encode()).decode()
def decrypt(s: str) -> str: return _f().decrypt(s.encode()).decode()
```

- [ ] **Step 4: 写模型 + serializer(隐藏敏感字段)+ views + urls**

```python
# models.py
from django.db import models
from django.conf import settings
class Env(models.TextChoices): SIM="sim","模拟盘"; LIVE="live","实盘"
class ExchangeCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exchange = models.CharField(max_length=16, default="okx")
    env = models.CharField(max_length=4, choices=Env.choices)
    label = models.CharField(max_length=64, default="default")
    api_key = models.CharField(max_length=128)
    secret_enc = models.TextField()
    passphrase_enc = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ("user","exchange","env","label")

# serializers.py — 写入接明文 secret/passphrase,读出只给 api_key 后四位
from rest_framework import serializers
from .models import ExchangeCredential
from .crypto import encrypt
class CredentialWriteSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True)
    passphrase = serializers.CharField(write_only=True)
    class Meta:
        model = ExchangeCredential
        fields = ("id","exchange","env","label","api_key","secret","passphrase")
    def create(self, v):
        v["secret_enc"] = encrypt(v.pop("secret")); v["passphrase_enc"] = encrypt(v.pop("passphrase"))
        v["user"] = self.context["request"].user
        return ExchangeCredential.objects.create(**v)
class CredentialReadSerializer(serializers.ModelSerializer):
    api_key_masked = serializers.SerializerMethodField()
    class Meta: model = ExchangeCredential; fields = ("id","exchange","env","label","api_key_masked","created_at")
    def get_api_key_masked(self, o): return "****" + o.api_key[-4:]

# views.py
from rest_framework import viewsets
from .models import ExchangeCredential
from .serializers import CredentialWriteSerializer, CredentialReadSerializer
class CredentialViewSet(viewsets.ModelViewSet):
    def get_queryset(self): return ExchangeCredential.objects.filter(user=self.request.user)
    def get_serializer_class(self):
        return CredentialWriteSerializer if self.action in ("create","update","partial_update") else CredentialReadSerializer
```
urls 用 DRF router 注册 `credentials`。

- [ ] **Step 5: 写 API 测试**

```python
import pytest
from cryptography.fernet import Fernet
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_credential_hides_secret(settings):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    u = get_user_model().objects.create_user("u1", password="pass12345")
    c = APIClient(); c.force_authenticate(u)
    r = c.post("/api/credentials/", {"env":"sim","label":"d","api_key":"AK1234567890",
        "secret":"S","passphrase":"P"}, format="json")
    assert r.status_code == 201
    r = c.get("/api/credentials/")
    body = str(r.data)
    assert "secret" not in body.lower() and "7890" in body
```

- [ ] **Step 6: 迁移 + 运行全部测试通过,勾选完成**

Run: `cd backend && .venv/bin/python manage.py makemigrations && .venv/bin/pytest apps/credentials -v`
Expected: PASS。

---

### Task 4: 交易所抽象层 + 标准数据结构

**Files:**
- Create: `backend/apps/exchanges/__init__.py`, `apps.py`, `types.py`, `base.py`, `errors.py`, `factory.py`
- Test: `backend/apps/exchanges/test_factory.py`

**Interfaces:**
- Produces:
  - `types.py`:`@dataclass` 标准结构 `Candle`、`Ticker`、`Balance`、`Position`、`Order`、`OrderRequest`;枚举 `Env`(SIM/LIVE)、`InstType`(SPOT/MARGIN/SWAP/FUTURES/OPTION)、`Capability`。
  - `base.py`:抽象基类 `ExchangeAdapter(credential, env)`,抽象方法 `get_candles/get_ticker/get_balances/get_positions/place_order/cancel_order`;`supports(cap)->bool`。
  - `errors.py`:`ExchangeError` 及子类 `AuthError/RateLimitError/InsufficientBalanceError/InvalidParamError`。
  - `factory.py`:`register_adapter(name, cls)`、`AdapterFactory.create(exchange, env, credential)->ExchangeAdapter`。

- [ ] **Step 1: 写工厂失败测试**

```python
import pytest
from apps.exchanges.base import ExchangeAdapter
from apps.exchanges.factory import AdapterFactory, register_adapter
from apps.exchanges.types import Env

def test_factory_creates_registered_adapter():
    class Dummy(ExchangeAdapter):
        def get_candles(self,*a,**k): return []
        def get_ticker(self,*a,**k): return None
        def get_balances(self): return []
        def get_positions(self): return []
        def place_order(self, req): return None
        def cancel_order(self, oid): return None
    register_adapter("dummy", Dummy)
    a = AdapterFactory.create("dummy", Env.SIM, credential=None)
    assert isinstance(a, ExchangeAdapter) and a.env == Env.SIM

def test_factory_unknown_raises():
    with pytest.raises(KeyError):
        AdapterFactory.create("nope", Env.SIM, credential=None)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/pytest apps/exchanges/test_factory.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 types.py / errors.py / base.py / factory.py**

```python
# types.py
from dataclasses import dataclass
from enum import Enum
class Env(str, Enum): SIM="sim"; LIVE="live"
class InstType(str, Enum): SPOT="SPOT"; MARGIN="MARGIN"; SWAP="SWAP"; FUTURES="FUTURES"; OPTION="OPTION"
class Capability(str, Enum): SPOT="spot"; SWAP="swap"; OPTION="option"; EARN="earn"; LOAN="loan"
@dataclass
class Candle: ts:int; open:float; high:float; low:float; close:float; vol:float
@dataclass
class Ticker: symbol:str; last:float; ts:int
@dataclass
class Balance: ccy:str; total:float; available:float; frozen:float
@dataclass
class Position: symbol:str; side:str; qty:float; avg_price:float; upl:float; liq_price:float=0.0
@dataclass
class OrderRequest: symbol:str; inst_type:InstType; side:str; ord_type:str; sz:float; px:float=None; td_mode:str="cash"
@dataclass
class Order: order_id:str; symbol:str; state:str; filled_sz:float=0.0; avg_px:float=0.0

# errors.py
class ExchangeError(Exception): ...
class AuthError(ExchangeError): ...
class RateLimitError(ExchangeError): ...
class InsufficientBalanceError(ExchangeError): ...
class InvalidParamError(ExchangeError): ...

# base.py
from abc import ABC, abstractmethod
from .types import Env, Capability
class ExchangeAdapter(ABC):
    capabilities: set = set()
    def __init__(self, credential, env: Env): self.credential=credential; self.env=env
    def supports(self, cap: Capability) -> bool: return cap in self.capabilities
    @abstractmethod
    def get_candles(self, symbol, timeframe, limit=100): ...
    @abstractmethod
    def get_ticker(self, symbol): ...
    @abstractmethod
    def get_balances(self): ...
    @abstractmethod
    def get_positions(self): ...
    @abstractmethod
    def place_order(self, req): ...
    @abstractmethod
    def cancel_order(self, order_id): ...

# factory.py
_REGISTRY = {}
def register_adapter(name, cls): _REGISTRY[name] = cls
class AdapterFactory:
    @staticmethod
    def create(exchange, env, credential):
        return _REGISTRY[exchange](credential, env)
```

- [ ] **Step 4: 运行测试通过,勾选完成**

Run: `cd backend && .venv/bin/pytest apps/exchanges/test_factory.py -v`
Expected: PASS。

---

### Task 5: OKXAdapter 骨架(SDK 封装 + flag 按 env 注入)

**Files:**
- Create: `backend/apps/exchanges/okx/__init__.py`, `backend/apps/exchanges/okx/adapter.py`, `backend/apps/exchanges/okx/mapping.py`
- Modify: `backend/apps/exchanges/apps.py`(ready() 里 `register_adapter("okx", OKXAdapter)`)
- Test: `backend/apps/exchanges/okx/test_adapter.py`

**Interfaces:**
- Consumes: `ExchangeAdapter`、`types`、`errors`(Task 4);`decrypt`(Task 3)。
- Produces: `OKXAdapter`,构造时按 `env` 决定 `flag`(SIM→"1"/LIVE→"0"),内部实例化 `okx.MarketData`、`okx.Account`、`okx.Trade` API;`get_ticker` 返回标准 `Ticker`。okx 网络调用在测试中用 monkeypatch 打桩,不真连网。

- [ ] **Step 1: 写测试(打桩,验证 flag 映射 + 返回标准结构)**

```python
from apps.exchanges.okx.adapter import OKXAdapter
from apps.exchanges.types import Env, Ticker

def test_flag_maps_from_env():
    assert OKXAdapter._flag_for(Env.SIM) == "1"
    assert OKXAdapter._flag_for(Env.LIVE) == "0"

def test_get_ticker_returns_standard(monkeypatch):
    a = OKXAdapter(credential=None, env=Env.SIM)
    monkeypatch.setattr(a, "_market", type("M", (), {
        "get_ticker": lambda self, instId: {"data":[{"last":"42000.5","ts":"1700000000000"}]}})())
    t = a.get_ticker("BTC-USDT")
    assert isinstance(t, Ticker) and t.last == 42000.5 and t.symbol == "BTC-USDT"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/pytest apps/exchanges/okx/test_adapter.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 adapter.py(骨架)**

```python
from apps.exchanges.base import ExchangeAdapter
from apps.exchanges.types import Env, Ticker, Capability
from apps.exchanges.errors import ExchangeError
from apps.credentials.crypto import decrypt

class OKXAdapter(ExchangeAdapter):
    capabilities = {Capability.SPOT, Capability.SWAP, Capability.OPTION}
    @staticmethod
    def _flag_for(env: Env) -> str: return "1" if env == Env.SIM else "0"
    def __init__(self, credential, env: Env):
        super().__init__(credential, env)
        flag = self._flag_for(env)
        from okx import MarketData, Account, Trade
        if credential is not None:
            key, secret, pph = credential.api_key, decrypt(credential.secret_enc), decrypt(credential.passphrase_enc)
        else:
            key = secret = pph = ""
        self._market = MarketData.MarketAPI(flag=flag)
        self._account = Account.AccountAPI(key, secret, pph, False, flag) if credential else None
        self._trade = Trade.TradeAPI(key, secret, pph, False, flag) if credential else None
    def get_ticker(self, symbol):
        d = self._market.get_ticker(instId=symbol)["data"][0]
        return Ticker(symbol=symbol, last=float(d["last"]), ts=int(d["ts"]))
    def get_candles(self, symbol, timeframe, limit=100): raise NotImplementedError  # P1 实现
    def get_balances(self): raise NotImplementedError  # P3 实现
    def get_positions(self): raise NotImplementedError  # P3 实现
    def place_order(self, req): raise NotImplementedError  # P2 实现
    def cancel_order(self, order_id): raise NotImplementedError  # P2 实现
```

> 说明:`get_candles/balances/positions/place_order/cancel_order` 在骨架期 `NotImplementedError`,由 P1/P2/P3 计划填充。这不是占位符——抽象契约已定义,只是分期实现,且已在 spec 排期中明确。

- [ ] **Step 4: apps.py ready() 注册**

```python
from django.apps import AppConfig
class ExchangesConfig(AppConfig):
    name = "apps.exchanges"
    def ready(self):
        from .okx.adapter import OKXAdapter
        from .factory import register_adapter
        register_adapter("okx", OKXAdapter)
```

- [ ] **Step 5: 运行测试通过,勾选完成**

Run: `cd backend && .venv/bin/pytest apps/exchanges/okx/test_adapter.py -v`
Expected: PASS。

---

### Task 6: 前端骨架(Vue3 毛玻璃壳 + 登录 + 密钥页 + 双语/双主题)

**Files:**
- Create: `frontend/package.json`, `vite.config.ts`, `index.html`, `tsconfig.json`
- Create: `frontend/src/main.ts`, `App.vue`, `src/router/index.ts`, `src/stores/auth.ts`, `src/api/client.ts`
- Create: `frontend/src/i18n/index.ts`, `src/i18n/zh-CN.ts`, `src/i18n/en-US.ts`
- Create: `frontend/src/styles/glass.css`
- Create: `frontend/src/layouts/GlassLayout.vue`
- Create: `frontend/src/views/Login.vue`, `Register.vue`, `Dashboard.vue`, `settings/Keys.vue`

**Interfaces:**
- Consumes: 后端 `/api/auth/*`、`/api/credentials/*`(Task 2/3)。
- Produces: 能登录、登录后进 Dashboard、能在 Keys 页增删查密钥(secret 不回显);一键中英切换 + 深浅主题切换,偏好存 localStorage。

- [ ] **Step 1: 初始化前端工程**

Run:
```bash
cd frontend && npm create vite@latest . -- --template vue-ts && \
npm install && npm install vue-router@4 pinia vue-i18n@9 axios
```
Expected: 依赖装好(node_modules 若跨机器拷贝需删掉重装)。

- [ ] **Step 2: 写毛玻璃基础样式 glass.css**

```css
:root[data-theme="dark"]{--glass-bg:rgba(28,28,34,.55);--glass-border:rgba(255,255,255,.12);--fg:#e8e8ed;--bg:#0b0b10}
:root[data-theme="light"]{--glass-bg:rgba(255,255,255,.55);--glass-border:rgba(0,0,0,.08);--fg:#1c1c1e;--bg:#f2f2f7}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,"SF Pro",system-ui,sans-serif}
.glass{background:var(--glass-bg);backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--glass-border);border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.18)}
```

- [ ] **Step 3: 写 i18n(zh-CN/en-US)+ 挂载**

```typescript
// zh-CN.ts
export default { login:{title:"登录",username:"用户名",password:"密码",submit:"登录"},
  nav:{dashboard:"资产总览",keys:"API 密钥"}, keys:{add:"新增密钥",secret:"Secret",passphrase:"Passphrase"} }
// en-US.ts
export default { login:{title:"Login",username:"Username",password:"Password",submit:"Sign in"},
  nav:{dashboard:"Dashboard",keys:"API Keys"}, keys:{add:"Add Key",secret:"Secret",passphrase:"Passphrase"} }
// i18n/index.ts
import { createI18n } from "vue-i18n"; import zhCN from "./zh-CN"; import enUS from "./en-US"
export default createI18n({ legacy:false, locale: localStorage.getItem("locale")||"zh-CN",
  messages:{ "zh-CN":zhCN, "en-US":enUS } })
```

- [ ] **Step 4: 写 api client(JWT 注入)+ auth store**

```typescript
// api/client.ts
import axios from "axios"
const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE || "/api" })
client.interceptors.request.use(c => { const t=localStorage.getItem("access"); if(t) c.headers.Authorization=`Bearer ${t}`; return c })
export default client
// stores/auth.ts
import { defineStore } from "pinia"; import client from "../api/client"
export const useAuth = defineStore("auth", { state:()=>({user:null as any}),
  actions:{ async login(username:string,password:string){ const r=await client.post("/auth/login",{username,password});
      localStorage.setItem("access",r.data.access); await this.fetchMe() },
    async fetchMe(){ const r=await client.get("/auth/me"); this.user=r.data } } })
```

- [ ] **Step 5: 写 router + GlassLayout + Login/Register/Dashboard/Keys 视图**

router 定义 `/login`、`/register`、`/dashboard`、`/settings/keys`,未登录守卫跳 `/login`。GlassLayout 含侧边栏(nav.dashboard/nav.keys)+ 顶栏(语言切换按钮 zh/en、主题切换按钮 dark/light,写 localStorage 并设 `document.documentElement.dataset.theme`)。Keys.vue 调 `/credentials` 列表 + 新增表单(api_key/secret/passphrase)+ 删除;列表只显示 api_key_masked。

- [ ] **Step 6: 构建 + 手动验证,勾选完成**

Run: `cd frontend && npm run build`
Expected: build 成功。手动:`npm run dev` 打开页面,注册→登录→进 Dashboard→Keys 页新增一条密钥→列表只见 `****后四位`、无 secret→切换中英/深浅主题生效→刷新后主题语言保持。

---

### Task 7: Docker Compose 全家桶(测试/生产共用,.env 区分)

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`, `frontend/Dockerfile`, `nginx/nginx.conf`
- Create: `.env.test`, `.env.example`
- Create: `backend/entrypoint.sh`

**Interfaces:**
- Consumes: backend(Task 1-5)、frontend(Task 6)。
- Produces: `docker compose --env-file .env.test up -d` 起 postgres/redis/influxdb/backend/nginx(前端静态),浏览器可访问登录页并完成 Task 6 的手动验证流程(这次跑在 postgres 上)。

- [ ] **Step 1: 写 backend/Dockerfile(多阶段,清华镜像)**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
```

- [ ] **Step 2: 写 entrypoint.sh(迁移 + gunicorn)**

```bash
#!/usr/bin/env bash
set -e
python manage.py migrate --noinput
gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 3
```

- [ ] **Step 3: 写 frontend/Dockerfile(多阶段 build → nginx 托管)+ nginx.conf**

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY ../nginx/nginx.conf /etc/nginx/conf.d/default.conf
```
nginx.conf:静态托管 + `/api` 反代 backend:8000 + `/ws` 反代 ws 服务(WS 服务 P1 加入,先预留)。

- [ ] **Step 4: 写 docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7
    volumes: [redisdata:/data]
  influxdb:
    image: influxdb:2.7
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: ${INFLUX_USER}
      DOCKER_INFLUXDB_INIT_PASSWORD: ${INFLUX_PASSWORD}
      DOCKER_INFLUXDB_INIT_ORG: quanly
      DOCKER_INFLUXDB_INIT_BUCKET: market
    volumes: [influxdata:/var/lib/influxdb2]
  backend:
    build: ./backend
    env_file: [.env.test]
    depends_on: [postgres, redis, influxdb]
  nginx:
    build: { context: ./frontend, dockerfile: Dockerfile }
    ports: ["8080:80"]
    depends_on: [backend]
volumes: { pgdata: {}, redisdata: {}, influxdata: {} }
```

- [ ] **Step 5: 写 .env.example / .env.test**

```
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
SECRET_ENCRYPTION_KEY=<Fernet.generate_key() 生成>
DB_ENGINE=django.db.backends.postgresql
DB_NAME=quanly
DB_USER=quanly
DB_PASSWORD=quanly-pass
DB_HOST=postgres
DB_PORT=5432
INFLUX_USER=quanly
INFLUX_PASSWORD=quanly-pass
```

- [ ] **Step 6: 一键起 + 端到端手动验证,勾选完成**

Run: `docker compose --env-file .env.test up -d --build`
Expected: 全部容器 healthy。浏览器开 `http://localhost:8080`,完成注册→登录→Keys 增删查(secret 隐藏)→主题/语言切换,数据落在 postgres,`docker compose down` 后 `up` 数据仍在。

---

## Self-Review

**Spec 覆盖(P0 骨架范围)**:
- Docker 全家桶 → Task 7 ✓(postgres/redis/influxdb/backend/nginx;celery/ws 属 P1+,已在预留)
- 多用户注册登录 → Task 2 ✓
- 密钥加密管理 → Task 3 ✓(Fernet、secret 不回显、api_key 后四位)
- 交易所抽象层 → Task 4 ✓(抽象基类+工厂+标准结构+能力声明)
- OKXAdapter 骨架 → Task 5 ✓(SDK 封装、flag 按 env 注入、上层不 import okx)
- 前端毛玻璃+双语+双主题 → Task 6 ✓
- env 隔离 → Task 3 模型带 env 字段 ✓;交易/资产/策略表在 P1+ 建

**占位符扫描**:Task 5 的 `NotImplementedError` 是分期实现的抽象契约(P1/P2/P3 填充),非计划占位符;已加说明。其余无 TBD/TODO。

**类型一致性**:`Env`(SIM/LIVE)在 credentials(Task3)与 exchanges(Task4)统一;`ExchangeAdapter` 抽象方法签名(Task4)与 `OKXAdapter` 实现(Task5)一致;前端 `/api/credentials` 字段(Task6)与后端 serializer(Task3)一致(api_key_masked)。

**边界说明**:本计划仅覆盖 P0。P1(行情/WS/InfluxDB 写入/Celery)、P2(交易)、P3(资产/账单)、P4(策略容器)、P5(回测)、P6(全品类前端)、P7(风控)各自后续单独出计划。
