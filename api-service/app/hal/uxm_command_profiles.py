"""
Keysight UXM E7515B — Test Application command profiles
========================================================

E7515B Platform hosts multiple Test Applications, each with its own SCPI
dialect. The platform itself (on hislip0) only exposes IEEE 488.2 core;
real test functionality lives in the Test Application Framework (hislip2)
under the currently-active Test Application.

Discovered at CAICT 2026-05-13 on live UXM:
  - hislip0 → "E7515B Platform"            (IEEE 488.2 only)
  - hislip2 → "Test Application Framework" (BSE:* + app-specific tree)
  - SYSTem:APPLication:NAME? identifies which app is running

Apps observed in the field:
  - "5G_NR_Test"   — pure 5G NR Standalone (SA) test, CONFig:NR5G:* root,
                     cells indexed from CELL0
  - "LTE_NR_IRAT"  — LTE + NR EN-DC / NSA inter-RAT, BSE:CONFig:NR5G:* root,
                     cells indexed from CELL1, BWP value uses BW<N> form
                     (e.g. "BW40" not "40")

Profile attributes mirror UxmScpiCommands; commands not verified to work
in a given app are set to ``None`` so caller methods can skip / log
"unsupported in profile {name}" without raising.
"""

from __future__ import annotations

from typing import Optional, Type


