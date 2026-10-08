"""P2-93：仅呈现已校验执行审计，不产生参数或硬件确认真值。"""
_SOURCE_LABELS = {'saved_configuration': '已保存配置',
                  'launch_default': '本次启动默认值', 'not_configured': '未配置',
                  'derived': '由本次输入派生',
                  'untraceable': '来源不可追溯'}

_LABELS = {
    'azimuths_deg': '测试方位', 'settling_time_s': '转台稳定等待',
    'num_samples_per_azimuth': '每方位请求窗口数', 'target_tx_power_dbm': '基站下行功率请求',
    'uxm_dl_power_dbm_per_bw': 'UXM 整带宽功率请求', 'f64_crest_db': 'F64 峰均比请求',
    'f64_output_level_dbm': 'F64 输出电平请求', 'f64_output_gain_db': 'F64 输出增益请求',
    'f64_input_ref_dbm': 'F64 输入参考请求', 'input_loop_initial_dl_power_dbm': '输入闭环初始下行功率',
    'target_rsrp_dbm': '目标 RSRP', 'target_snr_db': '目标 SNR',
    'f64_bypass_mode': 'F64 旁路模式', 'f64_fade_after_attach': '连接后开启衰落',
    'base_station_config_mode': '基站配置方式', 'mimo_port_preset': 'MIMO 端口预设',
    'attach_power_observation_s': '连接前人工功率观察时长', 'channel_asset_id': '信道资产引用',
    'emulation_file': '仿真文件请求', 'asc_source_path': 'ASC 来源路径', 'scd_id': '历史信道引用',
    'switch_mode_id': '射频开关模式', 'engine_mode': '请求信道引擎', 'cdl_model_name': '请求信道模型',
    'dut_profile_id': 'DUT 配置引用', 'measurement_duration_s': '旧测量时长字段',
    'sample_interval_ms': '旧采样间隔字段', 'theoretical_peak_throughput_mbps': '旧理论吞吐字段',
    'reference_antenna_model': '参考天线型号', 'reference_antenna_gain_dbi': '参考天线增益',
    'mimo_layers': 'MIMO 层数', 'modulation': '调制请求', 'frequency_hz': '中心频率',
    'bandwidth_mhz': '带宽', 'subcarrier_spacing_khz': '子载波间隔', 'band': '频段',
    'duplex': '双工模式', 'lte_dl_earfcn': 'LTE 下行 EARFCN', 'nr_arfcn': 'NR ARFCN',
    'role': '载波角色', 'carrier_id': '载波标识', 'radio_technology': '无线制式',
    'lte_transmission_mode': 'LTE 传输模式', 'transmission_mode': 'LTE 传输模式',
    'mcs': 'MCS 索引', 'rat': 'MAC 制式', 'kind': 'MAC 配置类型',
    'enable_amc': '自适应调制编码', 'tdd_period': 'TDD 周期', 'tdd_pattern': 'TDD 帧模式',
    'test_intent': '测试意图', 'csi_rs_ports': 'CSI-RS 端口数', 'rb_allocation': '资源块分配',
    'resource_allocation': '资源分配', 'harq_max_trans': 'HARQ 最大传输次数',
    'harq_processes': 'HARQ 进程数', 'schema_version': '数据结构版本',
    'profile_version': 'MAC 配置版本', 'source_reference': '参数域出处',
    'unit': '统计基数单位', 'count': '统计基数计数', 'metric_requirements': '必需测量指标',
    'scheduler_algorithm': '调度算法', 'profile_digest': '冻结 MAC 摘要',
    'uldl_configuration': 'LTE TDD 上下行配置', 'special_subframe': 'LTE TDD 特殊子帧',
    'rmc_version': 'LTE RMC 版本', 'min_sinr_db': '最小 SINR', 'rsrp_range_dbm': 'RSRP 判定范围',
    'min_throughput_mbps': '操作员吞吐通过阈值', 'max_rsrp_variance_db': '最大 RSRP 方差请求',
    'min_throughput_ratio': '旧吞吐比率字段', 'min_avg_rank_indicator': '最小平均秩指示',
    'max_quiet_zone_ripple_db': '最大静区波动请求',
    'key': '指标', 'scope': '范围',
}
_POWER = {k for k in _LABELS if k.endswith(('_dbm', '_db', '_dbm_per_bw')) and not k.startswith(('min_', 'max_', 'reference_'))}
_RECEIPTS = {'target_tx_power_dbm': 'config.downlink_power_dbm',
             'uxm_dl_power_dbm_per_bw': 'config.downlink_power_dbm_per_bandwidth',
             'mimo_port_preset': 'config.port_preset', 'mimo_layers': 'config.mimo_layers'}
_MAC_RECEIPTS = {'statistical_window.count': 'stat_count', 'subcarrier_spacing_khz': 'scs_khz'}


def parameter_display_value(value):
    if value is None:
        return '未配置'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return '、'.join(parameter_display_value(v) for v in value)
    if isinstance(value, dict):
        return '；'.join(f'{_LABELS.get(k, k)}={parameter_display_value(v)}' for k, v in value.items())
    return str(value)


