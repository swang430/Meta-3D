"""新历史/恢复端点的运行时及发布OpenAPI契约。"""
from pathlib import Path
import yaml
from app.main import app


def test_published_history_restore_contract_matches_runtime():
    runtime = app.openapi()
    published = yaml.safe_load((Path(__file__).parents[2] / 'api/openapi.yaml').read_text())
    for suffix, verb in [('revisions','get'), ('revisions/{revision}','get'),
                         ('restore-preview','post'), ('restore','post')]:
        path = '/api/v1/switch-topologies/{topology_id}/' + suffix
        assert published['paths'][path][verb] == runtime['paths'][path][verb]
    for name in ('TopologyRestoreRequest','TopologyRevisionSummary','TopologyRevisionDetail',
                 'TopologyRevisionList','TopologyFieldDifference','TopologyRestorePreview'):
        assert published['components']['schemas'][name] == runtime['components']['schemas'][name]
