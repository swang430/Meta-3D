"""Application configuration"""
import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import Any, ClassVar, Optional

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""

    # Application
    app_name: str = "Meta-3D OTA API"
    # 版本是构建属性，不是部署配置 —— ClassVar 让 BaseSettings 不再从环境 / .env 读它
    # （2026-08-23 实测 .env 的 APP_VERSION=1.0.0 会静默覆盖，运行时报假版本）。
    # 阶段性 release（日常测试用）；1.0.0 留给 first-call 现场通过后。
    app_version: ClassVar[str] = "0.9.0"

    @model_validator(mode="before")
    @classmethod
    def _ignore_legacy_app_version_input(cls, data: Any) -> Any:
        """旧 .env / README 里残留的 APP_VERSION 只忽略、不致命。

        ClassVar 让它不再是字段，但 BaseSettings 默认 extra="forbid"，.env 里的旧键会
        直接抛 extra_forbidden 让 API 起不来（内审 2026-08-23 抓出：爆炸半径从"报假
        版本"升级成"进程拒绝启动"）。这里把该键弹掉并 warning 一句；其它键照常校验。
        """
        if isinstance(data, dict) and "app_version" in data:
            data = {k: v for k, v in data.items() if k != "app_version"}
            logger.warning(
                "配置里的 APP_VERSION 已忽略：版本号是构建属性，唯一真值源 = app/config.py "
                "(app_version=%s)；请从 .env 删除该行", cls.app_version,
            )
        return data
    debug: bool = True

    # Database
    database_url: str = "postgresql://meta3d:meta3d_password@localhost:5432/meta3d_ota"

    # For SQLite (development fallback)
    # database_url: str = "sqlite:///./meta3d_ota.db"

    # API
    api_v1_prefix: str = "/api/v1"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://localhost:8080",
    ]

    # Mock instruments (for development without hardware)
    use_mock_instruments: bool = True

    # Human-facing filenames/tokens use the operator site's wall clock. DB/API
    # timestamps remain UTC. Override with OPERATOR_TIMEZONE at deployment.
    operator_timezone: str = "Asia/Shanghai"

    # Bootstrap (DB factory-defaults seeder) — runs on lifespan startup
    # after init_db(). Escape hatch for ops who want to manage seed data
    # out-of-band (e.g. by running `python -m scripts.bootstrap` from
    # their own deploy script).
    bootstrap_on_startup: bool = True

    # Calibration settings
    calibration_data_path: str = "./calibration_data"
    certificate_output_path: str = "./certificates"

    # Logging
    log_dir: str = "./logs"              # 日志文件输出目录
    log_retention_days: int = 30         # 日志文件保留天数
    log_scpi_enabled: bool = True        # 是否启用 SCPI 仪器通信专用日志
    log_db_enabled: bool = True          # 是否启用数据库 SQL 查询日志
    # SCPI 响应体写进 scpi.log 的最大字符数, 超出截断并显式标记
    # (P1-30; 原为硬编码 200 且无标记 —— 实测 22,914 条 real 模式 RX 恰好
    #  200 字符, 长响应从未在日志里露过全貌)。现场磁盘吃紧可调回 200。
    log_scpi_resp_max: int = 2000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
