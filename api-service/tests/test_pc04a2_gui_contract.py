"""拓扑侧栏公开契约：运行时序列化schema与checked镜像逐项一致。"""
from pathlib import Path
import yaml
from app.main import app


def test_topology_calibration_public_schemas_and_routes_match_live_openapi():
    checked=yaml.safe_load((Path(__file__).resolve().parents[2]/'api/openapi.yaml').read_text())
    live=app.openapi()
    for name in ('FixedRouteRequest','FixedRouteResult','FixedRouteRecord','RoutePort','RouteSelection',
                 'RouteEligibility','RouteApplicationPreview','ConfirmRouteApplication','RouteApplicationRecord'):
        assert checked['components']['schemas'][name]==live['components']['schemas'][name],name
    base='/api/v1/lab-profiles/{lab_profile_id}'
    for suffix in ('/route-calibration-paths','/fixed-route-acquisitions/{run_id}/application-preview',
                   '/route-calibration-applications'):
        assert checked['paths'][base+suffix]==live['paths'][base+suffix]
