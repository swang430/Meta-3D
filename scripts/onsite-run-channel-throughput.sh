#!/usr/bin/env bash
# 现场首测一键执行: 统一信道资产 (ChannelAsset) → MIMO_OTA 会话 → 4 方位吞吐 + 证据打印
#
# 为什么需要这个脚本 (2026-07-02 pre-departure 走查发现的两个缺口):
#   1. CreateSessionRequest / _request_overrides 没有 channel_asset_id 字段 —— 会话创建
#      API (路径 A) 带不进统一信道资产 (P2-16 S5 backlog);
#   2. 测试管理的计划步骤今天没有执行 runner (POST /test-plans/{id}/start 只转计划状态,
#      步骤停 pending) —— 步骤里配好的 channel_asset_id 无法经计划执行路消费。
# 现阶段唯一全公开 API 的可跑路 = 建会话 → PATCH 会话 TestCase 的
# configuration.channel_asset_id (合并, 不整体覆盖) → run-all。
#
# 用法:
#   ./scripts/onsite-run-channel-throughput.sh                 # 默认: F64 N78 资产 / 3549.99MHz / BW40 / 4 层
#   ASSET_ID=<uuid> FREQ_HZ=3549990000 LAYERS=4 DURATION_S=10 \
#     ./scripts/onsite-run-channel-throughput.sh
#
# 真硬件 (Real) 相关环境变量 (Codex #192 P1: 新会话没有本会话的 attach 记录, P1-9 门会拦):
#   DUT_IMSI=460xxxxxxxxxxxx   # 物理 attach 完成后传入 → 本会话记录 attach-dut (P1-9 门放行的正路)
#   DUT_MODEL="..."            # 可选, 随 attach 记录
#   STRICT_DUT=false           # bring-up 旁路 P1-9 DUT 门 (等价暗室首测页 Lab-smoke 开关)
#   STRICT_CAL=false           # bring-up 旁路 P1-8 校准门
#   TX_POWER_DBM=-46           # DL 功率 (RS EPRE dBm/SCS), 默认 -46 = EMQuest 基线; 不设会
#                              # 落 schema 默认 0.0 → measure 写 DL:POWer 0 冲掉现场基线 (热 46 dB)
#   AZIMUTHS=0,90,180,270      # 方位角列表; 转台断连退化预案 = AZIMUTHS=0,0,0,0 (同方位 4 个
#                              # 测量窗; 注意 AZIMUTHS=0 只测 1 次)
#   BW_MHZ=<M>                 # 显式带宽; 缺省从资产 scd_config.bandwidth_mhz 推导 (保持与
#                              # 资产声明一致), 推导不到 fallback 40
#   UXM_CONFIG_MODE=inherit    # 开关1: UXM 小区参数不下发, 沿用仪器当前态 (如 EMQuest 基线),
#                              # 频率核对改从仪器读回比对 (知情继承); 默认 dispatch=主动下发+对账
#   mock 模式两门自动降级 (strict = flag AND hardware_real), 不需要以上任何变量。
#
# 前置 (现场):
#   - 仪器资源配置页驱动模式已切 Real + 重新加载驱动 (mock 彩排则保持 Mock);
#   - TestCase 频率必须与资产声明一致 (F64 N78 UMa 资产 = arfcn 636666 = 3549.99 MHz,
#     2026-07-03 SMB 实测工程真值; 文件名 3600M 是标称会说谎),
#     不一致 P2-11 频率一致性网在真硬件下 fail-loud。
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
ASSET_ID="${ASSET_ID:-b328d53a-edfa-40a0-81e1-5efc759bcc5a}"  # UMa 3600M 场景文件 (vendor_file, 4x4)
# 2026-07-03 SMB 实测: UMa_3600M 工程真值 = 3549.99 MHz (ARFCN 636666, 恰是 UXM Test App
# 自带默认 —— 厂商配套基线, UXM 免手工改频)。资产 scd 声明已按真值修正 (文件名 3600M 是
# 标称, 会说谎), TestCase 频率必须同真值, 否则 P2-11 频率一致性网 fail-loud。
FREQ_HZ="${FREQ_HZ:-3549990000}"
# 2026-07-20 拍板: 吞吐 BW 跟 EMQuest 基线 40 (UXM 现场态即 BW40, 免改免小区重启;
# 资产 UMa_3600M scd 声明同步改 40)。未显式传时从资产 scd_config.bandwidth_mhz
# 推导 (门审 F2: 一致性网只比 TestCase vs 资产, UXM 下发侧无 BW 比对 — 换 ASSET_ID
# 覆盖跑时靠推导保持与资产声明一致, 不靠人记得同步传 BW_MHZ), 推导不到 fallback 40。
BW_MHZ="${BW_MHZ:-}"
# EMQuest 基线 RS EPRE -46 dBm/SCS; schema 默认 0.0 会冲掉现场基线 (agent 核查 B 项)
TX_POWER_DBM="${TX_POWER_DBM:--46}"
AZIMUTHS="${AZIMUTHS:-0,90,180,270}"
BAND="${BAND:-}"      # 2026-07-03 现场实证: 单载波自动构造 band=None → 驱动 set_cell_config
                      # None.upper() 崩且 ARFCN 不下发; 显式给 band 是零代码修法 (r5 验证)。
                      # 未显式传时从资产 scd_config.band 推导 (Codex #193 P2: 固定 n78 会让
                      # 非 n78 资产覆盖跑时下发错 band); FR1 泛化视同无 band → n78 + 警告。
