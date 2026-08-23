"""v0.9.0 release：版本号是构建属性，唯一真值源 = app/config.py，环境变量不得覆盖。

实证（2026-08-23）：本机 .env 的 APP_VERSION=1.0.0 曾让 settings.app_version 在代码已改
0.9.0 后仍报 1.0.0 —— release 写一个号、运行时报另一个号。把字段声明成 ClassVar，
BaseSettings 就不再从环境 / .env 读它（去掉入口，而不是靠"记得清理 .env"）。

变异：把 ClassVar 去掉 → 本门红（环境变量重新覆盖）。
"""
import os

import pytest

from app import config as config_module


@pytest.mark.parametrize("poison", ["9.9.9", "1.0.0", ""])
def test_app_version_cannot_be_overridden_by_environment(monkeypatch, poison):
    monkeypatch.setenv("APP_VERSION", poison)
    fresh = config_module.Settings(_env_file=None)
    assert fresh.app_version == "0.9.0", (
        f"APP_VERSION={poison!r} 覆盖了版本号：{fresh.app_version}"
    )


def test_app_version_is_single_sourced_in_config_module():
    # 三处版本字段（config / openapi / package.json）都对齐到同一个号
    import json
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    openapi = (root / "api" / "openapi.yaml").read_text(encoding="utf-8")
    package = json.loads((root / "gui" / "package.json").read_text(encoding="utf-8"))
    version = config_module.settings.app_version
    assert f"  version: {version}\n" in openapi
    assert package["version"] == version
