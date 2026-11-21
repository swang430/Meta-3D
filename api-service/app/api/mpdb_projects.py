"""一次保存原始传播数据，分别生成可下载的离线工程输入包。"""

import io
import json
import logging
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Literal
from uuid import UUID, uuid4
import zipfile

from dotenv import dotenv_values
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/channel-assets/mpdb-projects", tags=["Channel Asset"])
ROOT = Path(__file__).resolve().parents[3]
LIMIT = 256 * 1024**2
logger = logging.getLogger(__name__)


class ImportedSource(BaseModel):
    source_id: UUID


class BuiltProject(BaseModel):
    download_url: str
    asc_count: int
    manifests: dict[str, dict]
    results: dict | None = None
    evidence: dict | None = None


class BuildParameters(BaseModel):
    mode: Literal["conducted", "ota"]
    clustering_method: Literal["delay_bins", "hyperrt"] | None = None
    speed_m_s: float = Field(default=5, gt=0, allow_inf_nan=False)
    rate_hz: float = Field(default=171.18765176762867, gt=0, allow_inf_nan=False)


def storage():
    directory = Path(tempfile.gettempdir()) / "meta3d-mpdb-projects"
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory


@router.post("/import", response_model=ImportedSource)
def import_source(file: UploadFile = File(...), members: UploadFile | None = File(None)):
    base = storage()
    for old in base.iterdir():
        if old.is_dir() and old.stat().st_mtime < time.time() - 86400:
            shutil.rmtree(old, ignore_errors=True)
    ident = uuid4()
    folder = base / str(ident)
    folder.mkdir()
    try:
        archive = folder / "source.zip"
        with archive.open("wb") as output:
            while chunk := file.file.read(1024**2):
                if output.tell() + len(chunk) > LIMIT:
                    raise ValueError("原始压缩包超过 256 MiB")
                output.write(chunk)
        with zipfile.ZipFile(archive) as outer:
            matches = [i for i in outer.infolist() if i.filename == "R0B0S0D.mpdb"]
            if len(matches) != 1 or matches[0].file_size > LIMIT:
                raise ValueError(
                    "压缩包须包含一份下行 R0B0S0D.mpdb，大小不超过 256 MiB"
                )
            with zipfile.ZipFile(io.BytesIO(outer.read(matches[0]))) as db:
                if len(db.namelist()) != len(set(db.namelist())):
                    raise ValueError("传播数据库中存在同名文件，无法确认分片来源")
                if sum(i.file_size for i in db.infolist()) > 512 * 1024**2:
                    raise ValueError("解压后的下行数据超过 512 MiB")
                meta = json.loads(db.read("mpdb.json"))["meta"]
                platform = meta["lauraycsPlatform"]
                if platform["direction"] != "downlink":
                    raise ValueError("工程需要下行传播数据")
                if (
                    platform.get("angleCoordinateSystem") != "GCS"
                    or meta.get("mode") != "CIR"
                    or meta.get("numFrequency") != 1
                ):
                    raise ValueError(
                        "当前支持采用全局角度坐标、单一载频的信道冲激响应数据"
                    )
        if members is not None:
            with (folder / "members.npz").open("xb") as dest:
                while chunk := members.file.read(1024**2):
                    if dest.tell() + len(chunk) > 32 * 1024**2:
                        raise ValueError("成员表超过 32 MiB")
                    dest.write(chunk)
        return {"source_id": str(ident)}
    except (
        OSError,
        RuntimeError,
        KeyError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, f"无法导入下行 MPDB：{exc}") from exc


def worker_environment(root: Path):
    env = os.environ.copy()
    config = root / "channel-engine-service/.env"
    local = dotenv_values(config, interpolate=False) if config.is_file() else {}
    for key in ("CHANNEL_ENGINE_PATH", "HYPERRT_PATH"):
        if key not in env and local.get(key):
            env[key] = local[key]
    engine = Path(env.get("CHANNEL_ENGINE_PATH", ""))
    if not engine.is_absolute() or not (engine / "mimo_ota_simulator").is_dir():
        raise HTTPException(503, "找不到信道引擎。请在 channel-engine-service/.env 中设置 CHANNEL_ENGINE_PATH 为引擎的绝对路径；启动环境中的同名设置优先。")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(engine), env.get("PYTHONPATH"))))
    return env


