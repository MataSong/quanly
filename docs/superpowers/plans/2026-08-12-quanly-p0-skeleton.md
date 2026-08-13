# Quanly P0 骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 立起 quanly 平台底座——Django 5 + DRF 后端（含对标 ops_hub 的完整 RBAC）+ Vue 3 + Element Plus 前端壳（AppShell 布局 + 中英文 i18n + 登录）+ PostgreSQL + Docker 全家桶一键起，端到端跑通「注册 → 登录 → 拿到有效权限 → 进入仪表盘 → 切换语言 → 登出」。

**Architecture:** 前后端分离。后端 Django 5 + DRF + SimpleJWT，自研 RBAC（权限点注册表 + Role + 用户级 grant/deny 覆盖 + 双闸门），分层复刻 ops_hub（`core/auth`、`core/accounts`）。前端 Vue 3 + TS + Vite + Element Plus + Pinia + vue-i18n，布局/主题/i18n/权限守卫全面复刻 ops_hub。全部容器化，docker-compose 编排 postgres + redis + backend + frontend + nginx（P0 先不含 celery/ws，下一层加）。

**Tech Stack:** Django 5, DRF, djangorestframework-simplejwt, PostgreSQL, psycopg, Vue 3, TypeScript, Vite 5, Element Plus 2.7, Pinia, Vue Router 4, vue-i18n 9, axios, Docker, docker-compose, nginx。

**参考范本（实现时逐个打开对照，1:1 复刻风格）：** `/Users/C5386931/Project/ops_hub/`
- 后端 RBAC：`backend/core/accounts/{models,permissions_registry,services,drf,views,urls,serializers}.py`
- 后端认证：`backend/core/auth/{views,serializers,urls}.py`、`backend/config/settings/base.py`（SIMPLE_JWT 段）
- 前端布局：`frontend/src/layouts/AppShell.vue`、`frontend/src/styles/tokens.scss`
- 前端 i18n：`frontend/src/locales/{index.ts,zh-CN.ts,en-US.ts}`、`frontend/src/stores/locale.ts`、`frontend/src/components/LocaleSwitcher.vue`
- 前端权限：`frontend/src/router/{index,guards}.ts`、`frontend/src/stores/auth.ts`、`frontend/src/api/http.ts`

## Global Constraints

- **严禁任何 git 操作**：不 `git add` / `commit` / `push`。本计划所有任务末尾用「阶段验证 / 存盘检查点」代替提交，绝不出现 git 命令。
- **数据库统一 PostgreSQL**，禁止 SQLite。
- **全 Docker 化**：任何服务都必须能在 docker-compose 里起；本机开发也走容器。
- **前端所有用户可见文案走 i18n key**，禁止硬编码中文；zh-CN.ts 与 en-US.ts 键必须完全对齐。
- **权限校验以后端为准**，前端隐藏仅体验优化。
- **RBAC 颗粒度对标 ops_hub**：权限点随代码硬编码，管理员只分配不新造。
- **依赖安装**：PyPI 用清华镜像（`-i https://pypi.tuna.tsinghua.edu.cn/simple`）；venv 无 pip 时用 `uv`；前端换机重新 `npm ci`。
- **代码写抽象**，为后续策略/行情/交易板块预留扩展点（权限点分组、app 分层）。

---

## 文件结构

```
quanly/
  docker-compose.yml            # postgres + redis + backend + frontend + nginx
  .env.example                  # 所有环境变量样例
  backend/
    Dockerfile
    requirements.txt
    manage.py
    pytest.ini
    config/
      __init__.py
      settings/
        __init__.py             # 按 QUANLY_ENV 选 dev/prod/test
        base.py                 # 共用配置(DRF/SIMPLE_JWT/DATABASES=PG/apps)
        dev.py  prod.py  test.py
      urls.py                   # /api/* + SPA catch-all
      asgi.py  wsgi.py
    core/
      __init__.py
      auth/                     # 登录/登出/Me
        __init__.py apps.py views.py serializers.py urls.py
      accounts/                 # RBAC
        __init__.py apps.py models.py permissions_registry.py
        services.py drf.py views.py serializers.py urls.py
        migrations/__init__.py
      audit/                    # @audit + AuditLog(P0 建骨架)
        __init__.py apps.py models.py decorators.py migrations/__init__.py
    tests/
      __init__.py conftest.py
      test_accounts.py test_auth.py
  frontend/
    Dockerfile
    package.json tsconfig.json vite.config.ts index.html
    src/
      main.ts App.vue
      api/http.ts
      stores/{auth.ts,locale.ts}
      locales/{index.ts,zh-CN.ts,en-US.ts}
      layouts/AppShell.vue
      components/{LocaleSwitcher.vue,BrandLogo.vue}
      router/{index.ts,guards.ts}
      styles/{tokens.scss,base.scss}
      views/{Login.vue,Dashboard.vue,admin/{UserPanel.vue,RolePanel.vue,PermissionAdmin.vue}}
  nginx/
    default.conf                # 反代 /api 到 backend，托管前端，预留 /ws
```

