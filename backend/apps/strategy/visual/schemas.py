"""可视化策略参数 schema:前端据此渲染表单,后端据此校验。"""

SCHEMAS = {
    "ma_cross": [
        {"name": "short", "type": "int", "default": 3, "min": 1, "max": 200, "label_key": "strategy.visual.f.short"},
        {"name": "long", "type": "int", "default": 10, "min": 2, "max": 400, "label_key": "strategy.visual.f.long"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
    "grid": [
        {"name": "lower", "type": "float", "default": 100, "min": 0, "label_key": "strategy.visual.f.lower"},
        {"name": "upper", "type": "float", "default": 200, "min": 0, "label_key": "strategy.visual.f.upper"},
        {"name": "grids", "type": "int", "default": 5, "min": 1, "max": 100, "label_key": "strategy.visual.f.grids"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
    "dca": [
        {"name": "period", "type": "int", "default": 12, "min": 1, "label_key": "strategy.visual.f.period"},
        {"name": "amount", "type": "float", "default": 10, "min": 0, "label_key": "strategy.visual.f.amount"},
    ],
    "tp_sl": [
        {"name": "tp_pct", "type": "float", "default": 0.04, "min": 0, "label_key": "strategy.visual.f.tp"},
        {"name": "sl_pct", "type": "float", "default": 0.02, "min": 0, "label_key": "strategy.visual.f.sl"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
}