def report_parameter_groups(audit: dict) -> list[dict]:
    if audit.get('status') != 'frozen_request':
        return []
    groups = {}
    for path, item in audit.get('parameters', {}).items():
        leaf = path.rsplit('.', 1)[-1]
        if path.startswith('component_carriers.'):
            title = '载波配置'
            label = f"载波 {int(path.split('.')[1]) + 1} · {_LABELS.get(leaf, leaf)}"
        elif path.startswith('pass_criteria.'):
            title, label = '判据请求', _LABELS.get(leaf, leaf)
        elif 'statistical_window.' in path or path == 'num_samples_per_azimuth':
            title, label = '测量窗口', _LABELS.get(leaf, leaf)
        elif path.startswith('mac_profile.'):
            title, label = 'MAC 配置', _LABELS.get(leaf, leaf)
        elif path in _POWER:
            title, label = '功率请求', _LABELS.get(leaf, leaf)
        elif path in ('azimuths_deg', 'settling_time_s'):
            title, label = '方位与移动', _LABELS[leaf]
        elif path in ('channel_asset_id', 'emulation_file', 'asc_source_path', 'scd_id', 'engine_mode', 'cdl_model_name', 'f64_bypass_mode', 'f64_fade_after_attach'):
            title, label = '信道请求', _LABELS[leaf]
        else:
            title, label = '其他与历史兼容', _LABELS.get(leaf, path)
        unit = ('dBm' if leaf.endswith(('_dbm', '_dbm_per_bw')) else
                'dB' if leaf.endswith('_db') else 'Hz' if leaf.endswith('_hz') else
                'MHz' if leaf.endswith('_mhz') else 'kHz' if leaf.endswith('_khz') else
                'ms' if leaf.endswith('_ms') else 's' if leaf.endswith('_s') else
                '°' if leaf.endswith('_deg') else 'dBi' if leaf.endswith('_dbi') else
                'Mbps' if leaf.endswith('_mbps') else '')
        requested = item['requested']
        receipt_key = _RECEIPTS.get(path)
        # 以 BaseStationRequestedConfig.receipt_payload 的控制项为准；
        # RAT/channel_kind/frequency_mhz 描述项与 SCell 不借用 PCell 回执。
        if path.startswith('component_carriers.0.') and leaf in (
            'bandwidth_mhz', 'duplex', 'lte_transmission_mode', 'subcarrier_spacing_khz',
            'band', 'lte_dl_earfcn', 'nr_arfcn'
        ):
            receipt_key = 'config.' + leaf
        if path.startswith('mac_profile.profile.'):
            field = path.removeprefix('mac_profile.profile.')
            receipt_key = 'mac.' + _MAC_RECEIPTS.get(field, field)
            # scheduler 审计回执键属于 config 请求契约；其余 MAC 字段仍读 MAC
            # 应用阶段，不借较早 config 的同名字段冒充后续 MAC 确认。
            if field == 'scheduler_algorithm':
                receipt_key = 'config.scheduler_algorithm'
        receipt = audit.get('application_fields', {}).get(receipt_key, {})
        confirmed = (receipt.get('status') == 'confirmed' and receipt.get('simulated') is False
                     and receipt.get('requested') == requested and receipt.get('applied') is not None)
        note = '同次逐字段回执确认' if confirmed else '无匹配的同次确认回执'
        if receipt and not confirmed:
            note = '已有回执但未获确认：' + (receipt.get('reason') or '未记录具体原因')
            if receipt.get('simulated') is not False:
                note += '；模拟或来源未确认'
            if receipt.get('requested') != requested:
                note += '；回执请求与冻结值不一致'
            if receipt.get('applied') is None:
                note += '；未记录确认值'
        if path in ('measurement_duration_s', 'sample_interval_ms'):
            note = '历史兼容字段，不控制本次测量'
        elif path in ('theoretical_peak_throughput_mbps', 'pass_criteria.min_throughput_ratio'):
            note = '当前判据已弃用；不参与当前正式判定，不重写历史结论'
        if path.endswith('statistical_window.count'):
            unit = audit.get('parameters', {}).get('mac_profile.profile.statistical_window.unit', {}).get('requested') or '冻结单位未记录'
            note += '；统计基数不能直接换算成墙钟时长'
        values = [requested[i:i + 16] for i in range(0, len(requested), 16)] if isinstance(requested, list) and len(requested) > 16 else [requested]
        for index, value in enumerate(values):
            groups.setdefault(title, []).append({'path': path, 'label': label + (f'（段 {index + 1}）' if len(values) > 1 else ''),
                'unit': unit, 'requested': parameter_display_value(value),
                'source': _SOURCE_LABELS.get(item.get('source'), '来源不可追溯'),
                'applied': parameter_display_value(receipt['applied']) if confirmed else '未确认', 'note': note})
    order = ('载波配置', 'MAC 配置', '功率请求', '测量窗口', '方位与移动', '信道请求', '判据请求', '其他与历史兼容')
    return [{'title': title, 'rows': groups[title]} for title in order if title in groups]