---

## 权限点清单（P0 固定，硬编码在 permissions_registry.py）

```python
PERMISSIONS = {
    # page:* 页面可见性
    "page:dashboard": "查看仪表盘",
    "page:admin":     "查看权限管理",
    # 后续板块的 page:* 与 CRUD 权限点在各自阶段加入
    # (market/strategy/backtest/trading/credentials)
}
```
P0 只落 `page:dashboard` 和 `page:admin` 两个页面权限点 + 用户管理相关（用户/角色管理属超管，用 IsSuperUser 闸门，不单列权限码）。后续板块阶段再往这个 dict 里加权限点——这是预留的扩展点。

---

### Task 1: 后端工程骨架 + PostgreSQL + Django 起得来

**Files:**
- Create: `backend/requirements.txt`, `backend/manage.py`, `backend/pytest.ini`
- Create: `backend/config/__init__.py`, `backend/config/settings/{__init__,base,dev,prod,test}.py`, `backend/config/{urls,asgi,wsgi}.py`
- Create: `backend/tests/{__init__,conftest}.py`

**Interfaces:**
- Produces: Django project `config`，`QUANLY_ENV` 环境变量切换 settings；`DATABASES.default` = PostgreSQL（从 env 读 `POSTGRES_*`）；DRF 默认认证 `JWTAuthentication`、默认权限 `IsAuthenticated`；已装 `rest_framework`、`rest_framework_simplejwt`、`rest_framework_simplejwt.token_blacklist`、`corsheaders`。

- [ ] **Step 1: 写 requirements.txt**

```
Django>=5.0,<5.1
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
psycopg[binary]>=3.1
django-cors-headers>=4.3
cryptography>=42
pytest>=8
pytest-django>=4.8
```

- [ ] **Step 2: 写 config/settings/base.py**（关键段，参照 ops_hub base.py）

包含：`INSTALLED_APPS`（django 内置 + rest_framework + token_blacklist + corsheaders + core.auth + core.accounts + core.audit）；`DATABASES.default` 用 `django.db.backends.postgresql`，host/name/user/password/port 全读 `os.environ`；`REST_FRAMEWORK` 设 `DEFAULT_AUTHENTICATION_CLASSES=[JWTAuthentication]`、`DEFAULT_PERMISSION_CLASSES=[IsAuthenticated]`；`SIMPLE_JWT` 设 `ACCESS_TOKEN_LIFETIME=timedelta(minutes=30)`、`REFRESH_TOKEN_LIFETIME=timedelta(days=7)`、`ROTATE_REFRESH_TOKENS=True`、`BLACKLIST_AFTER_ROTATION=True`；`SECRET_KEY`/`ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` 读 env。`settings/__init__.py` 按 `QUANLY_ENV`（默认 dev）导入对应模块。`test.py` 可用独立测试库名。

- [ ] **Step 3: 写 config/urls.py**

`/api/accounts/` include `core.accounts.urls`、`/api/auth/` include `core.auth.urls`；末尾 SPA catch-all（`frontend_dist/index.html` 存在时 TemplateView 托管，否则跳过）。

- [ ] **Step 4: 写 manage.py / asgi.py / wsgi.py / pytest.ini / conftest.py**

`pytest.ini` 设 `DJANGO_SETTINGS_MODULE=config.settings.test`、`python_files=test_*.py`。`conftest.py` 提供 `api_client`（DRF APIClient）fixture。

- [ ] **Step 5: 起 PostgreSQL 容器并验证 Django 能连库**

