"""
Dummy Calibration Data Seeder for CATR-16-Dual Chamber (PostgreSQL)

为 CATR-16-Dual 暗室配置填充完备的 Dummy 校准数据，用于调试和
Bypass 真正的硬件校准流程。所有数据均为物理上合理但非实测的模拟值。

使用方法:
    cd /Users/Simon/Tools/MIMO-First/api-service
    .venv/bin/python scripts/seed_dummy_calibration.py
"""

import uuid
import json
import random
import math
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text

PG_URL = "postgresql://meta3d:meta3d_password@localhost:5432/meta3d_ota"
CHAMBER_ID = "59c73fbe-7362-4004-9a80-f72dd8779c3e"  # CAICT-16-Probe-Dual (active in PG)
CALIBRATOR = "SYSTEM_SEED"
NOW = datetime.utcnow()
VALID_UNTIL = NOW + timedelta(days=365)

# 频率点 (n77 Band: 3300-3800 MHz, 100MHz step)
FREQ_POINTS = [3300, 3400, 3500, 3600, 3700, 3800]


def uid():
    return uuid.uuid4().hex


def seed_probes_inline_calibration(conn):
    """更新 probes 表的 calibration_status 和 calibration_data 字段"""
    print("[1/9] Updating probes inline calibration fields...")
    
    probes = conn.execute(text(
        "SELECT id, probe_number, ring, polarization FROM probes ORDER BY probe_number"
    )).fetchall()
    
    for pid, pnum, ring, pol in probes:
        gain = round(8.0 + random.gauss(0, 0.15), 2)
        cal_data = {
            "frequency_mhz": FREQ_POINTS,
            "gain_offset_dbi": [round(random.gauss(0, 0.2), 3) for _ in FREQ_POINTS],
            "phase_offset_deg": [round(random.gauss(0, 1.5), 2) for _ in FREQ_POINTS],
        }
        conn.execute(text("""
            UPDATE probes SET 
               calibration_status = :status,
               calibration_data = :cal_data,
               last_calibration_date = :cal_date,
               gain_db = :gain
            WHERE id = :pid
        """), {
            "status": "valid",
            "cal_data": json.dumps(cal_data),
            "cal_date": NOW,
            "gain": gain,
            "pid": str(pid),
        })
    print(f"   → Updated {len(probes)} probes")


