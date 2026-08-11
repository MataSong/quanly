#!/usr/bin/env bash
# Quanly 统一入口。用法:./quanly <子命令>
#   deploy    一键部署(首次自动初始化;之后自动热更新)
#   backup    备份数据库与时序数据
#   restore   从备份恢复数据库:./quanly restore <file>
#   status    查看各服务运行状态
#   logs      跟踪日志:./quanly logs [服务名]
#   help      显示本帮助
set -euo pipefail
cd "$(dirname "$0")"
source deploy/lib.sh

usage() {
  cat <<'EOF'
Quanly 部署工具。用法: ./quanly <子命令>

  deploy          一键部署(无配置→首次初始化并拉起;已部署→git pull 热更新)
  backup          备份 PostgreSQL 与 InfluxDB
  restore <file>  从指定备份恢复数据库
  status          查看各服务运行状态
  logs [服务名]   跟踪日志(省略服务名则全部)
  help            显示本帮助
EOF
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
  deploy|init|update)  bash deploy/deploy.sh "$@" ;;
  backup)  bash deploy/backup.sh "$@" ;;
  restore) bash deploy/restore.sh "$@" ;;
  status)
    compose ps
    ;;
  logs)
    compose logs -f --tail=100 "$@"
    ;;
  help|--help|-h) usage ;;
  *) warn "未知子命令: $cmd"; usage; exit 1 ;;
esac
