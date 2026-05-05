"""ProbePattern file format parsers.

每个 parser 接受文件原始内容(bytes/str), 返回归一化的 `ParsedPattern`
(az_el 坐标系)。下游 import_service 不关心来源格式,只消费 ParsedPattern。

支持格式:
  - TICRA `.cut` — 业界主流, ϕ-cut 文本格式 (E_theta, E_phi 复数对)
  - CSV          — 简单二维表 (azimuth_deg, elevation_deg, gain_dbi)
  - JSON         — 结构化, 适合从其它系统导出

不支持(留尾巴):
  - TICRA `.swe` (球面波展开, 解码相对复杂, 需要 special math 库)
  - HFSS `.ffd`  (使用率低)
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParsedPattern:
    """归一化的方向图数据, 来自任意 parser。

    约定:
      - azimuth_deg: 0..360 (单调递增)
      - elevation_deg: 0..180 (0=top, 90=horizon, 180=bottom)
      - gain_pattern_dbi: 行优先扁平数组,
        长度 = len(elevation_deg) × len(azimuth_deg),
        index = el_idx * len(azimuth_deg) + az_idx
      - peak_gain_dbi / peak_az_deg / peak_el_deg: 整张方向图的最大增益位置
      - hpbw_*: -3 dB 波束宽度, 不强制要求 parser 计算 (None = 由 import_service 推算)
      - source_coordinate_system: 'az_el' | 'theta_phi' (导入时用,记原始格式溯源)
    """

    azimuth_deg: List[float]
    elevation_deg: List[float]
    gain_pattern_dbi: List[float]

    peak_gain_dbi: Optional[float] = None
    peak_azimuth_deg: Optional[float] = None
    peak_elevation_deg: Optional[float] = None
    hpbw_azimuth_deg: Optional[float] = None
    hpbw_elevation_deg: Optional[float] = None
    front_to_back_ratio_db: Optional[float] = None

    source_coordinate_system: str = "az_el"
    warnings: List[str] = field(default_factory=list)

    def compute_peak_if_missing(self) -> None:
        """填充 peak_* 字段(若 parser 没给)。"""
        if self.peak_gain_dbi is not None:
            return
        if not self.gain_pattern_dbi:
            return
        peak_idx = max(range(len(self.gain_pattern_dbi)), key=lambda i: self.gain_pattern_dbi[i])
        self.peak_gain_dbi = float(self.gain_pattern_dbi[peak_idx])
        n_az = len(self.azimuth_deg)
        if n_az > 0:
            el_idx, az_idx = divmod(peak_idx, n_az)
            if 0 <= el_idx < len(self.elevation_deg):
                self.peak_elevation_deg = float(self.elevation_deg[el_idx])
            if 0 <= az_idx < n_az:
                self.peak_azimuth_deg = float(self.azimuth_deg[az_idx])


# ============================================================
# JSON parser (最简单, 先做)
# ============================================================


class JsonParser:
    """Parse JSON pattern files.

    Required keys (minimum): azimuth_deg, elevation_deg, gain_pattern_dbi
    Optional: peak_gain_dbi, peak_az/el, hpbw_az/el, front_to_back_ratio_db,
              coordinate_system
    """

    file_format = "json"

    @staticmethod
    def parse(content: str | bytes) -> ParsedPattern:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        data = json.loads(text)

        for key in ("azimuth_deg", "elevation_deg", "gain_pattern_dbi"):
            if key not in data:
                raise ValueError(f"JSON pattern missing required key: {key}")

        gain = data["gain_pattern_dbi"]
        # Tolerate both flat and 2D nested arrays
        if gain and isinstance(gain[0], list):
            gain = [v for row in gain for v in row]

        coord = data.get("coordinate_system") or "az_el"

        result = ParsedPattern(
            azimuth_deg=list(data["azimuth_deg"]),
            elevation_deg=list(data["elevation_deg"]),
            gain_pattern_dbi=[float(v) for v in gain],
            peak_gain_dbi=data.get("peak_gain_dbi"),
            peak_azimuth_deg=data.get("peak_azimuth_deg") or data.get("peak_az_deg"),
            peak_elevation_deg=data.get("peak_elevation_deg") or data.get("peak_el_deg"),
            hpbw_azimuth_deg=data.get("hpbw_azimuth_deg") or data.get("hpbw_az_deg"),
            hpbw_elevation_deg=data.get("hpbw_elevation_deg") or data.get("hpbw_el_deg"),
            front_to_back_ratio_db=data.get("front_to_back_ratio_db"),
            source_coordinate_system=coord,
        )

        expected_len = len(result.azimuth_deg) * len(result.elevation_deg)
        if len(result.gain_pattern_dbi) != expected_len:
            raise ValueError(
                f"JSON gain_pattern_dbi length {len(result.gain_pattern_dbi)} "
                f"!= expected {expected_len} (= {len(result.elevation_deg)} el × "
                f"{len(result.azimuth_deg)} az)"
            )

        if coord == "theta_phi":
            result = _convert_theta_phi_to_az_el(result)

        result.compute_peak_if_missing()
        return result


# ============================================================
# CSV parser
# ============================================================


class CsvParser:
    """Parse CSV pattern files.

    Two layouts supported:
      1. Long format: columns (azimuth_deg, elevation_deg, gain_dbi)
         — one row per measurement point. Most flexible.
      2. Wide format: first row = azimuths, first col = elevations,
         body = gain values. Detected when no 'azimuth_deg' header found.

    Long format must have a header row with case-insensitive column names.
    """

    file_format = "csv"

    @staticmethod
    def parse(content: str | bytes) -> ParsedPattern:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        # Sniff for long vs wide
        sample = text.strip().splitlines()[:3]
        first_row = (sample[0] if sample else "").lower()
        if "azimuth" in first_row and "elevation" in first_row and "gain" in first_row:
            return CsvParser._parse_long(text)
        return CsvParser._parse_wide(text)

    @staticmethod
    def _parse_long(text: str) -> ParsedPattern:
        reader = csv.DictReader(io.StringIO(text))
        # Normalize column names
        col_az = col_el = col_g = None
        for fieldname in reader.fieldnames or []:
            lc = fieldname.lower().strip()
            if "azimuth" in lc:
                col_az = fieldname
            elif "elevation" in lc:
                col_el = fieldname
            elif "gain" in lc:
                col_g = fieldname
        if not (col_az and col_el and col_g):
            raise ValueError(
                "CSV long format needs columns containing 'azimuth', 'elevation', "
                f"'gain' (got: {reader.fieldnames})"
            )

        rows = []
        for row in reader:
            try:
                rows.append((
                    float(row[col_az]),
                    float(row[col_el]),
                    float(row[col_g]),
                ))
            except (ValueError, KeyError) as e:
                raise ValueError(f"CSV row parse error: {row} ({e})") from e

        if not rows:
            raise ValueError("CSV had header but no data rows")

        # Build az/el grids from unique values, sorted
        az_set = sorted({r[0] for r in rows})
        el_set = sorted({r[1] for r in rows})
        gain_lookup = {(r[0], r[1]): r[2] for r in rows}

        gain_flat: List[float] = []
        missing = 0
        for el in el_set:
            for az in az_set:
                if (az, el) in gain_lookup:
                    gain_flat.append(gain_lookup[(az, el)])
                else:
                    gain_flat.append(float("-inf"))
                    missing += 1

        warnings: List[str] = []
        if missing > 0:
            warnings.append(
                f"{missing} grid cells had no data (filled with -inf); "
                f"input may be sparse — verify az/el grid completeness"
            )

        result = ParsedPattern(
            azimuth_deg=az_set,
            elevation_deg=el_set,
            gain_pattern_dbi=gain_flat,
            warnings=warnings,
        )
        result.compute_peak_if_missing()
        return result

    @staticmethod
    def _parse_wide(text: str) -> ParsedPattern:
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2 or len(rows[0]) < 2:
            raise ValueError(
                "CSV wide format needs ≥2 rows × ≥2 cols (first row = azimuths, "
                "first col = elevations, body = gain dBi)"
            )
        # First row's first cell is corner placeholder (e.g., "el\\az"); rest are azimuths
        try:
            azimuths = [float(c) for c in rows[0][1:]]
        except ValueError as e:
            raise ValueError(f"CSV wide: header azimuths not numeric ({e})") from e

        elevations: List[float] = []
        gain_flat: List[float] = []
        for r in rows[1:]:
            if not r:
                continue
            try:
                elevations.append(float(r[0]))
                gain_flat.extend(float(c) for c in r[1:])
            except ValueError as e:
                raise ValueError(f"CSV wide: row parse error {r} ({e})") from e

        if len(gain_flat) != len(azimuths) * len(elevations):
            raise ValueError(
                f"CSV wide: {len(gain_flat)} gain values != "
                f"{len(elevations)}×{len(azimuths)} grid"
            )

        result = ParsedPattern(
            azimuth_deg=azimuths,
            elevation_deg=elevations,
            gain_pattern_dbi=gain_flat,
        )
        result.compute_peak_if_missing()
        return result


# ============================================================
# TICRA `.cut` parser (业界主流)
# ============================================================
#
# Format reference (TICRA GRASP / Office documentation):
#
#   Line 1: free-text header per ϕ-cut (one cut block; multiple blocks for
#           multiple ϕ values)
#   Line 2: V_INI V_INC V_NUM C ICOMP ICUT NCOMP
#           - V_INI:  starting θ (degrees)
#           - V_INC:  θ step
#           - V_NUM:  number of θ samples
#           - C:      ϕ (degrees) of this cut
#           - ICOMP:  field component code
#                      1 = E_theta, E_phi (linear, complex pairs)
#                      2 = E_RHC, E_LHC (circular)
#                      3 = E_co, E_x (Ludwig 3, polarization-aware)
#           - ICUT:   1 = standard polar cut
#           - NCOMP:  2 (always 2 components per row)
#   Line 3..N+2: real_1 imag_1 real_2 imag_2  (one row per θ sample)
#
# We extract magnitude in dBi: 20*log10(|E|) for the chosen polarization.
# For ICOMP=3 (Ludwig 3), the first pair is co-pol — that's the one we want
# for "the V probe's V output" or "the H probe's H output".


class TicraCutParser:
    """Parse TICRA `.cut` text format.

    Convention assumed:
      - Each block is a ϕ-cut at fixed phi
      - Multiple blocks → 2D pattern (theta varies fast, phi slow)
      - Polarization label is provided externally (the .cut file format
        doesn't carry V/H semantics in a standardized way; the operator
        knows which probe port produced the file)

    Output is in theta_phi coordinate system (TICRA native). Caller
    converts to az_el via _convert_theta_phi_to_az_el if needed; we do that
    automatically before returning ParsedPattern (so downstream is uniform).
    """

    file_format = "ticra_cut"

    @staticmethod
    def parse(content: str | bytes) -> ParsedPattern:
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < 3:
            raise ValueError(f"TICRA .cut file has only {len(lines)} non-blank lines; need ≥3")

        thetas_master: Optional[List[float]] = None
        phis: List[float] = []
        # Per-phi gain rows; each row is a theta-vs-gain list at that phi
        gain_by_phi: List[List[float]] = []

        i = 0
        while i < len(lines):
            # Line i: header (text); skip
            if i + 1 >= len(lines):
                break
            params_line = lines[i + 1]
            tokens = params_line.split()
            if len(tokens) < 5:
                # Not a parameter line; advance and keep looking
                i += 1
                continue
            try:
                v_ini = float(tokens[0])
                v_inc = float(tokens[1])
                v_num = int(float(tokens[2]))
                c_phi = float(tokens[3])
                icomp = int(float(tokens[4]))
            except ValueError:
                # Header didn't parse; advance and look for next block
                i += 1
                continue

            data_start = i + 2
            data_end = data_start + v_num
            if data_end > len(lines):
                raise ValueError(
                    f"TICRA block at phi={c_phi}: declared {v_num} samples but "
                    f"only {len(lines) - data_start} data lines remain"
                )

            thetas = [v_ini + k * v_inc for k in range(v_num)]
            if thetas_master is None:
                thetas_master = thetas
            elif thetas != thetas_master:
                raise ValueError(
                    f"TICRA block at phi={c_phi} has different θ grid than first block "
                    "(parser only supports uniform θ grids across cuts)"
                )

            row: List[float] = []
            for k in range(v_num):
                parts = lines[data_start + k].split()
                if len(parts) < 4:
                    raise ValueError(
                        f"TICRA θ row {k} at phi={c_phi}: needs 4 values "
                        f"(real1 imag1 real2 imag2), got {parts}"
                    )
                # ICOMP=1 → first pair is E_theta; ICOMP=3 → first pair is co-pol
                # (we always pick the first pair, which is the desired polarization
                # for both encodings when used correctly)
                re1 = float(parts[0])
                im1 = float(parts[1])
                # |E|² = re² + im²; gain_dbi = 20 log10 |E| (assuming reference
                # field of 1 V/m at boresight; vendors typically pre-normalize)
                mag2 = re1 * re1 + im1 * im1
                if mag2 <= 0:
                    gain_db = float("-inf")
                else:
                    gain_db = 10.0 * math.log10(mag2)
                row.append(gain_db)

            phis.append(c_phi)
            gain_by_phi.append(row)
            i = data_end

        if thetas_master is None or not phis:
            raise ValueError("TICRA .cut: no valid blocks found")

        # gain_by_phi is [phi][theta]; we want flat row-major in (el, az) order
        # If we treat theta as elevation and phi as azimuth (theta_phi system),
        # then index = phi_idx * len(theta) + theta_idx
        # We store in source_coordinate_system='theta_phi' and convert later.
        gain_flat: List[float] = []
        for phi_idx in range(len(phis)):
            gain_flat.extend(gain_by_phi[phi_idx])

        result = ParsedPattern(
            azimuth_deg=phis,  # ϕ → az
            elevation_deg=thetas_master,  # θ → el (will convert below)
            gain_pattern_dbi=gain_flat,
            source_coordinate_system="theta_phi",
        )
        # Reshape from theta_phi (phi outer, theta inner) to az_el (el outer, az inner)
        result = _theta_phi_layout_to_az_el_layout(result)
        result.compute_peak_if_missing()
        return result


# ============================================================
# Coordinate / layout conversions
# ============================================================


def _theta_phi_layout_to_az_el_layout(p: ParsedPattern) -> ParsedPattern:
    """Convert (phi-outer, theta-inner) flat layout to (el-outer, az-inner).

    Input p.azimuth_deg = phi list, p.elevation_deg = theta list.
    Input gain index = phi_idx * len(theta) + theta_idx.
    Output: az = phi (unchanged), el = theta (unchanged for now;
    no spherical reflection — TICRA θ ∈ [0, 180] already aligns with our
    elevation convention 0=top, 180=bottom).
    """
    n_phi = len(p.azimuth_deg)
    n_theta = len(p.elevation_deg)
    # Re-index: out[el_idx * n_az + az_idx] where el_idx → theta_idx, az_idx → phi_idx
    new_flat = [0.0] * (n_theta * n_phi)
    for phi_idx in range(n_phi):
        for theta_idx in range(n_theta):
            old = phi_idx * n_theta + theta_idx
            new = theta_idx * n_phi + phi_idx
            new_flat[new] = p.gain_pattern_dbi[old]
    p.gain_pattern_dbi = new_flat
    p.source_coordinate_system = "theta_phi"  # preserve provenance
    return p


def _convert_theta_phi_to_az_el(p: ParsedPattern) -> ParsedPattern:
    """If incoming JSON declared theta_phi axes, just record provenance.

    Numerically the (theta=el, phi=az) mapping is identity for our convention
    (el ∈ [0,180], az ∈ [0,360]). We preserve `source_coordinate_system` so
    auditors can see the original encoding; data values are unchanged.
    """
    p.source_coordinate_system = "theta_phi"
    return p


# ============================================================
# Dispatcher
# ============================================================


_PARSERS = {
    "ticra_cut": TicraCutParser,
    "csv": CsvParser,
    "json": JsonParser,
}


def get_parser(file_format: str):
    """Return parser class by format key. Raises ValueError on unknown."""
    parser = _PARSERS.get(file_format.lower())
    if parser is None:
        raise ValueError(
            f"Unsupported file format '{file_format}'; "
            f"supported: {list(_PARSERS.keys())}"
        )
    return parser


def detect_format_from_filename(filename: str) -> Optional[str]:
    """Best-effort format detection from filename suffix. None if ambiguous."""
    lc = filename.lower()
    if lc.endswith(".cut"):
        return "ticra_cut"
    if lc.endswith(".csv"):
        return "csv"
    if lc.endswith(".json"):
        return "json"
    return None
