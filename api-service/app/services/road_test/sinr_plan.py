"""对同一接收参考面的系统仿真时间窗计算新增干扰与噪声。"""
from math import expm1, isfinite, log, log10, sqrt
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Scope(Strict):
    frame: int = Field(ge=0)
    receiver: str = Field(min_length=1)
    plane: Literal["receiver_connector", "receiver_combined"]
    bandwidth_hz: float = Field(gt=0)
    start_s: float = Field(ge=0)
    duration_s: float = Field(gt=0)


class Level(Strict):
    scope: Scope
    dbm: float
    sources: list[str] = Field(min_length=1)
    kind: Literal["signal","interference_and_noise"]


class Window(Strict):
    scope: Scope
    target_sinr_db: float
    signal: Level | None = None
    existing: Level | None = None
    additional_source: str = Field(min_length=1)
    correlation_real: float | None = Field(default=None,ge=-1,le=1)
    method: Literal["equivalent_noise","waveform_covariance"]
    injection_plane: str | None = None


def budget(window):
    result = dict(scope=window.scope.model_dump(), formal_measurement=False,
                  total_disturbance_dbm=None, additional_dbm=None, reason=None)
    def unknown(reason):
        return {**result,"reason":reason}
    signal, existing = window.signal, window.existing
    if not signal or not existing:
        return unknown("缺少绝对信号功率或同一参考面的已有干扰与噪声总量")
    if signal.kind != "signal" or existing.kind != "interference_and_noise":
        return unknown("信号与已有干扰加噪声的来源类型不符")
    if signal.scope != window.scope or existing.scope != window.scope:
        return unknown("端口、参考面、带宽、帧或统计窗口不一致")
    names = [name.strip() for name in signal.sources + existing.sources + [window.additional_source]]
    if any(not name.strip() for name in names) or len(set(names)) != len(names):
        return unknown("来源缺失或重复计入")
    total_dbm = signal.dbm - window.target_sinr_db
    if not isfinite(total_dbm):
        return unknown("目标功率超出可计算范围")
    result["total_disturbance_dbm"] = total_dbm
    if existing.dbm > total_dbm:
        return unknown("已有干扰和噪声超过目标允许的总量")
    if window.correlation_real is None:
        return unknown("新增源与已有扰动的相关性未核验")
    if not window.injection_plane or window.injection_plane != window.scope.plane or window.scope.plane != "receiver_connector":
        return unknown("注入参考面与接收插口尚未对齐")
    # 以目标总量归一化，避免把极弱的绝对功率提前舍入为零。
    ratio = 10**((existing.dbm-total_dbm)/10)
    cross = window.correlation_real * sqrt(ratio)
    if existing.dbm == total_dbm:
        return {**result,"additional_mw":0.0,"additional_dbm":None,"reason":"无需新增扰动"}
    difference = -expm1((existing.dbm-total_dbm)*(log(10)/10))
    if difference <= 0:
        return unknown("功率差小于可分辨精度")
    radicand = cross*cross + difference
    amplitude = difference/(sqrt(radicand)+cross) if cross >= 0 else sqrt(radicand)-cross
    if not isfinite(amplitude) or amplitude <= 0:
        return unknown("功率差小于可分辨精度")
    result["additional_dbm"] = total_dbm+20*log10(amplitude)
    if window.method == "waveform_covariance":
        result["reason"] = "需另有干扰波形和多端口噪声相关矩阵；单个 SINR 无法确定空间特性"
    return result


class Waveforms(Strict):
    windows: list[Window] = Field(min_length=1,max_length=32)
    sample_rate_hz: float = Field(gt=0)
    sample_count: int = Field(ge=2, le=8192)
    correlation_real: list[list[float]]
    correlation_imag: list[list[float]]
    seed: int = Field(ge=0,le=2**32-1)
    # 单位为 sqrt(mW) 的复基带干扰波形，与新增高斯噪声互不相关。
    interference_i: list[list[float]]
    interference_q: list[list[float]]


def render_waveforms(request):
    import numpy as np
    ports = [w.scope.receiver for w in request.windows]
    n = len(ports)
    first = request.windows[0].scope
    common = first.model_dump(exclude={"receiver"})
    if len(set(ports)) != n or any(w.scope.model_dump(exclude={"receiver"}) != common for w in request.windows):
        raise ValueError("多端口波形需要唯一端口与相同统计窗口")
    if request.sample_rate_hz != first.bandwidth_hz or abs(request.sample_count/request.sample_rate_hz-first.duration_s)>1e-12:
        raise ValueError("当前离线复基带生成要求采样率等于占用带宽且样本覆盖统计窗口")
    results = [budget(w) for w in request.windows]
    if any(w.method!="waveform_covariance" or w.correlation_real!=0 for w in request.windows) or any(r["additional_dbm"] is None and r.get("additional_mw") != 0 for r in results):
        raise ValueError("波形生成需要已求得的新增功率，且新增源与既有扰动互不相关")
    c = np.asarray(request.correlation_real)+1j*np.asarray(request.correlation_imag)
    if np.shape(request.correlation_real)!=(n,n) or np.shape(request.correlation_imag)!=(n,n) or c.shape != (n,n) or not np.isfinite(c).all() or not np.allclose(c,c.conj().T,rtol=0,atol=1e-12) or not np.allclose(c.diagonal(),1,rtol=0,atol=1e-12):
        raise ValueError("噪声相关矩阵须为对角为一的厄米矩阵")
    values, vectors = np.linalg.eigh(c)
    tolerance = 8 * n * np.finfo(float).eps * np.max(abs(c))
    if values.min() < -tolerance or np.max(abs(c-c.conj().T)) > tolerance or np.max(abs(c.diagonal()-1)) > tolerance:
        raise ValueError("噪声相关矩阵必须半正定")
    known = np.asarray(request.interference_i)+1j*np.asarray(request.interference_q)
    if np.shape(request.interference_i)!=(n,request.sample_count) or np.shape(request.interference_q)!=(n,request.sample_count) or known.shape != (n,request.sample_count) or not np.isfinite(known).all():
        raise ValueError("干扰波形需按每端口提供完整实部和虚部")
    desired = np.array([0. if r["additional_dbm"] is None else 10**(r["additional_dbm"]/10) for r in results])
    if not np.isfinite(desired).all() or any(r["additional_dbm"] is not None and mw <= 0 for mw,r in zip(desired,results)):
        raise ValueError("要求的正功率无法表示为有限毫瓦值")
    left = desired - np.mean(abs(known)**2,axis=1)
    if np.any(left<0):
        raise ValueError("输入干扰波形已超过可新增扰动功率")
    rng = np.random.default_rng(request.seed)
    shape = (n, request.sample_count)
    white = (rng.normal(size=shape)+1j*rng.normal(size=shape))/sqrt(2)
    noise = np.sqrt(left)[:,None]*(vectors*np.sqrt(np.maximum(values,0)))@white
    output = known+noise
    if not np.isfinite(output).all() or not np.isfinite(abs(output)**2).all():
        raise ValueError("生成波形超出可表示范围")
    return dict(ports=ports, i=output.real.tolist(),q=output.imag.tolist(),unit="sqrt(mW)",
                requested_mw=desired.tolist(),realized_mw=np.mean(abs(output)**2,axis=1).tolist(),
                formal_measurement=False, rf_enabled=False)