LAYERS="${LAYERS:-4}"
DURATION_S="${DURATION_S:-10}"
RUN_TIMEOUT_S="${RUN_TIMEOUT_S:-1800}"

say() { printf '\n== %s ==\n' "$1"; }

say "1/6 校验信道资产 $ASSET_ID"
ASSET_JSON=$(curl -sf "$API/channel-assets/$ASSET_ID") || {
  echo "资产不存在或后端不可达 ($API)"; exit 1; }
# 按 source_type 推期望引擎, 最后取证时断言 (P2-16 resolver 映射)
EXPECTED_ENGINE=$(python3 - "$ASSET_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
print(f"  名称: {a.get('name')}  来源: {a.get('source_type')}", file=sys.stderr)
print(f"  文件: {a.get('associated_file_path')}", file=sys.stderr)
scd = (a.get('payload') or {}).get('scd_config') or {}
if scd.get('arfcn') is not None:
    print(f"  声明频率身份: arfcn={scd['arfcn']} bw={scd.get('bandwidth_mhz')}MHz  <- TestCase 频率须与此一致", file=sys.stderr)
print({'vendor_file': 'keysight_gcm', 'standard_3gpp': 'mimo_first_asc',
       'custom_static': 'mimo_first_asc', 'rt_dynamic': 'b2_parametric_tdl'
       }.get(a.get('source_type'), 'unknown'))
PY
)
echo "  期望 measure 引擎: $EXPECTED_ENGINE"

# BW 未显式传 → 从资产 scd_config.bandwidth_mhz 推导 (门审 F2, 与 BAND 推导同构)
if [ -z "$BW_MHZ" ]; then
  BW_MHZ=$(python3 - "$ASSET_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
bw = ((a.get('payload') or {}).get('scd_config') or {}).get('bandwidth_mhz')
print(int(bw) if bw else '')
PY
)
  if [ -n "$BW_MHZ" ]; then
    echo "  BW 从资产推导: ${BW_MHZ}M"
  else
    BW_MHZ=40
    echo "  ⚠ 资产无 scd bandwidth_mhz, fallback 40 — 请确认与 UXM/资产一致"
  fi
fi

