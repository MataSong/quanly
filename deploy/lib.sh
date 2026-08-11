#!/usr/bin/env bash
# 公共函数库:被 quanly.sh 与 deploy/*.sh 通过 `source` 引入,不单独执行。
# 提供:彩色输出、密钥生成、compose 命令(固定 .env.prod)、项目名。

# --- 彩色输出 ---
_c_red='\033[0;31m'; _c_yel='\033[0;33m'; _c_grn='\033[0;32m'; _c_rst='\033[0m'
say()  { printf "${_c_grn}==>${_c_rst} %s\n" "$*"; }
warn() { printf "${_c_yel}[!]${_c_rst} %s\n" "$*" >&2; }
die()  { printf "${_c_red}[x]${_c_rst} %s\n" "$*" >&2; exit 1; }

# --- 项目名(compose 卷前缀,取当前目录名规整为小写字母数字) ---
project_name() { basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9'; }

# --- 密钥生成 ---
gen_secret() { openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-50; }
gen_hex()    { openssl rand -hex 16; }
gen_fernet() {
  python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())' 2>/dev/null \
    || docker run --rm python:3.13-slim sh -c \
       'pip -q install cryptography >/dev/null 2>&1 && python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"'
}

# --- compose 命令(固定用 .env.prod,单一 docker-compose.yml) ---
# 用法:compose ps  /  compose up -d --build
ENV_FILE="${ENV_FILE:-.env.prod}"
compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

# --- 从 .env.prod 读取某个键的值(不存在返回空) ---
env_get() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  grep "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2-
}
