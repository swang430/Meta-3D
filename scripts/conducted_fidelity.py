"""从实际写出的传导 ASC 回读，比较同一源帧的复频响。"""
from itertools import combinations
import numpy as np


def spectral_matrix(reference, basis, tx_ports, rx_ports):
    """单边平坦发射功率谱，矩阵顺序必须与真实端口一致。"""
    doc = (reference or {}).get("tx_spectral_covariance")
    if doc is None:
        return None
    if (not isinstance(doc, dict) or doc.get("tx_ports") != tx_ports
            or doc.get("unit") != "mW/Hz" or not basis["bandwidth_hz"]
            or doc.get("frequency_model") != "flat_over_band"):
        raise ValueError("发射谱矩阵需要端口顺序、带宽和平坦的 mW/Hz 功率谱")
    n = len(tx_ports)
    values = []
    for field in ("real", "imag"):
        arr = np.asarray(doc.get(field))
        if arr.shape != (n, n) or arr.dtype.kind not in "fiu" or not np.isfinite(arr).all():
            raise ValueError("发射谱矩阵尺寸或数值无效")
        values.append(arr)
    q = values[0] + 1j * values[1]
    scale = max(np.max(abs(q)), np.finfo(float).tiny)
    if np.max(abs(q-q.conj().T)) > 1e-12*scale or min(np.linalg.eigvalsh(q)) < 0:
        raise ValueError("发射谱矩阵必须是厄米半正定矩阵")
    for i, t in enumerate(tx_ports):
        psd = (basis.get("tx_psd_dbm_per_hz") or {}).get(str(t))
        if psd is not None and not np.isclose(10**(psd/10), q[i,i].real, rtol=1e-8, atol=0):
            raise ValueError("端口功率谱与矩阵对角项不一致")
    for t in tx_ports:
        for r in rx_ports:
            link = basis["links"][f"{t}/{r}"]
            if (link["antenna_response"] not in ("both","tx","rx","neither")
                    or link["coefficient_unit"] != "power_wave_ratio"
                    or link["carrier_phase_convention"] != "included_in_coefficient"
                    or link["relative_ray_phase"] != "preserved"
                    or not all(isinstance(link[k], str) and link[k].strip().lower()
                               not in ("","unknown","unverified","未知","未核验")
                               for k in ("tx_plane","rx_plane","phase_origin","delay_origin","included_losses"))):
                return None
    for r in rx_ports:
        planes = [basis["links"][f"{t}/{r}"] for t in tx_ports]
        if any(len({link[k] for link in planes}) != 1 for k in ("phase_origin","delay_origin","rx_plane")):
            return None
    return q


def integrated_power(paths, q, bandwidth):
    # ∫exp(-j2π f Δτ)df = B sinc(B Δτ)，以 128 行分块限制内存。
    total = 0.0
    for i, (left, tau) in enumerate(paths):
        for j, (right, sigma) in enumerate(paths):
            if q[i,j] == 0:
                continue
            for start in range(0, len(left), 128):
                section = slice(start, start+128)
                overlap = np.sinc(bandwidth*(tau[section,None]-sigma[None,:]))
                total += (q[i,j] * (left[section] @ overlap @ right.conj())).real
    power = float(total * bandwidth)
    if not np.isfinite(power) or power < 0:
        raise ValueError("接收功率积分未得到有限非负值，请核对谱矩阵与参考面")
    return power


def compare_export(stage, links, frames, lookup, ids, coefficients, delays, bandwidth_hz, q=None, physical_phase=False):
    from mimo_ota_simulator.channel_comparison import frequency_response

    offsets = np.linspace(-bandwidth_hz / 2, bandwidth_hz / 2, 33)
    floor = 1e-12
    records = []
    phase_errors = []
    peak_phase = None
    peak_error = None
    rx_power = []
    excluded = 0
    tables = {}
    for link in links:
        pair = (link["tx"], link["rx"])
        values = np.loadtxt(stage / link["file"], skiprows=12, ndmin=2)
        tables[pair] = values.reshape(len(frames), -1, 3)
    pairs = [p for p in combinations(tables, 2) if p[0][0] == p[1][0] or p[0][1] == p[1][1]]
    for row, frame in enumerate(frames):
        curves = {}
        paths = {}
        for (tx, rx), table in tables.items():
            selected = ids == lookup[frame, tx, rx]
            ref = frequency_response(coefficients[selected], delays[selected], offsets)
            taps = table[row]
            asc = frequency_response(taps[:, 1] + 1j * taps[:, 2], taps[:, 0] * 1e-9, offsets)
            error = abs(asc - ref)
            index = int(np.argmax(error))
            detail = dict(frame=frame, tx=tx, rx=rx, worst_offset_hz=offsets[index],
                          max_complex_error=error[index], p95_complex_error=np.percentile(error, 95),
                          source_minimum_offset_hz=offsets[np.argmin(abs(ref))],
                          asc_minimum_offset_hz=offsets[np.argmin(abs(asc))])
            records.append(detail)
            if peak_error is None or error[index] > peak_error["max_complex_error"]:
                peak_error = detail
            curves[tx, rx] = (ref, asc)
            paths[tx, rx] = ((coefficients[selected], delays[selected]), (taps[:,1]+1j*taps[:,2], taps[:,0]*1e-9))
        if q is not None:
            for rx in sorted({r for _, r in tables}):
                spectra = []
                for side in (0, 1):
                    components = [paths[t, rx][side] for t in sorted({t for t, _ in tables})]
                    spectra.append(integrated_power(components, q, bandwidth_hz))
                rx_power.append(dict(frame=frame, rx=rx, source_mw=spectra[0], asc_mw=spectra[1]))
        for a, b in pairs:
            ar, ac = curves[a]
            br, bc = curves[b]
            valid = np.minimum.reduce([abs(ar), abs(ac), abs(br), abs(bc)]) > floor
            excluded += int(np.count_nonzero(~valid))
            if valid.any():
                errors = abs(np.angle(ac[valid] * bc[valid].conj() * ar[valid].conj() * br[valid], deg=True))
                phase_errors.extend(errors)
                i = int(np.argmax(errors))
                if peak_phase is None or errors[i] > peak_phase["error_deg"]:
                    peak_phase = dict(frame=frame, first=a, second=b, offset_hz=offsets[valid][i], error_deg=errors[i])
    p95 = np.percentile(phase_errors, 95) if phase_errors and np.iscomplexobj(coefficients) else None
    return dict(analysis_bandwidth_hz=bandwidth_hz, offsets_hz=offsets.tolist(), amplitude_floor=floor,
                rows=records, worst_complex=peak_error, numeric_worst_phase=peak_phase, worst_phase=peak_phase if physical_phase else None,
                numeric_phase_p95_deg=p95, phase_p95_deg=p95 if physical_phase else None,
                numeric_phase_count=len(phase_errors), phase_count=len(phase_errors) if physical_phase else 0, excluded_phase_count=excluded,
                receiver_band_power_mw=rx_power if q is not None else None, formal_measurement=False)
