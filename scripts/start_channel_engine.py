"""npm 开发入口：读取本机引擎路径，不从配置文件启用模拟模式。"""
import os
from pathlib import Path
import sys

from dotenv import dotenv_values


def main():
    service = Path(__file__).resolve().parents[1] / "channel-engine-service"
    config = service / ".env"
    if "CHANNEL_ENGINE_PATH" not in os.environ and config.is_file():
        value = dotenv_values(config, interpolate=False).get("CHANNEL_ENGINE_PATH")
        if value:
            os.environ["CHANNEL_ENGINE_PATH"] = value
    if not os.environ.get("CHANNEL_ENGINE_PATH") and not os.environ.get("MOCK_ASC_MODE"):
        sys.exit(f"未配置计算引擎目录。请在 {config} 设置 CHANNEL_ENGINE_PATH 为本机引擎的绝对路径。")
    os.chdir(service)
    # 直接运行工作进程，启动校验失败时退出，不遗留占用端口的重载进程。
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app",
                              "--host", "127.0.0.1", "--port", "8001"])


if __name__ == "__main__":
    main()
