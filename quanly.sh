#!/usr/bin/env bash
# Quanly 统一入口。用法:./quanly <子命令>
#   init      初始化部署(首次或重新拉起)
#   update    热更新(拉代码 + 只重建变更镜像)
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

  init            初始化部署(首次生成配置并拉起;已部署则重新拉起)
  update          热更新(git pull + 只重建变更的镜像 + 按需迁移)
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
  init)    bash deploy/init.sh "$@" ;;
  update)  bash deploy/update.sh "$@" ;;
  backup)  bash deploy/backup.sh "$@" ;;
  restore) bash deploy/restore.sh "$@" ;;
  status)
    load_mode
    compose ps
    ;;
  logs)
    load_mode
    compose logs -f --tail=100 "$@"
    ;;
  help|--help|-h) usage ;;
  *) warn "未知子命令: $cmd"; usage; exit 1 ;;
esac
