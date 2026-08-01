"""P3-14 契约收尾门: ① 列表 summary 频率/带宽从 configuration 换源 (行级派生列
是保存链不回写的 stale 源) ② template_category 超长 422 (列 String(100), 此前
超长打到 PG 直接 500) ③ CreateSessionRequest.channel_asset_id 透传 overrides
(此前统一信道资产进不了会话创建, 只能建完再 PATCH 绕道)。

G9 (门 G-A, schema 描述 ⊇ 枚举) 在 test_rule_gates.py。
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.api.commissioning import CreateSessionRequest, _request_overrides
from app.schemas.test_plan import TestCaseCreate, TestCaseResponse, TestCaseSummary


def _row(**kw):
    base = dict(
        id=uuid4(), name="tc", description=None, test_type="MIMO_OTA",
        template_category=None, channel_model=None,
        frequency_mhz=3500.0, bandwidth_mhz=100.0, test_duration_sec=None,
        is_template=False, pass_criteria=None, tags=None,
        created_by="t", created_at=datetime(2026, 1, 1),
        configuration={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestSummaryFrequencySource:
    def test_configuration_wins_over_stale_row_column(self):
        """行列 3500 (旧) vs configuration 3549.99 MHz (真) → 显示 3549.99。
        变异 (删 from_case_row 的 configuration 派生) → 红。
        这正是现场踩过的形态: GUI 改频只 PATCH configuration, 卡片显示旧频率。"""
        row = _row(configuration={"frequency_hz": 3_549_990_000, "bandwidth_mhz": 40})
        s = TestCaseSummary.from_case_row(row)
        assert s.frequency_mhz == 3549.99
        assert s.bandwidth_mhz == 40.0

    def test_row_column_is_fallback_when_config_lacks_frequency(self):
        """VRT / 旧用例 configuration 里没有 frequency_hz → 行列兜底, 不清零。"""
        row = _row(configuration={"channel_snapshots": []})
        s = TestCaseSummary.from_case_row(row)
        assert s.frequency_mhz == 3500.0
        assert s.bandwidth_mhz == 100.0

    def test_malformed_config_values_do_not_poison(self):
        """值形态卫兵: bool/负数/字符串形态不接管显示 — 频率与带宽两个键都验
        (内审 F3: 只循环频率的话, bandwidth 卫兵的变异可存活)。"""
        for bad in (True, -1, 0, "3549990000", None):
            row = _row(configuration={"frequency_hz": bad, "bandwidth_mhz": bad})
            s = TestCaseSummary.from_case_row(row)
            assert s.frequency_mhz == 3500.0, bad
            assert s.bandwidth_mhz == 100.0, bad

    def test_non_dict_configuration_safe(self):
        row = _row(configuration=None)
        s = TestCaseSummary.from_case_row(row)
        assert s.frequency_mhz == 3500.0


class TestDetailResponseSameSource:
    def test_detail_response_derives_from_configuration(self):
        """内审 F1: detail 响应 (POST/GET/PATCH 三端点) 与列表同源 — 不然两个
        端点对同一用例报两个频率。变异 (删 Response 的 validator) → 红。"""
        row = _row(
            configuration={"frequency_hz": 3_549_990_000, "bandwidth_mhz": 40},
            expected_results=None, probe_selection=None, instrument_config=None,
            channel_parameters=None, tx_power_dbm=None,
            updated_at=datetime(2026, 1, 1), version="1", parent_id=None,
        )
        r = TestCaseResponse.model_validate(row)
        assert r.frequency_mhz == 3549.99
        assert r.bandwidth_mhz == 40.0


class TestTemplateCategoryLength:
    def test_over_100_chars_rejected_at_schema(self):
        """列是 String(100) — schema 无约束时超长打到 PG 直接 500;
        现在 422 在门口挡下。"""
        with pytest.raises(ValidationError):
            TestCaseCreate(
                name="n", test_type="MIMO_OTA", configuration={},
                created_by="t", template_category="x" * 101,
            )

    def test_100_chars_ok(self):
        tc = TestCaseCreate(
            name="n", test_type="MIMO_OTA", configuration={},
            created_by="t", template_category="x" * 100,
        )
        assert len(tc.template_category) == 100


class TestSessionChannelAsset:
    def test_channel_asset_id_passthrough(self):
        """带资产建会话 → overrides 里出现 str 形态的 channel_asset_id
        (measure resolver 按它派生 engine_mode / .smu 源)。"""
        aid = uuid4()
        req = CreateSessionRequest(channel_asset_id=aid)
        overrides = _request_overrides(req)
        assert overrides["channel_asset_id"] == str(aid)

    def test_absent_asset_leaks_nothing(self):
        """None 不发 — 不覆盖配置默认 (与 strict 门旗标同款 None-leaves-default)。"""
        overrides = _request_overrides(CreateSessionRequest())
        assert "channel_asset_id" not in overrides

    def test_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(channel_asset_id="not-a-uuid")
