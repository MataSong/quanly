from .schemas import SCHEMAS
from .skeletons import SKELETONS


def generate_source(kind: str, config: dict) -> str:
    if kind not in SKELETONS:
        raise ValueError(f"unknown strategy kind: {kind}")
    schema = SCHEMAS[kind]
    params = {}
    for field in schema:
        name = field["name"]
        val = config.get(name, field.get("default"))
        if val is None:
            raise ValueError(f"missing field: {name}")
        if field["type"] == "int":
            val = int(val)
        elif field["type"] == "float":
            val = float(val)
        params[name] = val
    src = SKELETONS[kind].format(**params)
    compile(src, f"visual_{kind}.py", "exec")  # 自检:生成的源码必须语法正确
    return src
