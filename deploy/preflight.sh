#!/usr/bin/env bash
# 环境自检:Docker 安装/运行、compose 可用、端口占用、OKX 连通。
# 硬性失败(Docker 相关)中止;软性(端口/OKX)仅警告。
# 可独立运行,也被 init/update 通过 `source` 调用。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

preflight() {
  say "环境自检…"

  command -v docker >/dev/null 2>&1 \
    || die "未检测到 Docker。请先安装 Docker Desktop:https://www.docker.com/products/docker-desktop/"

  docker info >/dev/null 2>&1 \
    || die "Docker 未运行。请启动 Docker Desktop 后重试。"

  docker compose version >/dev/null 2>&1 \
    || die "docker compose 不可用。请升级到较新版 Docker Desktop。"

  # 端口占用(软性):本地查 8080;服务器查 80/443
  local mode="${QUANLY_MODE:-local}"
  local ports
  if [ "$mode" = "server" ]; then ports="80 443"; else ports="8080"; fi
  for p in $ports; do
    if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "端口 $p 已被占用(若是本项目自身在跑可忽略)。"
    fi
  done

  # OKX 连通(软性)
  if command -v curl >/dev/null 2>&1; then
    if ! curl -s --max-time 8 https://www.okx.com/api/v5/public/time >/dev/null 2>&1; then
      warn "无法连接 OKX(www.okx.com)。行情与交易将不可用,可能需要代理或检查网络。"
    fi
  fi

  say "自检完成。"
}

# 独立运行时执行 preflight;被 source 时仅定义函数
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  preflight
fi
