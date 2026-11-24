"""一次保存原始传播数据，分别生成可下载的离线工程输入包。"""

import io
import hashlib
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
import numpy as np

from dotenv import dotenv_values
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/channel-assets/mpdb-projects", tags=["Channel Asset"])
ROOT = Path(__file__).resolve().parents[3]
LIMIT = 256 * 1024**2
logger = logging.getLogger(__name__)


def offline_modules():
    # 只有离线工作台依赖仓库顶层的脚本；独立 API 镜像仍能启动和使用其他功能。
    scripts = ROOT / "scripts"
    if not (scripts / "mpdb_workbench.py").is_file():
        raise HTTPException(503, "当前服务未安装 MPDB 离线计算脚本，请使用配有离线工作台的部署。")
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    try:
        import mpdb_playback
        import mpdb_conducted_project
    except ImportError as exc:
        logger.warning("无法加载 MPDB 离线脚本：%s", exc)
        raise HTTPException(503, "当前服务的 MPDB 离线计算组件不完整，请检查部署。") from exc
    return mpdb_playback, mpdb_conducted_project


class SourceTiming(BaseModel):
    max_abs_doppler_hz: float | None = None
    plan_sha256: str | None = None
    frame_ids: list[int]
    distances_m: list[float | None]
    source_times_s: list[float] | None
    time_source: str | None


class ImportedSource(BaseModel):
    source_id: UUID
    timing: SourceTiming
    clustering: Literal["matched", "missing", "supplied"]


class BuiltProject(BaseModel):
    download_url: str
    asc_count: int
    manifests: dict[str, dict]
    results: dict | None = None
    evidence: dict | None = None


class BuildParameters(BaseModel):
    model_config = {"extra": "forbid"}
    mode: Literal["conducted", "ota"]
    clustering_method: Literal["delay_bins"] | None = None
    speed_m_s: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    rate_quality: Literal["standard", "dense"] = "standard"
    segment_durations_s: list[float] | None = None


def storage():
    directory = Path(tempfile.gettempdir()) / "meta3d-mpdb-projects"
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory


@router.post("/import", response_model=ImportedSource)
def import_source(file: UploadFile = File(...), members: UploadFile | None = File(None),
                  plan_manifest: UploadFile | None = File(None)):
    playback, conducted = offline_modules()
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
            raw = outer.read(matches[0])
            digest = hashlib.sha256(raw).hexdigest()
            with zipfile.ZipFile(io.BytesIO(raw)) as db:
                if len(db.namelist()) != len(set(db.namelist())):
                    raise ValueError("传播数据库中存在同名文件，无法确认分片来源")
                if sum(i.file_size for i in db.infolist()) > 512 * 1024**2:
                    raise ValueError("解压后的下行数据超过 512 MiB")
                desc = json.loads(db.read("mpdb.json"))
                meta = desc["meta"]
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
                plan_raw = None
                if plan_manifest is not None:
                    plan_raw = plan_manifest.file.read(8 * 1024**2 + 1)
                    if len(plan_raw) > 8 * 1024**2:
                        raise ValueError("链路计算清单超过 8 MiB")
                timing = playback.inspect_timing(db, desc, plan_raw)
                if members is not None:
                    link_ids = conducted.column(db, desc, "LINK", "LINK_ID").ravel()
        (folder / "timing.json").write_text(json.dumps(timing, allow_nan=False))
        known = ROOT / "docs/evidence/imt-three/members.npz"
        clustering = "missing"
        if known.is_file():
            with np.load(known, allow_pickle=False) as data:
                if str(data["source_sha256"]) == digest:
                    clustering = "matched"
        if members is not None:
            with (folder / "members.npz").open("xb") as dest:
                while chunk := members.file.read(1024**2):
                    if dest.tell() + len(chunk) > 32 * 1024**2:
                        raise ValueError("成员表超过 32 MiB")
                    dest.write(chunk)
            conducted.validate_members_container(dest.name, link_ids)
            with np.load(dest.name, allow_pickle=False) as data:
                if str(data["source_sha256"]) != digest:
                    raise ValueError("上传的聚簇结果不属于这份下行数据")
            clustering = "supplied"
        return {"source_id": str(ident), "timing":timing, "clustering":clustering}
    except (
        OSError,
        EOFError,
        AttributeError,
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
    env.pop("HYPERRT_PATH", None)
    if "CHANNEL_ENGINE_PATH" not in env and local.get("CHANNEL_ENGINE_PATH"):
        env["CHANNEL_ENGINE_PATH"] = local["CHANNEL_ENGINE_PATH"]
    engine = Path(env.get("CHANNEL_ENGINE_PATH", ""))
    if not engine.is_absolute() or not (engine / "mimo_ota_simulator").is_dir():
        raise HTTPException(503, "找不到信道引擎。请在 channel-engine-service/.env 中设置 CHANNEL_ENGINE_PATH 为引擎的绝对路径；启动环境中的同名设置优先。")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(engine), env.get("PYTHONPATH"))))
    return env