# BAND 未显式传 → 从资产 scd_config.band 推导 (Codex #193 P2); FR1 泛化不是合法 NR band
# 名 (722/836.5/1575.42/2450 等无准确 DL band 的登记值), 视同无 band。
if [ -z "$BAND" ]; then
  BAND=$(python3 - "$ASSET_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
b = str(((a.get('payload') or {}).get('scd_config') or {}).get('band') or '')
print(b if b and b.upper() != 'FR1' else '')
PY
)
  if [ -n "$BAND" ]; then
    echo "  band 从资产推导: $BAND"
  else
    BAND=n78
    echo "  ⚠ 资产无可用 band (缺失或 FR1 泛化), fallback n78 — 非 n78 资产请显式传 BAND=<nXX>"
  fi
fi

say "2/6 快照现有 TestCase id 集 (用于精确绑定新会话的 case, Codex #192 P2)"
BEFORE_IDS=$(curl -sf "$API/test-plans/cases?page_size=20&sort=-created_at" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(','.join(c['id'] for c in (d.get('items') or [])))")

say "3/6 创建 MIMO_OTA 会话 (freq=${FREQ_HZ}Hz bw=${BW_MHZ}M layers=${LAYERS} az=[${AZIMUTHS}])"
EXTRA_FLAGS=""
[ "${STRICT_DUT:-}" = "false" ] && EXTRA_FLAGS+=', "precheck_strict_dut": false' && echo "  ⚠ bring-up 旁路: managed MEASURE DUT 动态门关闭"
[ "${STRICT_CAL:-}" = "false" ] && EXTRA_FLAGS+=', "precheck_strict_cal": false' && echo "  ⚠ bring-up 旁路: precheck_strict_cal=false"
SESSION_ID=$(curl -sf -X POST "$API/commissioning/sessions" -H "Content-Type: application/json" -d "{
  \"frequency_hz\": $FREQ_HZ,
  \"bandwidth_mhz\": $BW_MHZ,
  \"mimo_layers\": $LAYERS,
  \"azimuths_deg\": [$AZIMUTHS],
  \"measurement_duration_s\": $DURATION_S$EXTRA_FLAGS
}" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "  session_id = $SESSION_ID"

say "4/6 绑定并注入 channel_asset_id (合并 configuration, 不覆盖)"
# 差集定位本会话新建的 TestCase: 恰好 1 个才继续, 0/多个都 fail-loud (并发窗口内有别人
# 建会话时, 全局最新一条可能属于别的会话 —— Codex #192 P2)。
TC_ID=$(curl -sf "$API/test-plans/cases?page_size=20&sort=-created_at" | python3 -c "
import sys, json
before = set('$BEFORE_IDS'.split(','))
d = json.load(sys.stdin)
new = [c for c in (d.get('items') or [])
       if c['id'] not in before and str(c.get('name', '')).startswith('MIMO_OTA Session')]
if len(new) != 1:
    print(f'预期恰好 1 个新建会话 TestCase, 实际 {len(new)} 个 — 疑并发创建, 请在无并发时重跑', file=sys.stderr)
    sys.exit(3)
print(new[0]['id'])")
curl -sf "$API/test-plans/cases/$TC_ID" | python3 -c "
import sys, json
c = json.load(sys.stdin)
cfg = c.get('configuration') or {}
cfg['channel_asset_id'] = '$ASSET_ID'
# band 显式进单载波 (否则 pcell.band=None → UXM set_cell_config None.upper() 崩, ARFCN 不下发)
cfg['component_carriers'] = [{'frequency_hz': float('$FREQ_HZ'), 'bandwidth_mhz': float('$BW_MHZ'),
                              'band': '$BAND', 'role': 'pcell'}]
# DL 功率 (RS EPRE): 不注入会落 schema 默认 0.0 → measure 无条件写 DL:POWer 0 冲掉
# EMQuest -46 基线 (热 46 dB, F64 输入 clipping 风险) — 2026-07-20 agent 核查 B 项
cfg['target_tx_power_dbm'] = float('$TX_POWER_DBM')
# 开关1: UXM 配置来源 (dispatch=下发+对账 / inherit=沿用仪器态+读回核对)
mode = '${UXM_CONFIG_MODE:-}'.strip()
if mode:
    if mode not in ('dispatch', 'inherit'):
        print(f'非法 UXM_CONFIG_MODE={mode!r} (合法 dispatch/inherit)', file=sys.stderr)
        sys.exit(5)
    cfg['uxm_config_mode'] = mode
json.dump({'configuration': cfg}, sys.stdout)" > /tmp/onsite_patch_$$.json
curl -sf -X PATCH "$API/test-plans/cases/$TC_ID" -H "Content-Type: application/json" \
  -d @/tmp/onsite_patch_$$.json > /dev/null
rm -f /tmp/onsite_patch_$$.json
echo "  test_case_id = $TC_ID  channel_asset_id 已注入"

# DUT_IMSI 是可选的执行追溯元数据；managed 流程不拿它证明连接成功。正式 DUT 门在
# MEASURE 按本次 TestCase 初始化 RF 链并受控 attach 后读取 UXM live CONN 状态。
if [ -n "${DUT_IMSI:-}" ]; then
  say "4b/6 记录 DUT attach (imsi=${DUT_IMSI})"
  ATTACH_JSON=$(curl -sf -X POST "$API/test-executions/$SESSION_ID/attach-dut" \
    -H "Content-Type: application/json" \
    -d "{\"imsi\": \"$DUT_IMSI\", \"dut_model\": \"${DUT_MODEL:-}\"}")
  python3 - "$ATTACH_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
print(f"  attach 记录: success={a.get('success')} rrc_connected={a.get('rrc_connected')}")
for w in a.get('warnings') or []:
    print(f"  ⚠ {w}")
PY
elif [ "${STRICT_DUT:-}" != "false" ]; then
  echo "  ℹ 未传 DUT_IMSI：允许继续；Real 模式将在 MEASURE 初始化后用 UXM live CONN 严格确认 attach。"
  echo "    DUT_IMSI 仅用于追溯；bring-up 如需跳过真实连接门，显式设置 STRICT_DUT=false。"
fi

say "5/6 run-all (预估 ~1min/方位, 超时 ${RUN_TIMEOUT_S}s)"
curl -sf --max-time "$RUN_TIMEOUT_S" -X POST \
  "$API/commissioning/sessions/$SESSION_ID/run-all" > /dev/null

say "6/6 取证"
# 注意: 不能 `curl | python3 - <<PY` —— heredoc 和管道都抢 stdin, json.load 会拿到空。
RESULT_JSON=$(curl -sf "$API/commissioning/sessions/$SESSION_ID")
python3 - "$RESULT_JSON" "$EXPECTED_ENGINE" <<'PY'
import sys, json
d = json.loads(sys.argv[1])
expected_engine = sys.argv[2]
ok = all(v == 'completed' for v in d['phase_statuses'].values())
print('  相位:', d['phase_statuses'])
mt = d.get('mimo_test') or {}
engine = mt.get('engine_mode')
print(f"  engine_mode (measure 实际) = {engine}   <- 期望 {expected_engine}")
print(f"  emulation_file = {mt.get('emulation_file')}  (source={mt.get('emulation_file_source')})")
for r in mt.get('azimuth_results') or []:
    print(f"    方位 {r['azimuth_deg']:>5}°  吞吐 {r['throughput_mbps']:.1f} Mbps")
an = d.get('analysis') or {}
print(f"  analysis: avg={an.get('avg_throughput_mbps', 0):.1f} Mbps  ratio={an.get('throughput_ratio')}  pass={an.get('throughput_pass')}")
print(f"  报告 id: {d.get('report_id')}")
if expected_engine != 'unknown' and engine != expected_engine:
    print(f"  ✗ 引擎不符: 资产未被 measure 消费 (疑注入没生效)", file=sys.stderr)
    sys.exit(4)
sys.exit(0 if ok else 2)
PY
