#!/usr/bin/env bash
# 恢复:从指定 db 备份还原 PostgreSQL(会覆盖当前库,需二次确认)。
# 复用 deploy/lib.sh(compose 按 QUANLY_MODE 选择,不再硬编码 prod)。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE,请先运行:./quanly init"
load_mode

DB_DUMP="${1:-}"
[ -z "$DB_DUMP" ] && die "用法:./quanly restore backups/db-YYYYmmdd-HHMMSS.sql.gz"
[ -f "$DB_DUMP" ] || die "找不到备份文件:$DB_DUMP"

read -rp "将覆盖当前数据库,确认?(输入 yes 继续) " ok
[ "$ok" = "yes" ] || { say "已取消。"; exit 0; }

say "恢复数据库 from $DB_DUMP …"
gunzip -c "$DB_DUMP" | compose exec -T postgres psql -U quanly quanly
say "恢复完成。正在重启后端…"
compose restart backend ws
say "完成。"
