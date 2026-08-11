#!/usr/bin/env bash
# 备份:PostgreSQL 逻辑导出 + InfluxDB 数据卷打包,保留最近 14 份。
# 复用 deploy/lib.sh(compose 固定用 .env.prod)。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE,请先运行:./quanly deploy"

TS="$(date +%Y%m%d-%H%M%S)"
OUT="backups"; mkdir -p "$OUT"
PROJECT="$(project_name)"

say "备份 PostgreSQL → $OUT/db-$TS.sql.gz"
compose exec -T postgres pg_dump -U quanly quanly | gzip > "$OUT/db-$TS.sql.gz"

say "备份 InfluxDB 数据卷 → $OUT/influx-$TS.tar.gz"
# 只挂载数据卷,tar 到 stdout 再由宿主机重定向落盘。
if docker run --rm -v "${PROJECT}_influxdata":/data alpine \
     tar czf - -C /data . > "$OUT/influx-$TS.tar.gz"; then
  :
else
  rm -f "$OUT/influx-$TS.tar.gz"
  warn "InfluxDB 卷备份失败(卷 ${PROJECT}_influxdata 可能不存在,可忽略)。"
fi

# 仅保留最近 14 份
ls -1t "$OUT"/db-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t "$OUT"/influx-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
say "备份完成:$TS"