def run_worker(command, env):
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
    clocks, _ = offline_modules()
    os.utime(folder, None)
    ident = uuid4()
    engine_python = ROOT / "channel-engine-service/.venv/bin/python"
    python = str(engine_python) if engine_python.is_file() else sys.executable
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        stage = Path(tmp)
        output = stage / "project"
        arguments = ["-", "-", params.clustering_method or "auto"]
        if params.mode == "ota":
            timing_path = folder / "timing.json"
            if not timing_path.is_file():
                raise HTTPException(409, "此导入记录没有时间检查结果，请重新导入")
            try:
                playback = clocks.resolve_playback(json.loads(timing_path.read_text()), params.speed_m_s,
                                            params.segment_durations_s, params.rate_quality)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            playback_path = stage / "playback.json"
            playback_path.write_text(json.dumps(playback, allow_nan=False))
            arguments = [str(playback_path)]
        elif (folder / "members.npz").is_file():
            arguments.append(str(folder / "members.npz"))
        env = worker_environment(ROOT)
        try:
            code, message = run_worker(
                [
                    python,
                    str(ROOT / "scripts/mpdb_workbench.py"),
                    str(archive),
                    str(output),
                    params.mode,
                    *arguments,
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


@router.post("/port-evidence", response_class=FileResponse, responses={
    200: {"content": {"application/json": {"schema": {"type": "object"}}},
          "description": "下载含摘要、分析参数和逐帧记录的完整结果"}
})
def analyze_port_evidence(archive: UploadFile, bandwidth_mhz: float = Form(..., gt=0, le=10000, allow_inf_nan=False),
                          points: int = Form(..., ge=3, le=257), members: UploadFile | None = File(None),
                          expected: UploadFile | None = File(None),
                          amplitude_floor: float | None = Form(None, gt=0, allow_inf_nan=False)):
    """只读核对各端口的成员，再比较同一批成员的两种时延。"""
    from starlette.background import BackgroundTask
    from app.services.channel_generation.mpdb_input import _archive

    if points % 2 == 0:
        raise HTTPException(422, "频点数须为包含中心和两端带边的奇数。")
    script = ROOT / "scripts/mpdb_port_evidence.py"
    if not script.is_file():
        raise HTTPException(503, "当前部署缺少端口分析脚本。")
    temporary = tempfile.TemporaryDirectory(prefix="mpdb-port-evidence-")
    directory = Path(temporary.name)
    output = directory / "port-evidence.json"
    command = [sys.executable, str(script), "--bandwidth-mhz", str(bandwidth_mhz),
               "--points", str(points), "--output", str(output)]
    try:
        if amplitude_floor is not None:
            command.extend(["--amplitude-floor", str(amplitude_floor)])
        for upload, option, name, limit in (
            (archive, "--archive", "source.zip", LIMIT),
            (members, "--members", "members.npz", 32 * 1024**2),
            (expected, "--expected", "results.json", 32 * 1024**2),
        ):
            if upload is None:
                continue
            path = directory / name
            with path.open("xb") as dest:
                while chunk := upload.file.read(1024**2):
                    if dest.tell() + len(chunk) > limit:
                        raise ValueError(f"{name} 超过 {limit // 1024**2} MiB")
                    dest.write(chunk)
            command.extend([option, str(path)])
        with _archive((directory / "source.zip").read_bytes()) as outer:
            with _archive(outer.read("R0B0S0D.mpdb")):
                pass
        if members is not None:
            with _archive((directory / "members.npz").read_bytes()) as container:
                if sum(entry.file_size for entry in container.infolist()) > 128 * 1024**2:
                    raise ValueError("解压后的成员表超过 128 MiB")
        env = worker_environment(ROOT)
        env.pop("HYPERRT_PATH", None)
        code, message = run_worker(command, env)
        if code:
            logger.warning("端口离线分析失败：%s", message[-2000:])
            raise HTTPException(422, "分析未完成，请检查原始数据和配套记录。")
        if not output.is_file():
            raise HTTPException(502, "分析程序未返回结果文件。")
        return FileResponse(output, filename=output.name, media_type="application/json",
                            background=BackgroundTask(temporary.cleanup))
    except (ValueError, KeyError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError) as exc:
        temporary.cleanup()
        raise HTTPException(422, f"无法读取分析文件：{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        temporary.cleanup()
        raise HTTPException(504, "端口分析超时。") from exc
    except Exception:
        temporary.cleanup()
        raise


@router.post('/comparisons')
def compare_existing_channels(
    archive: UploadFile = File(...), asc: UploadFile = File(...), members: UploadFile = File(...),
    bandwidth_mhz: float = Form(100, gt=0, le=10000, allow_inf_nan=False),
    points: int = Form(41, ge=3, le=257),
    amplitude_floor: float = Form(1e-8, gt=0, allow_inf_nan=False),
):
    """比较已有文件，返回摘要及独立下载，不修改工程或设备。"""
    if points % 2 == 0:
        raise HTTPException(422, '频点数须为包含中心频点的奇数。')
    script = ROOT / 'scripts/mpdb_comparison.py'
    if not script.is_file():
        raise HTTPException(503, '当前部署缺少已有信道比较组件。')
    base = storage()
    for old in base.glob('comparison-*.zip'):
        if old.stat().st_mtime < time.time() - 86400:
            old.unlink(missing_ok=True)
    ident = uuid4()
    with tempfile.TemporaryDirectory(prefix='mpdb-comparison-') as tmp:
        stage = Path(tmp)
        command = [sys.executable, str(script), '--output', str(stage/'result'),
            '--bandwidth-mhz', str(bandwidth_mhz), '--points', str(points),
            '--amplitude-floor', str(amplitude_floor)]
        try:
            for upload, option, limit in ((archive,'archive',LIMIT),(asc,'asc',LIMIT),(members,'members',32*1024**2)):
                local = stage/option
                with local.open('xb') as dest:
                    while chunk := upload.file.read(1024**2):
                        if dest.tell()+len(chunk) > limit:
                            raise ValueError(f'{option} 文件超过允许大小')
                        dest.write(chunk)
                command.extend(['--'+option,str(local)])
            env = worker_environment(ROOT)
            env.pop('HYPERRT_PATH',None)
            python = ROOT/'channel-engine-service/.venv/bin/python'
            if python.is_file():
                command[0] = str(python)
            code,message = run_worker(command,env)
            if code:
                logger.warning('已有信道比较失败：%s',message[-2000:])
                raise HTTPException(422,'比较未完成，请检查同源成员表、八路 ASC、载频、极化和源帧依据。')
            result = stage/'result'
            summary = json.loads((result/'summary.json').read_text(encoding='utf-8'))
            if (summary.get('schema') != 'mpdb-comparison/1' or summary.get('formal_verdict') is not None
                    or summary.get('alignment_status') != 'unverified'):
                raise HTTPException(502,'比较程序返回的分析状态无效。')
            package = stage/'package.zip'
            with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name in ('summary.json','report.json','points.csv'):
                    z.write(result/name,name)
            # 只有所有结果文件齐全才发布；打包与移动在同一存储目录完成。
            destination = base/f'comparison-{ident}.zip'
            with tempfile.NamedTemporaryFile(dir=base,delete=False) as target:
                unpublished = Path(target.name)
                try:
                    with package.open('rb') as source:
                        shutil.copyfileobj(source,target)
                    target.flush()
                    unpublished.replace(destination)
                finally:
                    unpublished.unlink(missing_ok=True)
            prefix = f'/api/v1/channel-assets/mpdb-projects/comparisons/{ident}'
            return dict(**summary,comparison_id=str(ident),download_url=prefix+'/report.zip',points_url=prefix+'/points.csv')
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504,'已有信道比较超时。') from exc
        except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
            raise HTTPException(422,f'无法完成文件比较：{exc}') from exc


@router.get('/comparisons/{comparison_id}/{artifact}')
def download_channel_comparison(comparison_id: UUID, artifact: Literal['report.zip','points.csv']):
    from fastapi.responses import Response
    path = storage()/f'comparison-{comparison_id}.zip'
    if not path.is_file() or path.stat().st_mtime < time.time()-86400:
        raise HTTPException(404,'比较结果不存在或已过期，请重新比较。')
    if artifact == 'report.zip':
        return FileResponse(path,filename=f'channel-comparison-{comparison_id}.zip',media_type='application/zip')
    with zipfile.ZipFile(path) as package:
        data = package.read('points.csv')
    return Response(data,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="channel-comparison-{comparison_id}.csv"'})


@router.post('/budget-comparisons')
def compare_tap_budgets(
    archive: UploadFile = File(...), members: UploadFile = File(...),
    bandwidth_mhz: float = Form(100, gt=0, le=10000, allow_inf_nan=False),
    points: int = Form(41, ge=3, le=257),
    amplitude_floor: float = Form(1e-8, gt=0, allow_inf_nan=False),
):
    """比较已有文件，返回摘要及独立下载，不修改工程或设备。"""
    if points % 2 == 0:
        raise HTTPException(422, '频点数须为包含中心频点的奇数。')
    script = ROOT / 'scripts/mpdb_budget.py'
    if not script.is_file():
        raise HTTPException(503, '当前部署缺少固定成员预算比较组件。')
    base = storage()
    for old in base.glob('budget-comparison-*.zip'):
        if old.stat().st_mtime < time.time() - 86400:
            old.unlink(missing_ok=True)
    ident = uuid4()
    with tempfile.TemporaryDirectory(prefix='mpdb-budget-comparison-') as tmp:
        stage = Path(tmp)
        command = [sys.executable, str(script), '--output', str(stage/'result'),
            '--bandwidth-mhz', str(bandwidth_mhz), '--points', str(points),
            '--amplitude-floor', str(amplitude_floor)]
        try:
            for upload, option, limit in ((archive,'archive',LIMIT),(members,'members',32*1024**2)):
                local = stage/option
                with local.open('xb') as dest:
                    while chunk := upload.file.read(1024**2):
                        if dest.tell()+len(chunk) > limit:
                            raise ValueError(f'{option} 文件超过允许大小')
                        dest.write(chunk)
                command.extend(['--'+option,str(local)])
            env = worker_environment(ROOT)
            env.pop('HYPERRT_PATH',None)
            python = ROOT/'channel-engine-service/.venv/bin/python'
            if python.is_file():
                command[0] = str(python)
            code,message = run_worker(command,env)
            if code:
                logger.warning('固定成员预算比较失败：%s',message[-2000:])
                raise HTTPException(422,'比较未完成，请检查同源成员表、原始 MPDB 和源帧依据。')
            result = stage/'result'
            summary = json.loads((result/'summary.json').read_text(encoding='utf-8'))
            if (summary.get('schema') != 'mpdb-budget/1' or summary.get('formal_verdict') is not None
                    or summary.get('alignment_status') != 'unverified'):
                raise HTTPException(502,'比较程序返回的分析状态无效。')
            package = stage/'package.zip'
            with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name in ('summary.json','report.json','points.csv'):
                    z.write(result/name,name)
            # 只有所有结果文件齐全才发布；打包与移动在同一存储目录完成。
            destination = base/f'budget-comparison-{ident}.zip'
            with tempfile.NamedTemporaryFile(dir=base,delete=False) as target:
                unpublished = Path(target.name)
                try:
                    with package.open('rb') as source:
                        shutil.copyfileobj(source,target)
                    target.flush()
                    unpublished.replace(destination)
                finally:
                    unpublished.unlink(missing_ok=True)
            prefix = f'/api/v1/channel-assets/mpdb-projects/budget-comparisons/{ident}'
            return dict(**summary,comparison_id=str(ident),download_url=prefix+'/report.zip',points_url=prefix+'/points.csv')
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504,'固定成员预算比较超时。') from exc
        except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
            raise HTTPException(422,f'无法完成文件比较：{exc}') from exc


@router.get('/budget-comparisons/{comparison_id}/{artifact}')
def download_budget_comparison(comparison_id: UUID, artifact: Literal['report.zip','points.csv']):
    from fastapi.responses import Response
    path = storage()/f'budget-comparison-{comparison_id}.zip'
    if not path.is_file() or path.stat().st_mtime < time.time()-86400:
        raise HTTPException(404,'比较结果不存在或已过期，请重新比较。')
    if artifact == 'report.zip':
        return FileResponse(path,filename=f'channel-budget-comparison-{comparison_id}.zip',media_type='application/zip')
    with zipfile.ZipFile(path) as package:
        data = package.read('points.csv')
    return Response(data,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="channel-budget-comparison-{comparison_id}.csv"'})


@router.post('/purpose-evaluations')
def evaluate_channel_purpose(
    archive: UploadFile = File(...), members: UploadFile = File(...),
    asc: UploadFile | None = File(None),
    bandwidth_mhz: float = Form(100, gt=0, le=10000, allow_inf_nan=False),
    points: int = Form(41, ge=3, le=257),
    amplitude_floor: float = Form(1e-8, gt=0, allow_inf_nan=False),
    selection_start: int = Form(0, ge=0), selection_end: int = Form(25, ge=0),
    holdout_start: int = Form(26, ge=0), holdout_end: int | None = Form(None, ge=0, description="省略时采用实际源帧与上传ASC实际恢复范围的共同末帧；显式不可用帧会被拒绝。"),
    objective: Literal['phase','matrix'] = Form('phase'),
    mode: Literal['conducted','ota'] = Form('conducted'),
    tap_budget_max: int = Form(31, ge=1, le=31),
    matrix_nmse_p95_max: float = Form(1., ge=0, allow_inf_nan=False),
    phase_error_p95_max_deg: float = Form(60., ge=0, le=180, allow_inf_nan=False),
    manual_candidate: Literal['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31','existing-asc'] | None = Form(None),
):
    """比较已有文件，返回摘要及独立下载，不修改工程或设备。"""
    if manual_candidate == 'existing-asc' and asc is None:
        raise HTTPException(422, '人工选择已有 ASC 时须上传真实 ASC 压缩包。')
    if not (selection_start <= selection_end < holdout_start and holdout_start == selection_end + 1 and (holdout_end is None or holdout_start <= holdout_end)):
        raise HTTPException(422, '选择集和留出集须为相邻、不重叠的连续源帧区间。')
    if points % 2 == 0:
        raise HTTPException(422, '频点数须为包含中心频点的奇数。')
    script = ROOT / 'scripts/mpdb_purpose.py'
    if not script.is_file():
        raise HTTPException(503, '当前部署缺少候选方案目的评估组件。')
    base = storage()
    for old in base.glob('purpose-evaluation-*.zip'):
        if old.stat().st_mtime < time.time() - 86400:
            old.unlink(missing_ok=True)
    ident = uuid4()
    with tempfile.TemporaryDirectory(prefix='mpdb-purpose-evaluation-') as tmp:
        stage = Path(tmp)
        command = [sys.executable, str(script), '--output', str(stage/'result'),
            '--bandwidth-mhz', str(bandwidth_mhz), '--points', str(points),
            '--amplitude-floor', str(amplitude_floor)]
        for key, value in dict(selection_start=selection_start,selection_end=selection_end,
                holdout_start=holdout_start,holdout_end=holdout_end,objective=objective,
                mode=mode,tap_budget_max=tap_budget_max,matrix_nmse_p95_max=matrix_nmse_p95_max,
                phase_error_p95_max_deg=phase_error_p95_max_deg).items():
            if value is not None:
                command.extend(['--'+key.replace('_','-'),str(value)])
        if manual_candidate is not None:
            command.extend(['--manual-candidate',manual_candidate])
        try:
            for upload, option, limit in ((archive,'archive',LIMIT),(members,'members',32*1024**2)):
                local = stage/option
                with local.open('xb') as dest:
                    while chunk := upload.file.read(1024**2):
                        if dest.tell()+len(chunk) > limit:
                            raise ValueError(f'{option} 文件超过允许大小')
                        dest.write(chunk)
                command.extend(['--'+option,str(local)])
            if asc is not None:
                local = stage/'asc'
                with local.open('xb') as dest:
                    while chunk := asc.file.read(1024**2):
                        if dest.tell()+len(chunk)>LIMIT:
                            raise ValueError('ASC 文件超过允许大小')
                        dest.write(chunk)
                command.extend(['--asc',str(local)])
            env = worker_environment(ROOT)
            env.pop('HYPERRT_PATH',None)
            python = ROOT/'channel-engine-service/.venv/bin/python'
            if python.is_file():
                command[0] = str(python)
            code,message = run_worker(command,env)
            if code:
                logger.warning('候选方案目的评估失败：%s',message[-2000:])
                raise HTTPException(422,'比较未完成，请检查同源成员表、原始 MPDB 和源帧依据。')
            result = stage/'result'
            summary = json.loads((result/'summary.json').read_text(encoding='utf-8'))
            if (summary.get('schema') != 'mpdb-purpose/1' or summary.get('formal_verdict') is not None
                    or summary.get('alignment_status') != 'unverified'
                    or summary.get('hardware_verified') is not False):
                raise HTTPException(502,'比较程序返回的分析状态无效。')
            package = stage/'package.zip'
            with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name in ('summary.json','report.json','points.csv'):
                    z.write(result/name,name)
            # 只有所有结果文件齐全才发布；打包与移动在同一存储目录完成。
            destination = base/f'purpose-evaluation-{ident}.zip'
            with tempfile.NamedTemporaryFile(dir=base,delete=False) as target:
                unpublished = Path(target.name)
                try:
                    with package.open('rb') as source:
                        shutil.copyfileobj(source,target)
                    target.flush()
                    unpublished.replace(destination)
                finally:
                    unpublished.unlink(missing_ok=True)
            prefix = f'/api/v1/channel-assets/mpdb-projects/purpose-evaluations/{ident}'
            return dict(**summary,comparison_id=str(ident),download_url=prefix+'/report.zip',points_url=prefix+'/points.csv')
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504,'候选方案目的评估超时。') from exc
        except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
            raise HTTPException(422,f'无法完成文件比较：{exc}') from exc




@router.get('/purpose-evaluations/{comparison_id}/{artifact}')
def download_purpose_evaluation(comparison_id: UUID, artifact: Literal['report.zip','points.csv']):
    from fastapi.responses import Response
    path = storage()/f'purpose-evaluation-{comparison_id}.zip'
    if not path.is_file() or path.stat().st_mtime < time.time()-86400:
        raise HTTPException(404,'比较结果不存在或已过期，请重新比较。')
    if artifact == 'report.zip':
        return FileResponse(path,filename=f'channel-purpose-evaluation-{comparison_id}.zip',media_type='application/zip')
    with zipfile.ZipFile(path) as package:
        data = package.read('points.csv')
    return Response(data,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="channel-purpose-evaluation-{comparison_id}.csv"'})
