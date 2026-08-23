"""P2-21 门: ① P1-12 三个可信化标志渲染可达 (parameters 下 + 渲染器实际产出含
未验证标注) ② pdf_certificate CJK 三族收敛 + 证书 PDF 字节含 CID 字体。

行为门打在**真实生效端**: 不是断言 step dict 形态就完 (那只是不变量门), 而是把
content_data 喂给 PDFGenerator 的步骤区渲染器, 断言产出的 Paragraph 流里真出现
"未验证" 标注 —— P1-12 的意图是操作员在 PDF 里**看得见**兜底提示, 顶层键时代
形态再对也看不见, 这正是本片要修的病。
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.mimo_ota.rf_kpi_trust import build_rf_kpi_trust
from app.services.pdf_generator import CJK_FONT, PDFGenerator
from app.services.pdf_certificate import PDFCertificateGenerator


def _exec(phases, validation_pass=None, status="completed"):
    return SimpleNamespace(
        measurements={"phases": phases},
        status=status,
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
        validation_pass=validation_pass,
    )


def _content(phases, **kw):
    return _build_mimo_ota_content_data(_exec(phases, **kw), datetime(2026, 1, 1))


# 全兜底执行: 静区 fallback / mock TRP / 无路损证书 — P1-12 最该叫的场景。
_FALLBACK_PHASES = {
    "precheck": {"overall_pass": True, "messages": ["静区用了默认波纹"],
                 "quiet_zone_ripple_db": 1.0,
                 "quiet_zone_ripple_source": "fallback_default"},
    "reference": {"measured_trp_dbm": -30.0, "compensation_factor_db": 1.5,
                  "measurement_source": "mock"},
    "measure": {"frequency_ghz": 3.55, "mimo_config": "4x4",
                "path_loss_certificate_id": None, "path_loss_verified": False,
                "path_loss_application": {
                    "schema_version": 1,
                    "status": "not_applied",
                    "provenance": "missing",
                    "reason": "missing",
                    "gate_mode": "operator_bypass",
                    "certificate_id": None,
                    "value_disclosure": "none",
                }},
    "analysis": {"verdict": "PASS"},
}

# 全实测执行: 三标志显式 True。
_VERIFIED_PHASES = {
    "precheck": {"overall_pass": True, "messages": [],
                 "quiet_zone_ripple_db": 0.5, "quiet_zone_verified": True},
    "reference": {"measured_trp_dbm": -28.0, "trp_verified": True,
                  "measurement_source": "hal_signal_analyzer"},
    "measure": {
        "frequency_ghz": 3.55,
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "verified-path-loss-cert",
            "value_disclosure": "verified",
        },
        "throughput_verified": True,
        "throughput_scope": "pcell",
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "rsrp_dbm": -80.0,
            "rsrp_valid": True,
            "sinr_db": 20.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
            "rank_indicator_valid": True,
            "throughput_mbps": 1.0,
            "throughput_valid": True,
            "throughput_scope": "pcell",
        }],
    },
    "analysis": {"verdict": "PASS"},
}
_VERIFIED_PHASES["measure"]["rf_kpi_trust"] = build_rf_kpi_trust(
    requested_azimuths=[0.0],
    azimuth_results=_VERIFIED_PHASES["measure"]["azimuth_results"],
    source="explicit_real",
)
_VERIFIED_PHASES["measure"]["formal_rf_kpi_verified"] = True


def _step(content, phase):
    return next(s for s in content["step_results"] if s["phase"] == phase)


def _para_text(p):
    """Paragraph 的**解析产物** (frags), 不是 .text —— .text 是输入回显 (标称端),
    被 paraparser 当 tag 吞掉的内容它照样显示, 拿它断言等于没验 (本文件曾在
    这上面假绿过一次: <prototype…<MPAC> 被整段当 tag 吞, .text 仍含 MPAC)。"""
    frags = getattr(p, "frags", None)
    if frags is not None:
        return "".join(f.text for f in frags)
    return getattr(p, "text", "")


def _rendered_text(content):
    """渲染器真实产出 (生效端): 步骤区 elements 的 Paragraph 解析文本 + Table
    单元格里嵌的 Paragraph (parameters 键值表渲染成 Table, 只收顶层会漏正文)。"""
    gen = PDFGenerator()
    elements = gen._generate_step_details_section(content)
    parts = []
    for e in elements:
        parts.append(_para_text(e))
        for row in (getattr(e, "_cellvalues", None) or []):
            for cell in row:
                items = cell if isinstance(cell, (list, tuple)) else [cell]
                parts.extend(_para_text(i) for i in items)
    return " ".join(parts)


class TestTrustFlagsReachable:
    def test_flags_live_under_parameters(self):
        """不变量: 三标志在 parameters 下 (渲染器唯一可达位置), 顶层渲染键删净。
        变异 (任一标志挪回顶层) → 红。"""
        c = _content(_FALLBACK_PHASES)
        for phase, key in (("precheck", "静区验证"), ("reference", "TRP 验证"),
                           ("measure", "路损验证")):
            step = _step(c, phase)
            assert key in step["parameters"], (phase, step)
            # 顶层不留死载荷双写 (P1-22 删死键先例)
            assert not any(k.endswith("_verified") for k in step), step

    def test_fallback_run_renders_unverified_labels(self):
        """行为门: 全兜底执行 → 渲染器产出里三条"未验证"标注全部可见。
        变异 (标志挪回顶层 / 删标注 helper) → 红。"""
        text = _rendered_text(_content(_FALLBACK_PHASES))
        assert "未验证 (兜底默认值, 非实测静区)" in text
        assert "未验证 (mock/兜底值)" in text
        assert "未验证 (未找到匹配的路损证书；本次结果未补偿。)" in text

    def test_verified_run_renders_verified_labels(self):
        """对向: 全实测执行 → 三条"已验证", 不出现"未验证" (别把好数据也叫脏)。"""
        text = _rendered_text(_content(_VERIFIED_PHASES))
        assert "已验证 (探头方向图实测)" in text
        assert "已验证 (真实信号分析仪)" in text
        assert "已验证 (真实来源路损校准证书)" in text
        assert "未验证" not in text

    def test_free_text_with_angle_bracket_survives_rendering(self):
        """内审 F1: `<字母` 形态的自由文本 (操作员命名 "TDL-A <30ns" / 掉线消息)
        会被 paraparser 当未闭合 tag — 不转义则**整份报告 PDF 生成失败**;
        完整 `<tag>` 形态更阴险: build 成功但内容被静默吞掉。
        变异 (删 _cell 的 escape) → 本测试红 (渲染抛 ValueError 或内容丢失)。"""
        phases = {**_FALLBACK_PHASES,
                  "precheck": {**_FALLBACK_PHASES["precheck"],
                               "messages": ["DUT <prototype 掉线", "标签 <MPAC> 完整形态"]},
                  "measure": {**_FALLBACK_PHASES["measure"],
                              "cdl_model_name": "TDL-A <30ns"}}
        text = _rendered_text(_content(phases))  # 不转义时这里直接抛
        assert "TDL-A <30ns" in text                      # 内容没被吞/没双重转义
        assert "标签 <MPAC> 完整形态" in text             # tag 形态也保下来了
        assert "DUT <prototype 掉线" in text

    def test_none_values_render_as_dash_not_english_none(self):
        """内审 F3: 缺值/显式 null → "—", 不是英文字面 "None" (中文报告里
        含义模糊)。messages 显式 null 也要兜 (.get 默认只兜键缺失)。"""
        phases = {**_FALLBACK_PHASES,
                  "precheck": {**_FALLBACK_PHASES["precheck"],
                               "quiet_zone_ripple_db": None, "messages": None}}
        text = _rendered_text(_content(phases))
        assert "None" not in text
        assert "—" in text

    def test_unknown_legacy_flag_is_loud_not_silent(self):
        """三值第三态: 历史数据判不了 (trp None 且来源非 mock) → 显式"未知",
        不沉默 —— 沉默正是 P2-21 要修的病。"""
        phases = {**_FALLBACK_PHASES,
                  "reference": {"measured_trp_dbm": -30.0,
                                "measurement_source": "hal_signal_analyzer"}}
        text = _rendered_text(_content(phases))
        assert "未知 (历史数据未区分真实/兜底)" in text


class TestSharedPdfFreeTextEscaping:
    def test_cover_title_with_angle_bracket_survives_rendering(self):
        """P3-18: TestCase 名进入封面标题后仍必须作为文本，而不是 XML tag。"""
        gen = PDFGenerator()
        elements = gen._generate_cover_page(
            {
                "title": "MIMO OTA — DUT <prototype",
                "report_type": "single_execution",
            },
            {},
        )
        rendered = " ".join(_para_text(item) for item in elements)
        assert "DUT <prototype" in rendered

    def test_test_case_template_autoescapes_substitutions_but_keeps_markup(self):
        """Jinja 只转义数据替换值；模板自带的 ``<b>`` 仍由 ReportLab 解析。"""
        gen = PDFGenerator()
        elements = gen._generate_text_section(
            {"content_template": gen._get_test_case_template()},
            {
                "test_plan": {
                    "name": "DUT <prototype",
                    "description": "描述 <MPAC>",
                    "status": "completed",
                    "created_by": "gui",
                }
            },
        )
        rendered = " ".join(_para_text(item) for item in elements)
        assert "Test Case: DUT <prototype" in rendered
        assert "Description: 描述 <MPAC>" in rendered

    def test_vrt_step_parameter_free_text_survives_shared_renderer(self):
        """VRT step_configs 绕过 MIMO report builder，必须在共享渲染器入口转义。"""
        text = _rendered_text(
            {
                "step_configs": [
                    {
                        "name": "车辆 <prototype",
                        "parameters": {
                            "场景 <name>": "TDL-A <30ns",
                            "标签": "<MPAC>",
                        },
                    }
                ]
            }
        )
        assert "车辆 <prototype" in text
        assert "场景 <name>" in text
        assert "TDL-A <30ns" in text
        assert "<MPAC>" in text


class TestCertificateCJK:
    def _cert(self):
        return SimpleNamespace(
            certificate_number="CAL-2026-001",
            system_name="MPAC 暗室系统", system_serial_number="SN-1",
            system_configuration={"探头数": 32},
            lab_name="测试实验室", lab_address="上海",
            lab_accreditation="CNAS", lab_accreditation_body="CNAS",
            calibration_date=datetime(2026, 8, 1),
            valid_until=datetime(2026, 8, 31), issued_at=datetime(2026, 8, 1),
            trp_error_db=0.3, trp_pass=True, tis_error_db=0.4, tis_pass=True,
            repeatability_std_dev_db=0.1, repeatability_pass=True,
            overall_pass=True, standards=["CTIA OTA v3.9"],
            calibrated_by="张三", reviewed_by="李四",
            digital_signature="abc123",
        )

    def test_all_styles_converged_to_cjk(self):
        """不变量: 自定义样式 + sample stylesheet 全族 == CJK_FONT。
        变异 (删遍历 / 漏改任一族) → 红。"""
        gen = PDFCertificateGenerator(output_dir="/tmp")
        wrong = {n: st.fontName for n, st in gen.styles.byName.items()
                 if hasattr(st, "fontName") and st.fontName != CJK_FONT}
        assert wrong == {}, wrong
        for st in (gen.title_style, gen.heading_style, gen.body_style):
            assert st.fontName == CJK_FONT, st.name

    def test_no_helvetica_literal_left_in_module(self):
        """存在性粗筛 (行为门在下一条): 模块源码零 Helvetica 字面量 —— 新加
        样式点忘了用 CJK_FONT 会在这红。"""
        import inspect
        import app.services.pdf_certificate as mod
        assert "Helvetica" not in inspect.getsource(mod)

    def test_generated_certificate_embeds_cid_font(self, tmp_path):
        """行为门: 真生成一份含中文字段的证书 PDF, 字节里有 CID 字体引用
        (STSong) —— 豆腐块时代这里是 Helvetica。"""
        gen = PDFCertificateGenerator(output_dir=str(tmp_path))
        path = gen.generate_certificate(self._cert())
        pdf = open(path, "rb").read()
        # 内审 F2: 不查 "无 Helvetica 残留" — reportlab 任何 PDF 都自带 F1
        # /Helvetica 默认字体对象, 那个断言要么恒真要么恒假, 什么都不防。
        # STSong 出现在字节里 = CJK 字体真被引用, 这一条就是行为门。
        assert b"STSong" in pdf