Run:
```
docker run -d --name quanly-pg-tmp -e POSTGRES_PASSWORD=quanly -e POSTGRES_DB=quanly -p 5433:5432 postgres:16
cd backend && QUANLY_ENV=dev POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=quanly POSTGRES_USER=postgres POSTGRES_PASSWORD=quanly python manage.py migrate
```
Expected: migrate 成功，无报错，可见 `Applying ...` 输出。

- [ ] **Step 6: 存盘检查点**

确认 `python manage.py check` 无 error；PG 容器可连。记录到本任务已完成。（不提交 git）

---

### Task 2: RBAC 数据模型 + 权限点注册表 + 有效权限合成

**Files:**
- Create: `backend/core/accounts/{__init__,apps}.py`
- Create: `backend/core/accounts/models.py`
- Create: `backend/core/accounts/permissions_registry.py`
- Create: `backend/core/accounts/services.py`
- Test: `backend/tests/test_accounts.py`

**Interfaces:**
- Consumes: Task 1 的 Django 工程与 PG。
- Produces:
  - 模型 `Role(name:str, permissions:JSONField=list, is_system:bool)`、`UserRole(user FK, role FK)`、`UserPermissionOverride(user FK, permission:str, effect:str∈{grant,deny}, unique(user,permission))`、`UserProfile(user OneToOne, auth_source:str∈{local,sso}='local', external_id:str='')`。
  - `permissions_registry.PERMISSIONS: dict[str,str]`、`ALL_PERMISSION_CODES: set[str]`。
  - `services.get_effective_permissions(user) -> set[str]`：superuser 返回 `ALL_PERMISSION_CODES`；否则「角色 permissions 并集 → 加 grant override → 减 deny override → 与 ALL_PERMISSION_CODES 取交集」。
  - `services.get_effective_permissions_cached(request) -> set[str]`：挂 `request._perm_cache`。

- [ ] **Step 1: 写失败测试 test_accounts.py**

```python
import pytest
from django.contrib.auth.models import User
from core.accounts.models import Role, UserRole, UserPermissionOverride
from core.accounts.services import get_effective_permissions
from core.accounts.permissions_registry import ALL_PERMISSION_CODES

@pytest.mark.django_db
def test_superuser_gets_all_permissions():
    u = User.objects.create_superuser("root", "r@x.com", "pw")
    assert get_effective_permissions(u) == ALL_PERMISSION_CODES

@pytest.mark.django_db
def test_role_union_then_override():
    u = User.objects.create_user("alice", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard"])
    UserRole.objects.create(user=u, role=role)
    UserPermissionOverride.objects.create(user=u, permission="page:admin", effect="grant")
    perms = get_effective_permissions(u)
    assert "page:dashboard" in perms
    assert "page:admin" in perms

@pytest.mark.django_db
def test_deny_override_removes_role_permission():
    u = User.objects.create_user("bob", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard", "page:admin"])
    UserRole.objects.create(user=u, role=role)
    UserPermissionOverride.objects.create(user=u, permission="page:admin", effect="deny")
    perms = get_effective_permissions(u)
    assert "page:dashboard" in perms
    assert "page:admin" not in perms

@pytest.mark.django_db
def test_invalid_permission_code_filtered_out():
    u = User.objects.create_user("carol", password="pw")
    role = Role.objects.create(name="x", permissions=["page:dashboard", "bogus:perm"])
    UserRole.objects.create(user=u, role=role)
    assert "bogus:perm" not in get_effective_permissions(u)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && QUANLY_ENV=test POSTGRES_* ... pytest tests/test_accounts.py -v`
Expected: FAIL（ImportError / 模型不存在）。

- [ ] **Step 3: 写 permissions_registry.py**

```python
PERMISSIONS = {
    "page:dashboard": "查看仪表盘",
    "page:admin": "查看权限管理",
}
ALL_PERMISSION_CODES = set(PERMISSIONS.keys())
```

- [ ] **Step 4: 写 models.py**（参照 ops_hub accounts/models.py，字段见 Interfaces）+ 生成迁移

Run: `python manage.py makemigrations accounts`

- [ ] **Step 5: 写 services.py**

