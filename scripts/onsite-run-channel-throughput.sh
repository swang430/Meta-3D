#!/usr/bin/env bash
# 现场首测一键执行: 统一信道资产 (ChannelAsset) → MIMO_OTA 会话 → 4 方位吞吐 + 证据打印
#
# 为什么需要这个脚本 (2026-07-02 pre-departure 走查发现的两个缺口):
#   1. CreateSessionRequest / _request_overrides 没有 channel_asset_id 字段 —— 会话创建
#      API (路径 A) 带不进统一信道资产 (P2-16 S5 backlog);
#   2. 测试管理的计划步骤今天没有执行 runner (POST /test-plans/{id}/start 只转计划状态,
#      步骤停 pending) —— 步骤里配好的 channel_asset_id 无法经计划执行路消费。
# 现阶段唯一全公开 API 的可跑路 = 建会话 → PATCH 会话 TestCase 的
# configuration.channel_asset_id (合并, 不整体覆盖) → run-all。本脚本把三步串成一条命令,
# 2026-07-02 晚已在 mock 模式端到端实证 PASS (engine_mode 覆盖 keysight_gcm + .smu 应用 +
# 4 方位吞吐 + analysis pass)。
#
# 用法:
#   ./scripts/onsite-run-channel-throughput.sh                 # 默认: F64 N78 资产 / 3.6GHz / 4 层
#   ASSET_ID=<uuid> FREQ_HZ=3600000000 LAYERS=4 DURATION_S=10 \
#     ./scripts/onsite-run-channel-throughput.sh
#
# 前置 (现场):
#   - 仪器资源配置页驱动模式已切 Real + 重新加载驱动 (mock 彩排则保持 Mock);
#   - TestCase 频率必须与资产声明一致 (F64 N78 资产 = arfcn 640000 = 3600 MHz),
#     不一致 P2-11 频率一致性网在真硬件下 fail-loud。
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
ASSET_ID="${ASSET_ID:-b328d53a-edfa-40a0-81e1-5efc759bcc5a}"  # F64 N78 场景文件 (vendor_file)
FREQ_HZ="${FREQ_HZ:-3600000000}"
BW_MHZ="${BW_MHZ:-100}"
LAYERS="${LAYERS:-4}"
DURATION_S="${DURATION_S:-10}"
RUN_TIMEOUT_S="${RUN_TIMEOUT_S:-1800}"

say() { printf '\n== %s ==\n' "$1"; }

say "1/5 校验信道资产 $ASSET_ID"
ASSET_JSON=$(curl -sf "$API/channel-assets/$ASSET_ID") || {
  echo "资产不存在或后端不可达 ($API)"; exit 1; }
python3 - "$ASSET_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
print(f"  名称: {a.get('name')}  来源: {a.get('source_type')}")
print(f"  文件: {a.get('associated_file_path')}")
scd = (a.get('payload') or {}).get('scd_config') or {}
if scd.get('arfcn') is not None:
    print(f"  声明频率身份: arfcn={scd['arfcn']} bw={scd.get('bandwidth_mhz')}MHz  <- TestCase 频率须与此一致")
PY

say "2/5 创建 MIMO_OTA 会话 (freq=${FREQ_HZ}Hz bw=${BW_MHZ}M layers=${LAYERS})"
SESSION_ID=$(curl -sf -X POST "$API/commissioning/sessions" -H "Content-Type: application/json" -d "{
  \"frequency_hz\": $FREQ_HZ,
  \"bandwidth_mhz\": $BW_MHZ,
  \"mimo_layers\": $LAYERS,
  \"azimuths_deg\": [0, 90, 180, 270],
  \"measurement_duration_s\": $DURATION_S
}" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "  session_id = $SESSION_ID"

say "3/5 注入 channel_asset_id 到会话 TestCase (合并 configuration, 不覆盖)"
TC_ID=$(curl -sf "$API/test-plans/cases?page_size=5&sort=-created_at" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in (d.get('items') or []):
    if str(c.get('name', '')).startswith('MIMO_OTA Session'):
        print(c['id']); break")
[ -n "$TC_ID" ] || { echo "找不到会话 TestCase"; exit 1; }
curl -sf "$API/test-plans/cases/$TC_ID" | python3 -c "
import sys, json
c = json.load(sys.stdin)
cfg = c.get('configuration') or {}
cfg['channel_asset_id'] = '$ASSET_ID'
json.dump({'configuration': cfg}, sys.stdout)" > /tmp/onsite_patch_$$.json
curl -sf -X PATCH "$API/test-plans/cases/$TC_ID" -H "Content-Type: application/json" \
  -d @/tmp/onsite_patch_$$.json > /dev/null
rm -f /tmp/onsite_patch_$$.json
echo "  test_case_id = $TC_ID  channel_asset_id 已注入"

say "4/5 run-all (预估 ~1min/方位, 超时 ${RUN_TIMEOUT_S}s)"
curl -sf --max-time "$RUN_TIMEOUT_S" -X POST \
  "$API/commissioning/sessions/$SESSION_ID/run-all" > /dev/null

say "5/5 取证"
# 注意: 不能 `curl | python3 - <<PY` —— heredoc 和管道都抢 stdin, json.load 会拿到空。
RESULT_JSON=$(curl -sf "$API/commissioning/sessions/$SESSION_ID")
python3 - "$RESULT_JSON" <<'PY'
import sys, json
d = json.loads(sys.argv[1])
ok = all(v == 'completed' for v in d['phase_statuses'].values())
print('  相位:', d['phase_statuses'])
mt = d.get('mimo_test') or {}
print(f"  engine_mode (measure 实际) = {mt.get('engine_mode')}   <- vendor_file 资产应为 keysight_gcm")
print(f"  emulation_file = {mt.get('emulation_file')}  (source={mt.get('emulation_file_source')})")
for r in mt.get('azimuth_results') or []:
    print(f"    方位 {r['azimuth_deg']:>5}°  吞吐 {r['throughput_mbps']:.1f} Mbps")
an = d.get('analysis') or {}
print(f"  analysis: avg={an.get('avg_throughput_mbps', 0):.1f} Mbps  ratio={an.get('throughput_ratio')}  pass={an.get('throughput_pass')}")
print(f"  报告 id: {d.get('report_id')}")
sys.exit(0 if ok else 2)
PY
