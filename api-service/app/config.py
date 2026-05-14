"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Application
    app_name: str = "Meta-3D OTA API"
    app_version: str = "1.0.0"
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

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
