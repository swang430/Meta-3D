"""P2-79A：归属字段/批量确认在 live、YAML、生成和手写类型中同义。"""
from pathlib import Path
import yaml
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_owner_contract_is_present_in_all_four_mirrors():
    live = app.openapi()
    checked = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())
    for name in ("ChannelAssetCreate", "ChannelAssetUpdate", "ChannelAssetResponse", "SCDCreateRequest"):
        assert "instrument_model_id" in live["components"]["schemas"][name]["properties"]
        assert "instrument_model_id" in checked["components"]["schemas"][name]["properties"]
    path = "/api/v1/channel-assets/vendor-files/confirm-ownership"
    assert path in checked["paths"] and path in live["paths"]
    assert "instrument_model_id" in checked["components"]["schemas"]["SCDCreateRequest"]["required"]
    generated = (ROOT / "gui/src/types/api.generated.ts").read_text()
    assert path in generated
    for path in ("channelAssetService.ts", "standardChannelService.ts"):
        assert "instrument_model_id" in (ROOT / "gui/src/api" / path).read_text()
