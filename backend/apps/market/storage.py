from django.conf import settings
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

_client = None
_write_api = None


def _get_write_api():
    global _client, _write_api
    if _write_api is None:
        _client = InfluxDBClient(
            url=settings.INFLUX_URL,
            token=settings.INFLUX_TOKEN,
            org=settings.INFLUX_ORG,
        )
        _write_api = _client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def write_candle(symbol: str, bar: str, ts_ms: int, o, h, l, c, vol):
    point = (
        Point("candle")
        .tag("symbol", symbol)
        .tag("bar", bar)
        .field("o", float(o))
        .field("h", float(h))
        .field("l", float(l))
        .field("c", float(c))
        .field("v", float(vol))
        .time(int(ts_ms), WritePrecision.MS)
    )
    _get_write_api().write(bucket=settings.INFLUX_BUCKET, record=point)
