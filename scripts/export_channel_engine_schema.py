"""从计算服务生成接口定义；路径相对项目定位，失败按非零退出码返回。"""
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "channel-engine-service"))

def main():
    # 只读取路由定义，不启动服务、不运行计算，也不伪装计算库或覆盖其配置。
    from app.main import app
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title, version=app.version,
        openapi_version=app.openapi_version, description=app.description,
        routes=app.routes,
    )
    output = PROJECT_ROOT / "gui/src/types/channel-engine-schema.json"
    output.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"接口定义已生成：{output}")

if __name__ == "__main__":
    main()