class UxmCommandProfile:
    """Base profile — IEEE 488.2 minimal set, common to every Test App.

    Subclasses override app-specific format strings. Driver methods read
    via ``self._cmds.X`` after profile is selected in ``connect()``.

    Format-string template variables:
      {cell} = e.g. "CELL0" / "CELL1"
      {bwp}  = e.g. "BWP0" / "BWP1"
      {ant}  = antenna index (1-based on UXM)
      {idx}  = SCC index for carrier aggregation
    """

    # --- Profile identity ---
    PROFILE_NAME: str = "base"
    APP_NAME_MATCH: tuple[str, ...] = ()   # e.g. ("5G_NR_Test",)
    PRIMARY_CELL: str = "CELL0"            # default cell id for set_cell_config
    PRIMARY_BWP: str = "BWP0"
    HISLIP_INDEX: int = 0                  # which hislip endpoint to connect

    # --- IEEE 488.2 / platform-mandatory ---
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    CLS = "*CLS"
    ERR = "SYSTem:ERRor?"

    # --- App selection (write-only) ---
    APP_SELECT: Optional[str] = None

    # --- Cell config (pre-templated; format with {cell}=CELL0/1/...) ---
    CELL_BAND: Optional[str] = None
    CELL_DL_ARFCN: Optional[str] = None
    CELL_DL_BW: Optional[str] = None
    CELL_UL_BW: Optional[str] = None
    CELL_SCS: Optional[str] = None
    CELL_DUPLEX: Optional[str] = None
    CELL_ACTIVE: Optional[str] = None
    CELL_DL_POINTA: Optional[str] = None

    # --- SSB ---
    SSB_ARFCN: Optional[str] = None

    # --- Downlink power ---
    DL_POWER: Optional[str] = None
    PDSCH_POWER: Optional[str] = None
    SSB_POWER: Optional[str] = None

    # --- PDSCH/PUSCH ---
    PDSCH_MCS: Optional[str] = None
    PDSCH_RB_ALLOC: Optional[str] = None
    PUSCH_MCS: Optional[str] = None
    PUSCH_RB_ALLOC: Optional[str] = None

    # --- MIMO logical layers ---
    MIMO_DL_LAYERS: Optional[str] = None
    MIMO_DL_CODEBOOK: Optional[str] = None

    # --- MIMO antenna → physical RF port routing ---
    MIMO_TX_ANT_PORT: Optional[str] = None
    MIMO_RX_ANT_PORT: Optional[str] = None
    MIMO_TX_ANT_PORT_QUERY: Optional[str] = None
    MIMO_RX_ANT_PORT_QUERY: Optional[str] = None

    # --- Cell signaling / state ---
    CELL_STATE_ON: Optional[str] = None
    CELL_STATE_OFF: Optional[str] = None
    CELL_STATE_QUERY: Optional[str] = None

    # --- Throughput measurement ---
    MEAS_BTHROUGHPUT_DL_START: Optional[str] = None
    MEAS_BTHROUGHPUT_DL_STOP: Optional[str] = None
    MEAS_BTHROUGHPUT_DL_JSON: Optional[str] = None
    MEAS_BTHROUGHPUT_DL_BLER: Optional[str] = None

    # --- UE capability / RRC reconfig ---
    UE_CAPABILITY_QUERY: Optional[str] = None
    UE_MAX_DL_LAYERS_QUERY: Optional[str] = None
    UE_MAX_UL_LAYERS_QUERY: Optional[str] = None
    UE_MAX_MODULATION_DL_QUERY: Optional[str] = None
    UE_SUPPORTED_BANDS_QUERY: Optional[str] = None

    RRC_RECONFIG_LAYERS: Optional[str] = None
    RRC_RECONFIG_MODULATION: Optional[str] = None
    RRC_RECONFIG_APPLY: Optional[str] = None

    # --- Carrier aggregation (SCell) ---
    SCELL_CONF_FREQ: Optional[str] = None
    SCELL_CONF_BW: Optional[str] = None
    SCELL_CONF_SCS: Optional[str] = None
    SCELL_CONF_BAND: Optional[str] = None
    SCELL_ADD: Optional[str] = None
    SCELL_ACTIVATE: Optional[str] = None
    SCELL_REMOVE_ALL: Optional[str] = None
    SCELL_LIST_QUERY: Optional[str] = None

    # --- CSI measurements ---
    MEAS_CSI_START: Optional[str] = None
    MEAS_CSI_STOP: Optional[str] = None
    MEAS_CSI_CQI: Optional[str] = None
    MEAS_CSI_RI: Optional[str] = None

    # --- UE Measurement Report (RSRP / SINR) ---
    MEAS_UE_RSRP: Optional[str] = None
    MEAS_UE_SINR: Optional[str] = None

    # --- EVM ---
    MEAS_EVM_START: Optional[str] = None

    # --- State save/load ---
    STATE_SAVE: Optional[str] = None
    STATE_LOAD: Optional[str] = None
    STATE_LIST: Optional[str] = None

    # --- RF routing ---
    RF_CONNECTOR: Optional[str] = None
    RF_PORT_DL: Optional[str] = None
    RF_PORT_UL: Optional[str] = None

    # --- TDD ---
    TDD_PATTERN: Optional[str] = None
    TDD_PERIOD: Optional[str] = None

    # --- PDSCH scheduling / AMC ---
    PDSCH_SCHED_ALGO: Optional[str] = None
    PDSCH_AMC_ENABLE: Optional[str] = None
    PUSCH_AMC_ENABLE: Optional[str] = None

    # --- HARQ ---
    HARQ_MAX_TRANS: Optional[str] = None
    HARQ_PROCESSES: Optional[str] = None

    # --- CSI-RS ports ---
    CSIRS_PORTS: Optional[str] = None

    # --- Throughput stat window ---
    MEAS_TPUT_STAT_COUNT: Optional[str] = None
    MEAS_TPUT_UL_JSON: Optional[str] = None
    MEAS_TPUT_UL_BLER: Optional[str] = None

    # --- Status ---
    STATUS_FAULTY: Optional[str] = None


