
import requests
import time
import sys
import os
import json
import logging

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
RUN_ID = f"sim-{int(time.time())}"

logging.basicConfig(level=logging.INFO, format='[SIM] %(message)s')
logger = logging.getLogger("SimVRT")

def run_simulation():
    try:
        # 0. Get Valid Scenario
        logger.info("0. Fetching Scenarios...")
        sc_resp = requests.get(f"{BASE_URL}/road-test/scenarios")
        scenarios = sc_resp.json()
        if not scenarios:
             logger.error("No scenarios found!")
             return False
        
        # Use first available scenario
        sc_id = list(scenarios.keys())[0] if isinstance(scenarios, dict) else scenarios[0]['id']
        logger.info(f"   Using Scenario ID: {sc_id}")

        # 1. Create Execution
        logger.info("1. Creating Execution...")
        resp = requests.post(f"{BASE_URL}/road-test/executions", json={
            "scenario_id": sc_id,
            "mode": "ota",
            "notes": "Simulation Run"
        })
        if resp.status_code not in [200, 201]:
            logger.error(f"Failed to create execution (Status {resp.status_code}): {resp.text}")
            return False
            
        execution = resp.json()
        exec_id = execution['execution_id']
        logger.info(f"   Execution Created: {exec_id}")

        # 2. Start Execution
        logger.info("2. Starting Execution...")
        requests.post(f"{BASE_URL}/road-test/executions/{exec_id}/control", json={"action": "start"})

        # 3. Submit Metrics (Simulate 5 seconds of data)
        logger.info("3. Submitting Metrics...")
        accumulated_series = []
        for i in range(5):
            point = {
                "time_s": i,
                "rsrp_dbm": -80 + i,
                "rsrq_db": -10,
                "sinr_db": 20,
                "dl_throughput_mbps": 100 + i*10,
                "ul_throughput_mbps": 50,
                "latency_ms": 10,
                "position": {"x": i*10, "y": i*10, "z": 0},
                "event": None
            }
            accumulated_series.append(point)

            metrics_payload = {
                "execution_id": exec_id,
                "time_series": accumulated_series,
                "phases": [],
                "events": [],
                "kpi_summary": []
            }
            m_resp = requests.post(f"{BASE_URL}/road-test/executions/{exec_id}/metrics", json=metrics_payload)
            if m_resp.status_code != 200:
                logger.error(f"   Metrics Submission FAILED: {m_resp.status_code} {m_resp.text}")
            else:
                logger.info(f"   Metrics Submitted (200 OK)")
            time.sleep(0.5)

        # 4. Stop Execution (Triggers Report Generation)
        logger.info("4. Stopping Execution (triggering archive)...")
        stop_resp = requests.post(f"{BASE_URL}/road-test/executions/{exec_id}/control", json={"action": "stop"})
        logger.info(f"   Stop Response: {stop_resp.status_code}")

        # 5. Verify Report
        logger.info("5. Verifying Report...")
        # Give it a second to generate
        time.sleep(2)
        
        # Check specific file path (assuming default location)
        # We need to find the report ID first.
        # But we can check the debug_report_dump.txt file too!
        if os.path.exists("debug_report_dump.txt"):
            size = os.path.getsize("debug_report_dump.txt")
            logger.info(f"   debug_report_dump.txt size: {size} bytes")
            if size > 0:
                logger.info("   SUCCESS: Debug dump was written!")
            else:
                logger.error("   FAILURE: Debug dump is empty!")
        else:
            logger.error("   FAILURE: Debug dump file missing!")

        return True

    except Exception as e:
        logger.exception("Simulation Failed")
        return False

if __name__ == "__main__":
    if run_simulation():
        sys.exit(0)
    else:
        sys.exit(1)