def seed_amplitude_calibrations(conn):
    """探头幅度校准 (probe_amplitude_calibrations)"""
    print("[2/9] Seeding probe amplitude calibrations...")
    
    # 先清除旧的 SYSTEM_SEED 数据
    conn.execute(text("DELETE FROM probe_amplitude_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    probes = conn.execute(text("SELECT id, probe_number, polarization FROM probes ORDER BY probe_number")).fetchall()
    count = 0
    for pid, pnum, pol in probes:
        tx_gains = [round(8.0 + random.gauss(0, 0.2), 3) for _ in FREQ_POINTS]
        rx_gains = [round(7.8 + random.gauss(0, 0.2), 3) for _ in FREQ_POINTS]
        conn.execute(text("""
            INSERT INTO probe_amplitude_calibrations 
               (id, probe_id, polarization, frequency_points_mhz, 
                tx_gain_dbi, rx_gain_dbi, tx_gain_uncertainty_db, rx_gain_uncertainty_db,
                reference_antenna, reference_power_meter,
                temperature_celsius, humidity_percent,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:probe_id,:pol,:freq,
                    :tx,:rx,:txu,:rxu,
                    :ref_ant,:ref_pm,
                    :temp,:hum,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "probe_id": pnum, "pol": pol, "freq": json.dumps(FREQ_POINTS),
            "tx": json.dumps(tx_gains), "rx": json.dumps(rx_gains),
            "txu": json.dumps([0.3]*len(FREQ_POINTS)), "rxu": json.dumps([0.3]*len(FREQ_POINTS)),
            "ref_ant": "Schwarzbeck BBHA 9120 D SN:DUMMY-001", "ref_pm": "Keysight N1913A SN:DUMMY-002",
            "temp": 23.0, "hum": 45.0,
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def seed_phase_calibrations(conn):
    """探头相位校准 (probe_phase_calibrations)"""
    print("[3/9] Seeding probe phase calibrations...")
    
    conn.execute(text("DELETE FROM probe_phase_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    probes = conn.execute(text("SELECT probe_number, polarization FROM probes ORDER BY probe_number")).fetchall()
    count = 0
    for pnum, pol in probes:
        phase_offsets = [round(random.gauss(0, 2.0) if pnum > 1 else 0.0, 2) for _ in FREQ_POINTS]
        group_delays = [round(0.5 + random.gauss(0, 0.05), 3) for _ in FREQ_POINTS]
        conn.execute(text("""
            INSERT INTO probe_phase_calibrations
               (id, probe_id, polarization, reference_probe_id,
                frequency_points_mhz, phase_offset_deg, group_delay_ns, phase_uncertainty_deg,
                vna_model, vna_serial,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:pid,:pol,:ref,
                    :freq,:phase,:delay,:unc,
                    :vna,:vna_sn,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "pid": pnum, "pol": pol, "ref": 0,
            "freq": json.dumps(FREQ_POINTS), "phase": json.dumps(phase_offsets),
            "delay": json.dumps(group_delays), "unc": json.dumps([1.0]*len(FREQ_POINTS)),
            "vna": "Keysight N5227B PNA", "vna_sn": "SN:DUMMY-VNA-001",
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def seed_polarization_calibrations(conn):
    """探头极化校准 (probe_polarization_calibrations)"""
    print("[4/9] Seeding probe polarization calibrations...")
    
    conn.execute(text("DELETE FROM probe_polarization_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    probes = conn.execute(text("SELECT probe_number FROM probes ORDER BY probe_number")).fetchall()
    count = 0
    for (pnum,) in probes:
        v_to_h = round(25.0 + random.gauss(0, 1.5), 1)
        h_to_v = round(24.0 + random.gauss(0, 1.5), 1)
        iso_vs_freq = [round(25.0 + random.gauss(0, 1.0), 1) for _ in FREQ_POINTS]
        conn.execute(text("""
            INSERT INTO probe_polarization_calibrations
               (id, probe_id, probe_type,
                v_to_h_isolation_db, h_to_v_isolation_db,
                frequency_points_mhz, isolation_vs_frequency_db,
                reference_antenna, positioner,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:pid,:ptype,
                    :vth,:htv,
                    :freq,:iso,
                    :ref,:pos,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "pid": pnum, "ptype": "dual_linear",
            "vth": v_to_h, "htv": h_to_v,
            "freq": json.dumps(FREQ_POINTS), "iso": json.dumps(iso_vs_freq),
            "ref": "Schwarzbeck BBHA 9120 D", "pos": "Orbit FR 5060",
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def seed_path_loss_calibrations(conn):
    """探头路径损耗校准 (probe_path_loss_calibrations)"""
    print("[5/9] Seeding probe path loss calibrations...")
    
    conn.execute(text("DELETE FROM probe_path_loss_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    probes = conn.execute(text("SELECT probe_number, ring, polarization FROM probes ORDER BY probe_number")).fetchall()
    count = 0
    
    for freq in FREQ_POINTS:
        fspl_base = 20*math.log10(4.0) + 20*math.log10(freq*1e6) - 147.55
        
        probe_losses = {}
        for pnum, ring, pol in probes:
            ring_offset = (ring - 1) * 0.3
            loss = round(fspl_base + ring_offset + random.gauss(0, 0.3), 2)
            probe_losses[str(pnum)] = {
                "path_loss_db": loss,
                "uncertainty_db": 0.5,
                "pol_v_db": loss if pol == "V" else loss + 0.2,
                "pol_h_db": loss if pol == "H" else loss + 0.2,
            }
        
        losses_list = [v["path_loss_db"] for v in probe_losses.values()]
        avg_loss = sum(losses_list)/len(losses_list)
        conn.execute(text("""
            INSERT INTO probe_path_loss_calibrations
               (id, chamber_id, frequency_mhz, probe_path_losses,
                sgh_model, sgh_serial, sgh_gain_dbi, sgh_certificate_date,
                vna_model, vna_if_bandwidth_hz, cable_loss_db, measurement_distance_m,
                temperature_celsius, humidity_percent,
                avg_path_loss_db, max_path_loss_db, min_path_loss_db, std_dev_db,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:cid,:freq,:losses,
                    :sgh,:sgh_sn,:sgh_gain,:sgh_date,
                    :vna,:ifbw,:cable,:dist,
                    :temp,:hum,
                    :avg,:mx,:mn,:std,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "cid": CHAMBER_ID, "freq": freq, "losses": json.dumps(probe_losses),
            "sgh": "ETS-Lindgren 3164-06", "sgh_sn": "SN:SGH-DUMMY-001", "sgh_gain": 6.1, "sgh_date": NOW,
            "vna": "Keysight N5227B PNA", "ifbw": 100.0, "cable": 2.5, "dist": 4.0,
            "temp": 23.0, "hum": 45.0,
            "avg": round(avg_loss, 2), "mx": round(max(losses_list), 2),
            "mn": round(min(losses_list), 2),
            "std": round((sum((x - avg_loss)**2 for x in losses_list) / len(losses_list))**0.5, 3),
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records (one per frequency point)")


def seed_rf_chain_calibrations(conn):
    """RF 链路校准 (rf_chain_calibrations) - 下行含 PA"""
    print("[6/9] Seeding RF chain calibrations...")
    
    conn.execute(text("DELETE FROM rf_chain_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    count = 0
    for freq in FREQ_POINTS:
        probe_chain = {}
        for pnum in range(1, 33):
            probe_chain[str(pnum)] = {
                "gain_db": round(20.0 + random.gauss(0, 0.2), 2),
                "phase_deg": round(random.gauss(0, 1.5), 2),
            }
        
        conn.execute(text("""
            INSERT INTO rf_chain_calibrations
               (id, chamber_id, chain_type, frequency_mhz,
                has_lna, has_pa, pa_model, pa_serial,
                pa_gain_measured_db, pa_p1db_measured_dbm,
                has_duplexer,
                cable_loss_to_ce_db, cable_loss_to_probe_db,
                total_chain_gain_db, probe_chain_data,
                vna_model, temperature_celsius,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:cid,:chain,:freq,
                    :lna,:pa,:pa_model,:pa_sn,
                    :pa_gain,:pa_p1db,
                    :dup,
                    :cable_ce,:cable_probe,
                    :total,:chain_data,
                    :vna,:temp,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "cid": CHAMBER_ID, "chain": "downlink", "freq": freq,
            "lna": False, "pa": True, "pa_model": "Mini-Circuits ZHL-20W-13+", "pa_sn": "SN:PA-DUMMY-001",
            "pa_gain": round(20.0 + random.gauss(0, 0.1), 2), "pa_p1db": round(20.0 + random.gauss(0, 0.2), 1),
            "dup": False,
            "cable_ce": round(2.5 + random.gauss(0, 0.1), 2), "cable_probe": round(1.5 + random.gauss(0, 0.1), 2),
            "total": round(16.0 + random.gauss(0, 0.15), 2), "chain_data": json.dumps(probe_chain),
            "vna": "Keysight N5227B PNA", "temp": 23.0,
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def seed_link_calibrations(conn):
    """链路端到端校准 (link_calibrations)"""
    print("[7/9] Seeding link (end-to-end) calibrations...")
    
    conn.execute(text("DELETE FROM link_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    probe_links = []
    for pnum in range(1, 33):
        probe_links.append({
            "probe_id": pnum,
            "link_loss_db": round(35.0 + random.gauss(0, 0.5), 2),
            "phase_offset_deg": round(random.gauss(0, 2.0), 2),
        })
    
    conn.execute(text("""
        INSERT INTO link_calibrations
           (id, calibration_type, standard_dut_type, standard_dut_model, standard_dut_serial,
            known_gain_dbi, frequency_mhz,
            measured_gain_dbi, deviation_db,
            probe_link_calibrations,
            validation_pass, threshold_db,
            calibrated_at, calibrated_by)
        VALUES (:id,:ctype,:dut_type,:dut_model,:dut_sn,
                :known,:freq,
                :measured,:dev,
                :links,
                :vpass,:thresh,
                :cal_at,:cal_by)
    """), {
        "id": uid(), "ctype": "pre_test", "dut_type": "dipole",
        "dut_model": "Schwarzbeck SBA 9113", "dut_sn": "SN:DUT-DUMMY-001",
        "known": 2.15, "freq": 3500.0,
        "measured": 2.18, "dev": 0.03,
        "links": json.dumps(probe_links),
        "vpass": True, "thresh": 1.0,
        "cal_at": NOW, "cal_by": CALIBRATOR,
    })
    print(f"   → Inserted 1 record")


def seed_channel_phase_calibrations(conn):
    """通道相位校准 (channel_phase_calibrations)"""
    print("[8/9] Seeding channel phase calibrations...")
    
    conn.execute(text("DELETE FROM channel_phase_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    count = 0
    for freq in FREQ_POINTS:
        channel_phases = []
        for ch in range(32):
            channel_phases.append({
                "channel_id": ch,
                "phase_deg": round(random.gauss(0, 2.0) if ch > 0 else 0.0, 2),
                "amplitude_db": round(random.gauss(0, 0.15), 3),
            })
        
        phase_devs = [abs(c["phase_deg"]) for c in channel_phases]
        compensation = [{"channel_id": c["channel_id"], "compensation_deg": round(-c["phase_deg"], 2)} for c in channel_phases]
        
        conn.execute(text("""
            INSERT INTO channel_phase_calibrations
               (id, chamber_id, frequency_mhz, reference_channel_id,
                channel_phases, coherence_score,
                max_phase_deviation_deg, mean_phase_deviation_deg, std_phase_deviation_deg,
                phase_compensation, compensation_applied,
                vna_model, measurement_method,
                calibrated_at, calibrated_by, valid_until, status)
            VALUES (:id,:cid,:freq,:ref,
                    :phases,:coh,
                    :mx,:mean,:std,
                    :comp,:applied,
                    :vna,:method,
                    :cal_at,:cal_by,:valid,:st)
        """), {
            "id": uid(), "cid": CHAMBER_ID, "freq": freq, "ref": 0,
            "phases": json.dumps(channel_phases), "coh": round(0.98 + random.gauss(0, 0.005), 4),
            "mx": round(max(phase_devs), 2), "mean": round(sum(phase_devs)/len(phase_devs), 2),
            "std": round((sum(d**2 for d in phase_devs)/len(phase_devs))**0.5, 2),
            "comp": json.dumps(compensation), "applied": True,
            "vna": "Keysight N5227B PNA", "method": "vna",
            "cal_at": NOW, "cal_by": CALIBRATOR, "valid": VALID_UNTIL, "st": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def seed_ce_internal_calibrations(conn):
    """CE 内部校准 (ce_internal_calibrations)"""
    print("[9/9] Seeding CE internal calibrations...")
    
    conn.execute(text("DELETE FROM ce_internal_calibrations WHERE calibrated_by = :cb"), {"cb": CALIBRATOR})
    
    channels_data = []
    for ch in range(64):
        channels_data.append({
            "channel_id": ch,
            "power_offset_db": round(random.gauss(0, 0.1), 3),
            "phase_offset_deg": round(random.gauss(0, 0.5), 2),
            "delay_offset_ns": round(random.gauss(0, 0.2), 3),
        })
    
    conn.execute(text("""
        INSERT INTO ce_internal_calibrations
           (id, ce_id, vendor, calibration_type,
            frequency_start_mhz, frequency_stop_mhz,
            channel_count, channels_data,
            max_power_deviation_db, max_phase_deviation_deg, max_delay_deviation_ns,
            pass_criteria, power_tolerance_db, phase_tolerance_deg, delay_tolerance_ns,
            firmware_version,
            calibrated_at, calibrated_by, notes, valid_until, status)
        VALUES (:id,:ce,:vendor,:ctype,
                :fstart,:fstop,
                :chcount,:chdata,
                :mp,:mph,:md,
                :pass,:ptol,:phtol,:dtol,
                :fw,
                :cal_at,:cal_by,:notes,:valid,:st)
    """), {
        "id": uid(), "ce": "F64-UNIT-001", "vendor": "keysight", "ctype": "full",
        "fstart": 3300.0, "fstop": 3800.0,
        "chcount": 64, "chdata": json.dumps(channels_data),
        "mp": round(max(abs(c["power_offset_db"]) for c in channels_data), 3),
        "mph": round(max(abs(c["phase_offset_deg"]) for c in channels_data), 2),
        "md": round(max(abs(c["delay_offset_ns"]) for c in channels_data), 3),
        "pass": True, "ptol": 0.5, "phtol": 5.0, "dtol": 1.0,
        "fw": "F64-FW-v5.2.1",
        "cal_at": NOW, "cal_by": CALIBRATOR, "notes": "Dummy seed for debug bypass",
        "valid": VALID_UNTIL, "st": "valid",
    })
    print(f"   → Inserted 1 record")


def seed_probe_calibration_validity(conn):
    """更新探头校准有效性汇总表"""
    print("[Bonus] Seeding probe calibration validity summary...")
    
    probes = conn.execute(text("SELECT probe_number FROM probes ORDER BY probe_number")).fetchall()

    amp_ids = {r[0]: r[1] for r in conn.execute(text("SELECT probe_id, id FROM probe_amplitude_calibrations")).fetchall()}
    phase_ids = {r[0]: r[1] for r in conn.execute(text("SELECT probe_id, id FROM probe_phase_calibrations")).fetchall()}
    pol_ids = {r[0]: r[1] for r in conn.execute(text("SELECT probe_id, id FROM probe_polarization_calibrations")).fetchall()}
    
    # 先清除再插入 (PostgreSQL 用 ON CONFLICT)
    conn.execute(text("DELETE FROM probe_calibration_validity"))
    
    count = 0
    for (pnum,) in probes:
        conn.execute(text("""
            INSERT INTO probe_calibration_validity
               (probe_id, 
                amplitude_valid, amplitude_valid_until, amplitude_calibration_id,
                phase_valid, phase_valid_until, phase_calibration_id,
                polarization_valid, polarization_valid_until, polarization_calibration_id,
                pattern_valid, link_valid,
                overall_status)
            VALUES (:pid,
                    :av,:avt,:acid,
                    :pv,:pvt,:pcid,
                    :polv,:polvt,:polcid,
                    :patv,:lnkv,
                    :os)
        """), {
            "pid": pnum,
            "av": True, "avt": VALID_UNTIL, "acid": amp_ids.get(pnum),
            "pv": True, "pvt": VALID_UNTIL, "pcid": phase_ids.get(pnum),
            "polv": True, "polvt": VALID_UNTIL, "polcid": pol_ids.get(pnum),
            "patv": False, "lnkv": False,
            "os": "valid",
        })
        count += 1
    print(f"   → Inserted {count} records")


def main():
    print("=" * 60)
    print("  Dummy Calibration Data Seeder (PostgreSQL)")
    print(f"  Target DB: {PG_URL.split('@')[1]}")
    print(f"  Target Chamber: CATR-16-Dual ({CHAMBER_ID})")
    print(f"  Timestamp: {NOW.isoformat()}")
    print("=" * 60)
    
    engine = create_engine(PG_URL)
    
    with engine.begin() as conn:
        seed_probes_inline_calibration(conn)
        seed_amplitude_calibrations(conn)
        seed_phase_calibrations(conn)
        seed_polarization_calibrations(conn)
        seed_path_loss_calibrations(conn)
        seed_rf_chain_calibrations(conn)
        seed_link_calibrations(conn)
        seed_channel_phase_calibrations(conn)
        seed_ce_internal_calibrations(conn)
        seed_probe_calibration_validity(conn)
    
    print("\n✅ All dummy calibration data seeded successfully!")
    print("⚠️  This data is for DEBUG ONLY. Do NOT use in production measurements.")


if __name__ == "__main__":
    main()