```python
from .permissions_registry import ALL_PERMISSION_CODES

def get_effective_permissions(user):
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSION_CODES)
    perms = set()
    for ur in user.userrole_set.select_related("role").all():
        perms |= set(ur.role.permissions or [])
    for ov in user.userpermissionoverride_set.all():
        if ov.effect == "grant":
            perms.add(ov.permission)
        elif ov.effect == "deny":
            perms.discard(ov.permission)
    return perms & set(ALL_PERMISSION_CODES)

def get_effective_permissions_cached(request):
    if not hasattr(request, "_perm_cache"):
        request._perm_cache = get_effective_permissions(request.user)
    return request._perm_cache
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_accounts.py -v`
Expected: 4 passed。

- [ ] **Step 7: 存盘检查点**（不提交 git）

---

### Task 3: 后端权限双闸门（HasRequiredPermissions + require_perm）

**Files:**
- Create: `backend/core/accounts/drf.py`
- Test: 追加到 `backend/tests/test_accounts.py`

**Interfaces:**
- Consumes: Task 2 的 `get_effective_permissions_cached`。
- Produces:
  - `HasRequiredPermissions(BasePermission)`：读 `view.required_permissions`（可为 `list[str]` 或 `dict[method,list[str]]`），校验用户有效权限包含所需全部。
  - `require_perm(request, code:str)`：无权限抛 DRF `PermissionDenied`（403）。

- [ ] **Step 1: 写失败测试**

```python
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework.response import Response
from core.accounts.drf import HasRequiredPermissions

class _View(APIView):
    permission_classes = [HasRequiredPermissions]
    required_permissions = ["page:admin"]
    def get(self, request): return Response({"ok": True})

@pytest.mark.django_db
def test_permission_denied_without_perm(api_client):
    u = User.objects.create_user("nop", password="pw")
    api_client.force_authenticate(u)
    # 需将 _View 挂到临时路由或直接调 has_permission
```
（实现者可用 `HasRequiredPermissions().has_permission(request, view)` 直接单测，避免临时路由。）

- [ ] **Step 2: 跑测试确认失败** — Expected: ImportError。

- [ ] **Step 3: 写 drf.py**（参照 ops_hub accounts/drf.py）

```python
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from .services import get_effective_permissions_cached

class HasRequiredPermissions(BasePermission):
    def has_permission(self, request, view):
        required = getattr(view, "required_permissions", None)
        if not required:
            return True
        if isinstance(required, dict):
            required = required.get(request.method, [])
        perms = get_effective_permissions_cached(request)
        return all(code in perms for code in required)

def require_perm(request, code):
    if code not in get_effective_permissions_cached(request):
        raise PermissionDenied(f"缺少权限: {code}")
```

- [ ] **Step 4: 跑测试确认通过** — Expected: passed。
- [ ] **Step 5: 存盘检查点**（不提交 git）

---

### Task 4: 认证 API（登录 / 登出 / Me，登录响应内联权限）