class Uxm5GNRTestAppProfile(UxmCommandProfile):
    """Pure 5G NR Test Application — SA mode, CONFig:NR5G:* root.

    Cell indices CELL0..CELL3. This is the dialect the original UxmScpiCommands
    class was authored against (pre-CAICT-2026-05-13).
    """

    PROFILE_NAME = "5G_NR_Test"
    APP_NAME_MATCH = ("5G_NR_Test", "5G NR Test", "5G_NR_TEST")
    PRIMARY_CELL = "CELL0"
    PRIMARY_BWP = "BWP0"
    HISLIP_INDEX = 0   # historically connected via hislip0; works for SA app

    APP_SELECT = 'SYSTem:APPLication:NAME "5G_NR_Test"'

    CELL_BAND = "CONFig:NR5G:{cell}:BAND"
    CELL_DL_ARFCN = "CONFig:NR5G:{cell}:DL:ARFCN"
    CELL_DL_BW = "CONFig:NR5G:{cell}:DL:BW"
    CELL_UL_BW = "CONFig:NR5G:{cell}:UL:BW"
    CELL_SCS = "CONFig:NR5G:{cell}:SCS"
    CELL_DUPLEX = "CONFig:NR5G:{cell}:DUPLex"
    CELL_ACTIVE = "CONFig:NR5G:{cell}:ACTive:STATe"
    CELL_DL_POINTA = "CONFig:NR5G:{cell}:DL:POINta"

    SSB_ARFCN = "CONFig:NR5G:{cell}:{bwp}:SSB:NCD:ARFCn"

    DL_POWER = "CONFig:NR5G:{cell}:PHY:DL:POWer"
    PDSCH_POWER = "CONFig:NR5G:{cell}:{bwp}:PDSCH:POWer"
    SSB_POWER = "CONFig:NR5G:{cell}:SSB:POWer"

    PDSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PDSCH:MCS"
    PDSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PDSCH:RB:ALLocation"
    PUSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PUSCH:MCS"
    PUSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PUSCH:RB:ALLocation"

    MIMO_DL_LAYERS = "CONFig:NR5G:{cell}:PHY:DL:MIMO:LAYers"
    MIMO_DL_CODEBOOK = "CONFig:NR5G:{cell}:PHY:DL:MIMO:CODEbook"

    MIMO_TX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT"
    MIMO_RX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT"
    MIMO_TX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT?"
    MIMO_RX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT?"

    CELL_STATE_ON = "CONFig:NR5G:{cell}:ACTive:STATe ON"
    CELL_STATE_OFF = "CONFig:NR5G:{cell}:ACTive:STATe OFF"
    CELL_STATE_QUERY = "CONFig:NR5G:{cell}:ACTive:STATe?"

    MEAS_BTHROUGHPUT_DL_START = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STARt"
    MEAS_BTHROUGHPUT_DL_STOP = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STOP"
    MEAS_BTHROUGHPUT_DL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"
    MEAS_BTHROUGHPUT_DL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:DL:BLER:STATistical:ALL?"

    UE_CAPABILITY_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability?"
    UE_MAX_DL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:DL:LAYers?"
    UE_MAX_UL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:UL:LAYers?"
    UE_MAX_MODULATION_DL_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MODulation:DL?"
    UE_SUPPORTED_BANDS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:BANDs?"

    RRC_RECONFIG_LAYERS = "CALL:NR5G:{cell}:RRC:RECon:MIMO:LAYers {layers}"
    RRC_RECONFIG_MODULATION = "CALL:NR5G:{cell}:RRC:RECon:MODulation:DL {mod}"
    RRC_RECONFIG_APPLY = "CALL:NR5G:{cell}:RRC:RECon:APPLy"

    SCELL_CONF_FREQ = "CALL:NR5G:{cell}:SCEL{idx}:CONF:FREQuency {freq_mhz}MHz"
    SCELL_CONF_BW = "CALL:NR5G:{cell}:SCEL{idx}:CONF:BWIDth {bw_mhz}MHz"
    SCELL_CONF_SCS = "CALL:NR5G:{cell}:SCEL{idx}:CONF:SCS {scs_khz}KHz"
    SCELL_CONF_BAND = "CALL:NR5G:{cell}:SCEL{idx}:CONF:BAND {band}"
    SCELL_ADD = "CALL:NR5G:{cell}:SCEL{idx}:ADD"
    SCELL_ACTIVATE = "CALL:NR5G:{cell}:SCEL{idx}:ACTive ON"
    SCELL_REMOVE_ALL = "CALL:NR5G:{cell}:SCEL:REMove:ALL"
    SCELL_LIST_QUERY = "CALL:NR5G:{cell}:SCEL:LIST?"

    MEAS_CSI_START = "MEASure:NR5G:{cell}:CSI:STARt"
    MEAS_CSI_STOP = "MEASure:NR5G:{cell}:CSI:STOP"
    MEAS_CSI_CQI = "MEASure:NR5G:{cell}:CSI:CQI:STATistics?"
    MEAS_CSI_RI = "MEASure:NR5G:{cell}:CSI:RI:HISTogram?"

    MEAS_UE_RSRP = "MEASure:NR5G:{cell}:UEReport:RSRP:STATistics?"
    MEAS_UE_SINR = "MEASure:NR5G:{cell}:UEReport:SINR:STATistics?"

    MEAS_EVM_START = "MEASure:NR5G:{cell}:PHY:EVM:STARt"

    STATE_SAVE = 'SYSTem:CONFiguration:SAVE "{filepath}"'
    STATE_LOAD = 'SYSTem:CONFiguration:LOAD "{filepath}"'
    STATE_LIST = 'MMEMory:CATalog? "D:\\User Files"'

    RF_CONNECTOR = "CONFig:NR5G:{cell}:RFSettings:CHANnel"
    RF_PORT_DL = "CONFig:NR5G:{cell}:RFSettings:DL:PORT"
    RF_PORT_UL = "CONFig:NR5G:{cell}:RFSettings:UL:PORT"

    TDD_PATTERN = "CONFig:NR5G:{cell}:TDD:PATTern"
    TDD_PERIOD = "CONFig:NR5G:{cell}:TDD:PERiod"

    PDSCH_SCHED_ALGO = "CONFig:NR5G:{cell}:{bwp}:PDSCH:SchedAlgoritm"
    PDSCH_AMC_ENABLE = "CONFig:NR5G:{cell}:{bwp}:PDSCH:AMC:ENABle"
    PUSCH_AMC_ENABLE = "CONFig:NR5G:{cell}:{bwp}:PUSCH:AMC:ENABle"

    HARQ_MAX_TRANS = "CONFig:NR5G:{cell}:HARQ:MaxTrans"
    HARQ_PROCESSES = "CONFig:NR5G:{cell}:HARQ:PROCesses"

    CSIRS_PORTS = "CONFig:NR5G:{cell}:CSIRS:PORTs"

    MEAS_TPUT_STAT_COUNT = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:COUNt"
    MEAS_TPUT_UL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:UL:TSTatistics:JSON?"
    MEAS_TPUT_UL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:UL:BLER:STATistical:ALL?"

    STATUS_FAULTY = "STATus:FAULty:RECovery"


