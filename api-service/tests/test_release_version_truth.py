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


@pytest.mark.parametrize("legacy_line", ["APP_VERSION=1.0.0", "APP_VERSION=9.9.9", "APP_VERSION="])
def test_legacy_dotenv_app_version_is_ignored_not_fatal(tmp_path, monkeypatch, legacy_line):
    """内审 F1（P1）：按旧 .env.example / README 配好的 .env 里残留 APP_VERSION，
    ClassVar 后 BaseSettings(extra=forbid) 会抛 extra_forbidden —— API 起不来，
    爆炸半径从"报假版本"升级成"进程拒绝启动"。必须忽略（可 warning），不能致命。

    变异：去掉 before-validator 的弹键 → 本门以 ValidationError 红。
    """
    monkeypatch.delenv("APP_VERSION", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_NAME=Meta-3D OTA API\n{legacy_line}\nDEBUG=false\n", encoding="utf-8")

    fresh = config_module.Settings(_env_file=str(env_file))  # 不得抛

    assert fresh.app_version == "0.9.0"
    assert fresh.debug is False, "同一份 .env 里的其它键必须照常生效"


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