**Files:**
- Create: `backend/core/auth/{__init__,apps,views,serializers,urls}.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: Task 2 services、SimpleJWT。
- Produces:
  - `POST /api/auth/`：body `{username,password}` → `{access, refresh, user}`，`user` 含 `id,username,is_superuser,permissions(list),auth_source`。
  - `POST /api/auth/logout/`：body `{refresh}` → refresh 加黑名单，204。
  - `GET /api/auth/me/`：返回当前 user（同上结构）。

- [ ] **Step 1: 写失败测试 test_auth.py**

```python
@pytest.mark.django_db
def test_login_returns_tokens_and_permissions(api_client):
    User.objects.create_user("alice", password="pw123456")
    resp = api_client.post("/api/auth/", {"username": "alice", "password": "pw123456"}, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert "permissions" in resp.data["user"]

@pytest.mark.django_db
def test_me_requires_auth(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401
```

- [ ] **Step 2: 跑测试确认失败** — Expected: 404/ImportError。

- [ ] **Step 3: 写 serializers.py + views.py + urls.py**（参照 ops_hub auth）

`UserSerializer` 输出 `id,username,is_superuser,auth_source,permissions`（permissions 用 `list(get_effective_permissions(user))`）。`LoginView` 校验账号密码 → 签发 token + UserSerializer。`LogoutView` 把 refresh 加黑名单。`MeView`（IsAuthenticated）返回 UserSerializer。

- [ ] **Step 4: 跑测试确认通过** — Expected: passed。
- [ ] **Step 5: 存盘检查点**（不提交 git）

---

### Task 5: 用户 / 角色管理 API（超管专属）

**Files:**
- Create: `backend/core/accounts/{serializers,views,urls}.py`
- Create: `backend/core/audit/{__init__,apps,models,decorators}.py` + migrations
- Test: 追加 `backend/tests/test_accounts.py`

**Interfaces:**
- Consumes: Task 2/3。
- Produces（挂 `/api/accounts/`，权限 `IsAuthenticated + IsSuperUser`）：
  - `RoleViewSet`（`roles/` CRUD）。
  - `UserViewSet`（`users/` 列表/详情 + actions：`roles`(设角色)、`set_active`、`reset_password`(≥8位)、`overrides`(增/查)、`delete_override`）。删除保护：不能删超管、不能删自己。
  - `PermissionsListView`（`permissions/`）返回 `PERMISSIONS` 清单供前端渲染。
  - `@audit(action)` 装饰器 + `AuditLog(user,action,detail,created_at)` 模型，写操作挂 `@audit`。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.django_db
def test_non_superuser_cannot_list_users(api_client):
    u = User.objects.create_user("plain", password="pw123456")
    api_client.force_authenticate(u)
    assert api_client.get("/api/accounts/users/").status_code == 403

@pytest.mark.django_db
def test_superuser_can_list_users(api_client):
    su = User.objects.create_superuser("root", "r@x.com", "pw123456")
    api_client.force_authenticate(su)
    assert api_client.get("/api/accounts/users/").status_code == 200

@pytest.mark.django_db
def test_permissions_list_endpoint(api_client):
    su = User.objects.create_superuser("root2", "r@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.get("/api/accounts/permissions/")
    assert resp.status_code == 200
    assert "page:dashboard" in str(resp.data)
```

- [ ] **Step 2: 跑测试确认失败** — Expected: 404。
- [ ] **Step 3: 写 audit 模型 + decorators.py**（`@audit` 记录 user/action/detail）+ makemigrations。
- [ ] **Step 4: 写 serializers.py + views.py + urls.py**（参照 ops_hub accounts/views.py，含删除保护 + @audit）。
- [ ] **Step 5: 跑测试确认通过** — Expected: passed。
- [ ] **Step 6: 存盘检查点**（不提交 git）

---

### Task 6: 前端工程骨架 + Element Plus + 主题令牌

**Files:**
- Create: `frontend/{package.json,tsconfig.json,vite.config.ts,index.html}`
- Create: `frontend/src/{main.ts,App.vue}`
- Create: `frontend/src/styles/{tokens.scss,base.scss}`
- Create: `frontend/src/components/BrandLogo.vue`

**Interfaces:**
- Produces: Vue3+TS+Vite 工程，`@` 别名指向 `src`，dev server 代理 `/api` 到 backend。`main.ts` 依次 `use(pinia)`、`use(router)`、`use(i18n)`、`use(ElementPlus)`。tokens.scss 复刻 ops_hub 紫青主题变量。

- [ ] **Step 1: 写 package.json**（依赖：vue^3.4、element-plus^2.7、@element-plus/icons-vue、pinia^2.1、vue-router^4.3、vue-i18n^9.14、axios^1.6、sass；devDeps：vite^5.2、@vitejs/plugin-vue^5、typescript^5.4、vue-tsc）。
- [ ] **Step 2: 写 tsconfig.json + vite.config.ts**（`@`→src，server.proxy `/api`→`http://backend:8000` 或本机 `localhost:8000`）。
- [ ] **Step 3: 复刻 tokens.scss**（从 ops_hub 拷贝 `--brand-primary:#635bff` 等全套 CSS 变量）+ base.scss。
- [ ] **Step 4: 写 index.html + main.ts + App.vue + BrandLogo.vue**（App.vue 只放 `<router-view/>`）。
- [ ] **Step 5: 验证 `npm ci && npm run build` 通过** — Expected: 产出 `dist/`。（依赖装不动用清华 npm 镜像）
- [ ] **Step 6: 存盘检查点**（不提交 git）

---

### Task 7: 前端 i18n（中英文，键完全对齐）

**Files:**
- Create: `frontend/src/locales/{index.ts,zh-CN.ts,en-US.ts}`
- Create: `frontend/src/stores/locale.ts`
- Create: `frontend/src/components/LocaleSwitcher.vue`

**Interfaces:**
- Consumes: Task 6 工程。
- Produces: `i18n`（vue-i18n，legacy:false，locale 默认 zh-CN）；`t(key,named?)` 便捷函数；`useLocaleStore()`（`setLocale()` 更新 i18n + 持久化 localStorage `quanly:locale` + 联动 Element Plus 语言包 + 设 `document.documentElement.lang`）；`<LocaleSwitcher>` 中文/EN 切换。

- [ ] **Step 1: 复刻 locales/index.ts**（createI18n legacy:false，messages zh-CN/en-US）。
- [ ] **Step 2: 写 zh-CN.ts / en-US.ts**（P0 覆盖：common、login、layout、dashboard、admin 分组的所有文案；**两侧键完全对齐**）。
- [ ] **Step 3: 复刻 stores/locale.ts + LocaleSwitcher.vue**。
- [ ] **Step 4: 验证键对齐**

Run: 写一个临时脚本或 `vue-tsc --noEmit` 确认无缺键；或人工比对 zh/en 键集合相等。
Expected: 键集合完全一致。

- [ ] **Step 5: 存盘检查点**（不提交 git）

---

### Task 8: 前端 axios 封装 + auth store + 路由 + 权限守卫

**Files:**
- Create: `frontend/src/api/http.ts`
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/router/{index.ts,guards.ts}`

**Interfaces:**
- Consumes: Task 4 的 `/api/auth/*`。
- Produces:
  - `http`：axios 实例，请求拦截注入 `Authorization: Bearer <access>`，401 时用 refresh 刷新或跳登录。
  - `useAuthStore()`：state `access/refresh/user`（持久化 localStorage `quanly_access/refresh/user`）；actions `login()/logout()/fetchMe()`；getter `hasPerm(code)`（superuser 全放通，否则查 `user.permissions`）。
  - 路由：`/login`(Login)、`/`(AppShell 布局，children：`dashboard` meta.perm=`page:dashboard`、`admin/users`|`admin/roles`|`admin/permissions` meta.perm=`page:admin`）。
  - `guards.ts`：`beforeEach` 未登录跳 `/login`；已登录访问无 `meta.perm` 权限的页 → 跳第一个有权限的页（`firstAllowed()`）。

- [ ] **Step 1: 复刻 http.ts**（拦截器 + 刷新逻辑，参照 ops_hub）。
- [ ] **Step 2: 复刻 stores/auth.ts**（含 hasPerm）。
- [ ] **Step 3: 写 router/index.ts（路由表 + meta.perm）+ guards.ts**。
- [ ] **Step 4: 验证 `npm run build` 通过** — Expected: 无类型错误。
- [ ] **Step 5: 存盘检查点**（不提交 git）

---

### Task 9: 前端 AppShell 布局 + 登录页 + 仪表盘 + 权限管理页

**Files:**
- Create: `frontend/src/layouts/AppShell.vue`
- Create: `frontend/src/views/Login.vue`
- Create: `frontend/src/views/Dashboard.vue`
- Create: `frontend/src/views/admin/{UserPanel.vue,RolePanel.vue,PermissionAdmin.vue}`

**Interfaces:**
- Consumes: Task 5 的 `/api/accounts/*`、Task 7 i18n、Task 8 auth store/router。
- Produces:
  - `AppShell.vue`：复刻 ops_hub——CSS Grid（深色顶栏 56px + 白色可折叠侧边栏 240px + 内容区独立滚动）；顶栏含 BrandLogo + LocaleSwitcher + 用户下拉（登出）；侧边栏菜单按 `hasPerm(page:*)` 过滤；折叠状态存 localStorage。
  - `Login.vue`：用户名/密码登录，调 auth.login，成功跳 firstAllowed。
  - `Dashboard.vue`：P0 占位（欢迎 + 用户名 + 权限数），后续阶段接资产看板。
  - admin 三页：UserPanel（用户列表 + 设角色/启停/重置密码/覆盖）、RolePanel（角色 CRUD + 勾权限点）、PermissionAdmin（权限点清单只读展示）。

- [ ] **Step 1: 复刻 AppShell.vue**（布局 + 菜单权限过滤 + 折叠 + 顶栏组件）。
- [ ] **Step 2: 写 Login.vue**（Element Plus 表单，走 auth store，文案用 i18n）。
- [ ] **Step 3: 写 Dashboard.vue 占位**。
- [ ] **Step 4: 写 admin 三页**（DataTable 风格对齐 ops_hub，调 /api/accounts/*）。
- [ ] **Step 5: 验证 `npm run build` 通过** — Expected: 无错误。
- [ ] **Step 6: 存盘检查点**（不提交 git）

---

### Task 10: Docker 全家桶 + nginx + 端到端验收

**Files:**
- Create: `backend/Dockerfile`, `frontend/Dockerfile`
- Create: `docker-compose.yml`, `.env.example`, `nginx/default.conf`

**Interfaces:**
- Consumes: 全部前置任务。
- Produces: `docker compose up --build` 起 postgres + redis + backend(gunicorn) + frontend(build 产物) + nginx；nginx 反代 `/api`→backend、托管前端 SPA、预留 `/ws`。种子超管账号（management command 或 compose 启动脚本，账号 `admin` / 密码从 env，或复刻 ops_hub 的 seed 脚本）。

- [ ] **Step 1: 写 backend/Dockerfile**（python:3.12-slim，pip 用清华镜像装 requirements，`collectstatic` + gunicorn 起 `config.wsgi`）。
- [ ] **Step 2: 写 frontend/Dockerfile**（多阶段：node build → 产物给 nginx 或拷进 backend `frontend_dist`）。P0 用「Django 托管 SPA」或「nginx 单独托管」二选一，推荐 nginx 托管更清晰。
- [ ] **Step 3: 写 nginx/default.conf**（`location /api`→backend:8000，`location /ws`→预留，`location /` 托管前端 dist，try_files SPA fallback）。
- [ ] **Step 4: 写 docker-compose.yml**（postgres:16 带 volume、redis:7、backend、frontend/nginx；env 从 `.env`；backend `depends_on` postgres）+ `.env.example`。
- [ ] **Step 5: 写种子超管命令**（`python manage.py seed_admin` 读 env 建超管 + 一个内置 `admin` 系统角色含全部权限）。
- [ ] **Step 6: 一键起 + 端到端验收**

Run: `docker compose --env-file .env up -d --build`，然后浏览器/curl 验证：
1. 访问前端首页 → 跳登录页
2. 用种子超管登录 → 拿到 token + 全部权限
3. 进入仪表盘 → 显示用户名 + 权限数
4. 切换中/英文 → 界面文案切换，刷新后保持
5. 进入权限管理 → 看到用户列表、角色、权限点清单
6. 新建一个普通角色 + 普通用户，赋 `page:dashboard`，用它登录 → 只能看到仪表盘，看不到权限管理菜单，直接访问 `/admin/users` 被守卫拦回
7. 登出 → 回登录页，token 清除
8. `docker compose down && up` → 数据仍在（PG volume 持久化）

Expected: 以上 8 条全通过。

- [ ] **Step 7: 存盘检查点 + 更新项目记忆**（记录 P0 完成状态，不提交 git）

---

## Self-Review（对照 spec 检查）

- **spec §3.3/§3.4 用户管理 RBAC** → Task 2/3/4/5/9 覆盖（权限点注册表、Role/Override、双闸门、认证、管理 API、前端守卫与管理页）。✓
- **spec §3.1/§3.2 前端 + i18n** → Task 6/7/8/9（Vue3+EP+主题、i18n 双语对齐、路由守卫、AppShell）。✓
- **spec §3.5 PostgreSQL** → Task 1（DATABASES=PG）+ Task 10（compose postgres）。✓
- **spec §3.6 全 Docker** → Task 10。✓
- **Global Constraints 严禁 git** → 全任务用「存盘检查点」代替 commit，无 git 命令。✓
- **权限点扩展性** → permissions_registry 是单一 dict，后续板块阶段往里加即可（已在文档注明）。✓
- **P0 不含内容**：OKX/策略/行情/交易/回测/Celery/Channels 均不在 P0，留待后续阶段。✓（下一阶段计划：P1 OKX 密钥管理 + 行情。）

## 下一阶段预告（P0 验收通过后再写详细计划）
- **P1**：OKX 密钥管理（Fernet 加密，带 env sim/live）+ 行情（python-okx 拉现货 K 线 + Channels WS 推前端 + Lightweight Charts）。
- **P2**：交易/下单到 OKX（虚拟盘/实盘双 flag）+ 订单/持仓监控。
- **P3**：策略容器（Celery worker + Docker 隔离 + RUN_TOKEN 策略专用 API）+ 1 个内置策略。
- **P4**：回测引擎 + 指标 + 净值曲线。
- **P5**：资产看板聚合。