def run_worker(command, env):
    # HyperRT 是传导计算的子进程；超时要一起结束，之后才能删除它正在使用的目录。
    with subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name == "posix"),
    ) as worker:
        try:
            _, message = worker.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(worker.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(worker.pid)],
                        capture_output=True, timeout=15, check=True,
                    )
                except (OSError, subprocess.SubprocessError):
                    worker.kill()
                    raise HTTPException(
                        503, "离线计算已超时，子进程退出未经确认，请检查计算主机"
                    )
            worker.kill()
            worker.wait(timeout=15)
            raise
        return worker.returncode, message


def checked_manifest(directory: Path, role: str, expected: int):
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        links = manifest["links"]
        if not isinstance(links, list):
            raise ValueError
        declared = {link["file"] for link in links}
        if not all(isinstance(name, str) for name in declared):
            raise ValueError
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(500, f"{role} 工程清单缺失或文件名列表无效") from exc

    actual = {path.name for path in directory.iterdir()
              if path.is_file() and path.suffix.lower() == ".asc"}
    problems = []
    if len(links) != expected or len(declared) != expected or len(actual) != expected:
        problems.append(f"预期 {expected} 条通路，清单有 {len(links)} 条记录、"
                        f"{len(declared)} 个不同文件名，目录有 {len(actual)} 个 ASC 文件")
    if missing := declared - actual:
        problems.append("缺少文件：" + "、".join(sorted(missing)))
    if extra := actual - declared:
        problems.append("额外文件：" + "、".join(sorted(extra)))
    if problems:
        raise HTTPException(500, f"{role} 工程未发布。" + "。".join(problems))
    return manifest


@router.post(
    "/{source_id}/build", response_model=BuiltProject, response_model_exclude_none=True
)
def build_project(source_id: UUID, params: BuildParameters):
    folder = storage() / str(source_id)
    archive = folder / "source.zip"
    if not archive.is_file():
        raise HTTPException(404, "导入记录已过期，请重新选择原始文件")
    os.utime(folder, None)
    env = worker_environment(ROOT)
    ident = uuid4()
    engine_python = ROOT / "channel-engine-service/.venv/bin/python"
    python = str(engine_python) if engine_python.is_file() else sys.executable
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        stage = Path(tmp)
        output = stage / "project"
        try:
            code, message = run_worker(
                [
                    python,
                    str(ROOT / "scripts/mpdb_workbench.py"),
                    str(archive),
                    str(output),
                    params.mode,
                    str(params.speed_m_s),
                    str(params.rate_hz),
                    *([params.clustering_method or "auto"] if params.mode == "conducted" else []),
                    *([str(folder / "members.npz")] if params.mode == "conducted" and
                      (folder / "members.npz").is_file() else []),
                ],
                env=env,
            )
            if code == 3 and params.mode == "conducted":
                raise HTTPException(409, "未找到同源成员表，请选择聚簇方式。")
            if code:
                logger.warning("信道工程生成失败：%s", message[-2000:])
                message = message.strip().splitlines()
                raise HTTPException(
                    422, message[-1][:500] if message else "计算程序未生成工程"
                )
            if params.mode == "conducted":
                manifests = {"conducted": checked_manifest(output, "conducted", 8)}
            else:
                manifests = {
                    role: checked_manifest(output / role, role, 128)
                    for role in ("baseline", "dynamic")
                }
            primary = "conducted" if params.mode == "conducted" else "dynamic"
            result = {
                "download_url": f"/api/v1/channel-assets/mpdb-projects/{source_id}/{ident}.zip",
                "asc_count": len(manifests[primary]["links"]),
                "manifests": manifests,
            }
            if params.mode == "conducted":
                for key in ("results", "evidence"):
                    try:
                        document = json.loads((output / f"{key}.json").read_text(encoding="utf-8"))
                    except (FileNotFoundError, ValueError):
                        continue
                    if isinstance(document, dict):
                        result[key] = document
            package = shutil.make_archive(str(stage / "package"), "zip", output)
            Path(package).replace(folder / f"{ident}.zip")
            return result
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(503, "离线计算超时，请检查数据量和计算环境") from exc


@router.get(
    "/{source_id}/{project_id}.zip",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
def download_project(source_id: UUID, project_id: UUID):
    path = storage() / str(source_id) / f"{project_id}.zip"
    if not path.is_file():
        raise HTTPException(404, "工程包不存在或已过期")
    return FileResponse(
        path, filename=f"MPDB-{project_id}.zip", media_type="application/zip"
    )