class UxmLteNrIratProfile(UxmCommandProfile):
    """LTE + NR Inter-RAT (EN-DC / NSA) Test Application.

    Hosted on hislip2 under the Test Application Framework. Commands rooted
    at BSE: (Base Station Emulator) and cells indexed from CELL1.

    Live-verified at CAICT 2026-05-13 against E7515B firmware 28.21.0.32.
    Commands marked ``None`` were probed and returned -113 "Undefined
    header"; driver methods should detect None and skip / log instead of
    sending. Filling them in requires firmware reference cross-check
    (the 110 MB SCPI HTML in Instrument_API_Doc/Keysight UXM NR SCPI/).

    Notable IRAT-specific value encoding:
      - Bandwidth: returns "BW40" (not raw "40"); set with same form
      - First user cell is CELL1; CELL0 doesn't exist in this app
      - Throughput JSON wraps NR cell index inside payload ("CellIndex": 0)
    """

    PROFILE_NAME = "LTE_NR_IRAT"
    APP_NAME_MATCH = ("LTE_NR_IRAT", "LTE+NR", "EN-DC", "LTE_NR")
    PRIMARY_CELL = "CELL1"
    PRIMARY_BWP = "BWP0"
    HISLIP_INDEX = 2   # Test Application Framework lives here

    # Note: app selection on E7515B Test App Framework is GUI-driven —
    # SCPI write to change app isn't safe to send unprompted.
    APP_SELECT = None

    # === Live-verified at CAICT 2026-05-13 ===
    CELL_BAND = "BSE:CONFig:NR5G:{cell}:BAND"
    CELL_DL_ARFCN = "BSE:CONFig:NR5G:{cell}:DL:ARFCN"
    CELL_DL_BW = "BSE:CONFig:NR5G:{cell}:DL:BW"        # value form "BW40"
    CELL_UL_BW = "BSE:CONFig:NR5G:{cell}:UL:BW"
    CELL_ACTIVE = "BSE:CONFig:NR5G:{cell}:ACTive:STATe"
    CELL_STATE_ON = "BSE:CONFig:NR5G:{cell}:ACTive:STATe 1"
    CELL_STATE_OFF = "BSE:CONFig:NR5G:{cell}:ACTive:STATe 0"
    CELL_STATE_QUERY = "BSE:CONFig:NR5G:{cell}:ACTive:STATe?"

    MEAS_BTHROUGHPUT_DL_JSON = "BSE:MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"

    # === IRAT-extras (not in 5G_NR_Test app) ===
    # PROPSIM channel emulator integration commands
    PROPSIM_IP = "BSE:CONFig:PROPsim:IPADdress"
    PROPSIM_EMULATION_STATE = "BSE:CONFig:PROPsim:EMULation:STATe"
    PROPSIM_EMULATION_RUN = "BSE:CONFig:PROPsim:EMULation:RUN"
    PROPSIM_EMULATION_STOP = "BSE:CONFig:PROPsim:EMULation:STOP"
    PROPSIM_EMULATION_LOAD = "BSE:CONFig:PROPsim:EMULation:LOAD"

    BSE_STATUS = "BSE:STATus?"
    BSE_SELECTED_CELL = "BSE:SELected:CELL?"
    BSE_INFO_LTE_CELL_NUMBER = "BSE:INFO:LTE:CELL:NUMBer?"
    BSE_NR5G_DEFAULT_TYPE = "BSE:CONFig:NR5G:DEFault:TYPE"   # NSA / SA
    BSE_NR5G_CA_MODE = "BSE:CONFig:NR5G:CAGGregation:MODE"
    BSE_LTE_CA_MODE = "BSE:CONFig:LTE:CAGGregation:MODE"

    # LTE side (live-verified for CELL1 BW + ACTive)
    LTE_CELL_DL_BW = "BSE:CONFig:LTE:{cell}:DL:BW"
    LTE_CELL_ACTIVE = "BSE:CONFig:LTE:{cell}:ACTive:STATe"

    # === Power commands — verified at CAICT 2026-05-13 after probe revealed
    # the initial guesses (:PHY:DL:POWer and :SSB:POWer) returned -113. The
    # IRAT app uses different mnemonics:
    #   DL power: BSE:CONFig:NR5G:<cell>:DL:POWer  (no :PHY: segment;
    #             optional [:EPRE] sub-node for EPRE-form value)
    #   SSB power: BSE:CONFig:NR5G:<cell>:SSB:POWer:ADVertised  (advertised
    #             form is the actually-routable one; bare :SSB:POWer is
    #             undefined header on this firmware)
    DL_POWER = "BSE:CONFig:NR5G:{cell}:DL:POWer"
    SSB_POWER = "BSE:CONFig:NR5G:{cell}:SSB:POWer:ADVertised"
    SCELL_CONF_BAND = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST"
    SCELL_ADD = "BSE:CONFig:LTE:{cell}:CAGGregation:ACTivate:SCC:LIST"
    SCELL_LIST_QUERY = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST?"

    # === Verified unsupported in this app (left as None per base) ===
    # CELL_SCS, CELL_DUPLEX, CELL_DL_POINTA, SSB_ARFCN,
    # MIMO_DL_LAYERS, MIMO_DL_CODEBOOK, MIMO_TX/RX_ANT_PORT*,
    # PDSCH_MCS / RB_ALLOC, PUSCH_MCS / RB_ALLOC,
    # UE_* (CALL: prefix not exposed), RRC_*,
    # MEAS_CSI_*, MEAS_UE_RSRP/SINR, MEAS_EVM_START,
    # STATE_*, RF_*, TDD_*, PDSCH_SCHED_ALGO, *_AMC_ENABLE, HARQ_*, CSIRS_PORTS,
    # MEAS_TPUT_STAT_COUNT, MEAS_TPUT_UL_*, STATUS_FAULTY
    # — driver should check `if cmd is not None` before sending.


# ===========================================================================
# Profile registry + detection
# ===========================================================================

ALL_PROFILES: tuple[Type[UxmCommandProfile], ...] = (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)


def detect_profile(app_name: str) -> Type[UxmCommandProfile]:
    """Return the profile class matching ``app_name`` (case-insensitive
    substring match against each profile's APP_NAME_MATCH tuple).

    Falls back to ``Uxm5GNRTestAppProfile`` for unrecognised apps —
    historically that's been the only profile and most existing labs use
    pure 5G NR Test App.
    """
    if not app_name:
        return Uxm5GNRTestAppProfile
    upper = app_name.upper()
    for profile in ALL_PROFILES:
        for tag in profile.APP_NAME_MATCH:
            if tag.upper() in upper:
                return profile
    return Uxm5GNRTestAppProfile


# Backward-compat alias — existing callsites import UxmScpiCommands from
# uxm_base_station; after the refactor, importing from here works too.
UxmScpiCommands = Uxm5GNRTestAppProfile
