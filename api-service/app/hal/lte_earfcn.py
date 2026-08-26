"""LTE downlink EARFCN working-point conversion for R&S CMW290/500.

This module deliberately does not reuse the NR-ARFCN converter.  The local
vendor manual is the authority:

* R&S CMW290/500 LTE UE User Manual 1173.9628.02-41, §2.2.23, p.91:
  ``N = 10 × (F - FOffset)/MHz + NOffset`` and offsets are the lower
  boundaries of the table ranges.
* Table 2-55, pp.93-95: FDD downlink ranges.
* Table 2-56, p.95: TDD ranges.

SCC-only rows are intentionally absent because MIMO OTA configures one LTE
PCell in P1-73A.  Option requirements are exposed separately; instrument
readiness validates them against the selected instrument snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Literal


LteDuplex = Literal["fdd", "tdd"]


@dataclass(frozen=True)
class LteDownlinkBand:
    band: str
    duplex: LteDuplex
    n_low: int
    n_high: int
    f_low_mhz: float


def _fdd(band: int, n_low: int, n_high: int, f_low_mhz: float) -> LteDownlinkBand:
    return LteDownlinkBand(f"B{band}", "fdd", n_low, n_high, f_low_mhz)


def _tdd(band: int, n_low: int, n_high: int, f_low_mhz: float) -> LteDownlinkBand:
    return LteDownlinkBand(f"B{band}", "tdd", n_low, n_high, f_low_mhz)


# R&S CMW LTE UE User Manual 1173.9628.02-41, Table 2-55, pp.93-95.
# Footnote-1/2 SCC-only bands (29/32/67/69/75/76/252/255) are excluded.
# Band 70 is excluded conservatively because Table 2-55 splits its DL range
# into PCC-capable and SCC-only sub-ranges with configurable separation.
_FDD_DOWNLINK = (
    _fdd(1, 0, 599, 2110.0), _fdd(2, 600, 1199, 1930.0),
    _fdd(3, 1200, 1949, 1805.0), _fdd(4, 1950, 2399, 2110.0),
    _fdd(5, 2400, 2649, 869.0), _fdd(6, 2650, 2749, 875.0),
    _fdd(7, 2750, 3449, 2620.0), _fdd(8, 3450, 3799, 925.0),
    _fdd(9, 3800, 4149, 1844.9), _fdd(10, 4150, 4749, 2110.0),
    _fdd(11, 4750, 4949, 1475.9), _fdd(12, 5010, 5179, 729.0),
    _fdd(13, 5180, 5279, 746.0), _fdd(14, 5280, 5379, 758.0),
    _fdd(15, 5380, 5579, 2600.0), _fdd(16, 5580, 5729, 2585.0),
    _fdd(17, 5730, 5849, 734.0), _fdd(18, 5850, 5999, 860.0),
    _fdd(19, 6000, 6149, 875.0), _fdd(20, 6150, 6449, 791.0),
    _fdd(21, 6450, 6599, 1495.9), _fdd(22, 6600, 7399, 3510.0),
    _fdd(23, 7500, 7699, 2180.0), _fdd(24, 7700, 8039, 1525.0),
    _fdd(25, 8040, 8689, 1930.0), _fdd(26, 8690, 9039, 859.0),
    _fdd(27, 9040, 9209, 852.0), _fdd(28, 9210, 9659, 758.0),
    _fdd(30, 9770, 9869, 2350.0), _fdd(31, 9870, 9919, 462.5),
    _fdd(65, 65536, 66435, 2110.0), _fdd(66, 66436, 67135, 2110.0),
    _fdd(68, 67536, 67835, 753.0), _fdd(71, 68586, 68935, 617.0),
    _fdd(72, 68936, 68985, 461.0), _fdd(73, 68986, 69035, 460.0),
    _fdd(74, 69036, 69465, 1475.0), _fdd(85, 70366, 70545, 728.0),
    _fdd(87, 70546, 70595, 420.0), _fdd(88, 70596, 70645, 422.0),
    _fdd(106, 70656, 70705, 935.0),
)

# R&S CMW LTE UE User Manual 1173.9628.02-41, Table 2-56, p.95.
# Bands 46/49 are SCC-only LAA and therefore absent.  Band 250 remains in the
# table but readiness must verify KS525 before it is used.
_TDD = (
    _tdd(33, 36000, 36199, 1900.0), _tdd(34, 36200, 36349, 2010.0),
    _tdd(35, 36350, 36949, 1850.0), _tdd(36, 36950, 37549, 1930.0),
    _tdd(37, 37550, 37749, 1910.0), _tdd(38, 37750, 38249, 2570.0),
    _tdd(39, 38250, 38649, 1880.0), _tdd(40, 38650, 39649, 2300.0),
    _tdd(41, 39650, 41589, 2496.0), _tdd(42, 41590, 43589, 3400.0),
    _tdd(43, 43590, 45589, 3600.0), _tdd(44, 45590, 46589, 703.0),
    _tdd(45, 46590, 46789, 1447.0), _tdd(48, 55240, 56739, 3550.0),
    _tdd(50, 58240, 59089, 1432.0), _tdd(51, 59090, 59139, 1427.0),
    _tdd(52, 59140, 60139, 3300.0), _tdd(53, 60140, 60254, 2483.5),
    _tdd(250, 253644, 255143, 3550.0),
)

_BANDS = {entry.band: entry for entry in (*_FDD_DOWNLINK, *_TDD)}

# §2.2.23 p.91: RF above 3.3 GHz needs KB036; Table 2-56 footnote 1:
# band 250 additionally needs KS525.
_REQUIRED_OPTIONS = {
    "B22": frozenset({"CMW-KB036"}),
    "B42": frozenset({"CMW-KB036"}),
    "B43": frozenset({"CMW-KB036"}),
    "B48": frozenset({"CMW-KB036"}),
    "B52": frozenset({"CMW-KB036"}),
    "B250": frozenset({"CMW-KB036", "CMW-KS525"}),
}


def normalize_lte_band(band: str | int) -> str:
    raw = str(band).strip().upper()
    if raw.startswith("B"):
        raw = raw[1:]
    if not raw.isdigit():
        raise ValueError(f"unsupported LTE PCell band: {band!r}")
    return f"B{int(raw)}"


def lte_downlink_band(band: str | int) -> LteDownlinkBand:
    normalized = normalize_lte_band(band)
    entry = _BANDS.get(normalized)
    if entry is None:
        raise ValueError(
            f"unsupported LTE PCell band {normalized}; unknown or SCC-only"
        )
    return entry


def required_options_for_lte_band(band: str | int) -> frozenset[str]:
    return _REQUIRED_OPTIONS.get(normalize_lte_band(band), frozenset())


def validate_lte_band_options(
    band: str | int,
    enabled_options: Iterable[str],
) -> None:
    required = required_options_for_lte_band(band)
    enabled = {str(option).strip().upper() for option in enabled_options}
    missing = {option for option in required if option.upper() not in enabled}
    if missing:
        raise ValueError(
            f"LTE {normalize_lte_band(band)} requires instrument options "
            f"{sorted(missing)}"
        )


def lte_dl_earfcn_to_frequency_mhz(band: str | int, dl_earfcn: int) -> float:
    entry = lte_downlink_band(band)
    if type(dl_earfcn) is not int or not entry.n_low <= dl_earfcn <= entry.n_high:
        raise ValueError(
            f"LTE {entry.band} PCell EARFCN must be within "
            f"[{entry.n_low}, {entry.n_high}]"
        )
    return entry.f_low_mhz + 0.1 * (dl_earfcn - entry.n_low)


def frequency_mhz_to_lte_dl_earfcn(band: str | int, frequency_mhz: float) -> int:
    """Return the exact LTE downlink EARFCN for one explicit band.

    Unlike the NR compatibility converter, this function is a strict write
    boundary: a value between the 100 kHz LTE raster points is rejected rather
    than rounded.  The band remains mandatory because LTE EARFCN ranges are
    band-scoped in the CMW manual tables cited at the top of this module.
    """

    entry = lte_downlink_band(band)
    if isinstance(frequency_mhz, bool) or not isinstance(frequency_mhz, (int, float)):
        raise ValueError("LTE frequency must be numeric")
    value = float(frequency_mhz)
    if not math.isfinite(value):
        raise ValueError("LTE frequency must be finite")
    candidate = round(entry.n_low + (value - entry.f_low_mhz) * 10.0)
    expected = lte_dl_earfcn_to_frequency_mhz(entry.band, candidate)
    if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(
            f"LTE {entry.band} frequency {value:g} MHz is not on the 100 kHz DL raster"
        )
    return candidate


def validate_lte_downlink_operating_point(
    *,
    band: str | int,
    duplex: str,
    dl_earfcn: int,
    frequency_mhz: float,
) -> float:
    entry = lte_downlink_band(band)
    normalized_duplex = str(duplex).strip().lower()
    if normalized_duplex != entry.duplex:
        raise ValueError(
            f"LTE {entry.band} duplex is {entry.duplex}, not {normalized_duplex}"
        )
    if not math.isfinite(frequency_mhz):
        raise ValueError("LTE frequency must be finite")
    expected = lte_dl_earfcn_to_frequency_mhz(entry.band, dl_earfcn)
    if not math.isclose(float(frequency_mhz), expected, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(
            f"LTE frequency {frequency_mhz:g} MHz conflicts with "
            f"{entry.band} DL EARFCN {dl_earfcn} ({expected:g} MHz)"
        )
    return expected
