import copy
import importlib.util
from pathlib import Path

import pytest


def collector():
    spec = importlib.util.spec_from_file_location('collect', Path(__file__).parents[1] / 'lauraycs_collect.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    from test_cluster_import import document
    value = document()
    value['schemaVersion'] = 'meta3d-lauraycs-request/1'
    value['samples'] = [{k: f[k] for k in ('sampleIndex', 'frameId', 'internalLinkId')}
                        for f in value.pop('frames')]
    return value


def reply(request):
    from test_cluster_import import document
    result = document()['frames'][0]['clustering']
    result['algorithm'] = 'cluster_cdl_kmeans'
    # 原版接口不返回聚簇多普勒，接收端必须显式保留未知。
    del result['paths'][0]['dopplerHz']
    return dict(code=200, data=dict(mpdbPath=request['mpdbPath'],
        internalLinkId=request['internalLinkId'], frameId=request['frameId'],
        available=True, pathCount=4, filteredPathCount=3, algorithms=[result]))


def test_existing_api_collects_every_frame_without_reclustering():
    calls = []
    def request(body):
        calls.append(copy.deepcopy(body))
        return reply(body)
    value = collector().collect(manifest(), request)
    assert len(calls) == 3
    assert [r['internalLinkId'] for r in calls] == [10, 11, 12]
    assert all(set(r) == {'mpdbPath', 'internalLinkId', 'frameId', 'kMeansClusterCount'} for r in calls)
    assert value['schemaVersion'] == 'meta3d-cluster-trajectory/1'
    assert value['frames'][-1]['timeSeconds'] == 1.145913773532114
    assert value['frames'][0]['clustering']['paths'][0]['dopplerHz'] is None
    assert 'dopplerHz' not in value['responses'][0]['data']['algorithms'][0]['paths'][0]
    assert value['hardwareEligible'] is False


@pytest.mark.parametrize('bad', ['identity', 'failure', 'unknown_empty', 'count', 'budget', 'algorithm',
                                'null_algorithm', 'null_path'])
def test_failed_frames_are_retained_and_not_accepted(bad):
    def request(body):
        if body['internalLinkId'] != 11:
            return reply(body)
        result = reply(body)
        if bad == 'identity': result['data']['frameId'] = 99
        if bad == 'failure': raise TimeoutError('timeout')
        if bad == 'unknown_empty': result['data'].update(available=False, unavailableReason='unknown')
        if bad == 'count': result['data']['pathCount'] = 500
        if bad == 'budget': result['data']['algorithms'][0]['paths'] *= 9
        if bad == 'algorithm': result['data']['algorithms'][0]['algorithm'] = 'other'
        if bad == 'null_algorithm': result['data']['algorithms'] = [None]
        if bad == 'null_path': result['data']['algorithms'][0]['paths'] = [None]
        return result
    value = collector().collect(manifest(), request)
    assert len(value['frames']) == 3
    assert value['frames'][1]['status'] == 'failed'
    assert value['collectionStatus'] == 'incomplete'
    assert value['frames'][2]['status'] == 'clustered'


@pytest.mark.parametrize('reason,count', [('no_paths', 0), ('no_valid_paths', 4)])
def test_empty_response_is_not_failed_or_dropped(reason, count):
    def request(body):
        result = reply(body)
        result['data'].update(available=False, unavailableReason=reason,
                              pathCount=count, filteredPathCount=0, algorithms=[])
        return result
    value = collector().collect(manifest(), request)
    assert [f['status'] for f in value['frames']] == [reason] * 3
    assert value['collectionStatus'] == 'complete'


def test_bad_manifest_is_rejected_before_network():
    value = manifest()
    value['timing']['timesSeconds'][1] = 0.
    with pytest.raises(ValueError):
        collector().collect(value, lambda _: pytest.fail('network called'))


def test_duplicate_link_identity_rejected_before_network():
    value = manifest()
    value['samples'][1].update(internalLinkId=10, frameId=0)
    with pytest.raises(ValueError):
        collector().collect(value, lambda _: pytest.fail('network called'))


def test_http_to_ce_uses_original_endpoint_and_preserves_response():
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from cluster_import import sampled_responses
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, self.headers.get('Authorization'), body))
            payload = json.dumps(reply(body)).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            module = collector()
            value = module.collect(manifest(), module.http_request(
                f'http://127.0.0.1:{server.server_port}', 'Bearer synthetic-test-only'))
            responses = sampled_responses(value, [0., 125e6])
            assert len(responses) == 3
            assert responses[0]['real'] == pytest.approx([-1., 2.])
            assert responses[-1]['timeSeconds'] == 1.145913773532114
            assert all(path == module.ENDPOINT and auth == 'Bearer synthetic-test-only'
                       for path, auth, _ in calls)
            assert len(calls) == 3
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.parametrize('failure', ['interrupted', 'http_500'])
def test_http_failure_retains_evidence_and_writes_remaining_frames(failure, tmp_path, monkeypatch):
    import base64
    import json
    import sys
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    calls = []
    error_body = json.dumps(reply({'mpdbPath': manifest()['source']['mpdbPath'],
                                 'internalLinkId': 11, 'frameId': 1})).encode()
    partial = b'{"code":200,'

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body['internalLinkId'])
            if body['internalLinkId'] == 11:
                if failure == 'interrupted':
                    self.send_response(200)
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    self.wfile.write(f'{len(partial):x}\r\n'.encode() + partial + b'\r\n')
                    # 完整发出一块后断开，不发送结束块，真实触发IncompleteRead。
                    self.close_connection = True
                else:
                    self.send_response(500)
                    self.send_header('Content-Length', str(len(error_body)))
                    self.end_headers()
                    self.wfile.write(error_body)
                return
            payload = json.dumps(reply(body)).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    source, target = tmp_path / 'manifest.json', tmp_path / 'result.json'
    source.write_text(json.dumps(manifest()), encoding='utf-8')
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setattr(sys, 'argv', ['collect', '--manifest', str(source),
                '--output', str(target), '--base-url', f'http://127.0.0.1:{server.server_port}'])
            assert collector().main() == 2
        finally:
            server.shutdown()
            thread.join()

    value = json.loads(target.read_text(encoding='utf-8'))
    assert calls == [10, 11, 12]
    assert [f['status'] for f in value['frames']] == ['clustered', 'failed', 'clustered']
    assert value['frames'][1]['clustering'] is None
    assert value['collectionStatus'] == 'incomplete'
    assert value['hardwareEligible'] is False
    assert len(value['responses']) == 3
    evidence = value['responses'][1]
    assert base64.b64decode(evidence['bodyBase64']) == (partial if failure == 'interrupted' else error_body)
    if failure == 'http_500':
        assert evidence['httpStatus'] == 500
    else:
        assert evidence['bodyIncomplete'] is True
