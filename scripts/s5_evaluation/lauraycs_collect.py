"""调用未修改Lauraycs已有逐帧接口，保存完整响应；不导入HyperRT或重新聚簇。"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cluster_import import validate_trajectory

ENDPOINT = '/api/task/channel-analysis/clustering/kmeans/analyze'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _manifest(value):
    require(isinstance(value, dict) and value.get('schemaVersion') == 'meta3d-lauraycs-request/1',
            '不支持的采集清单版本')
    result = copy.deepcopy(value)
    samples = result.pop('samples', None)
    require(isinstance(samples, list) and samples, '采集清单必须列出全部所需样本')
    times = result.get('timing', {}).get('timesSeconds', [])
    require(len(times) == len(samples), '样本数量与明确时间轴不一致')
    # 仅用空帧结构复用CE时间/身份校验；任何返回结果必须由下面真实请求逐帧填充。
    result['schemaVersion'] = 'meta3d-cluster-trajectory/1'
    result['frames'] = [dict(sampleIndex=s['sampleIndex'], frameId=s['frameId'],
        internalLinkId=s['internalLinkId'], timeSeconds=t, inputPathCount=0,
        status='no_paths', clustering=None) for s, t in zip(samples, times)]
    validate_trajectory(result)
    require(result['source']['mpdbPath'].startswith('s3://'), '必须使用Lauraycs任务内的MPDB位置')
    require(result['source']['additionalLoss'] is None,
            '现有逐帧接口不接收附加损耗选择，不能声明已应用')
    for s in samples:
        require(s.get('rxId') is None or type(s['rxId']) is int, '接收端身份无效')
    return result, samples


def collect(manifest, request):
    """失败帧留在结果内；complete仅表示清单请求完成，不表示完整任务或物理验收。"""
    try:
        output, samples = _manifest(manifest)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f'采集清单缺字段或结构错误：{exc}') from exc
    output.update(responses=[], collectionStatus='complete', hardwareEligible=False,
                  provenance='simulation-service-response',
                  sourceVerification='manifest-declared; service echoes sample identity only',
                  responseSemantics='source-channel-H')
    for index, sample in enumerate(samples):
        frame = output['frames'][index]
        body = dict(mpdbPath=output['source']['mpdbPath'], internalLinkId=sample['internalLinkId'],
                    frameId=sample['frameId'], kMeansClusterCount=output['requestedClusterCount'])
        if sample.get('rxId') is not None:
            body['rxId'] = sample['rxId']
        response = None
        try:
            response = request(body)
            # 不截断或清洗服务端证据；无效JSON数据按失败保存原因。
            json.dumps(response, allow_nan=False)
            require(isinstance(response, dict) and response.get('code') == 200, '服务没有返回成功响应')
            data = response['data']
            for key in ('mpdbPath', 'internalLinkId', 'frameId'):
                require(data[key] == body[key] and type(data[key]) is type(body[key]),
                        f'服务返回的样本身份不一致：{key}')
            if 'rxId' in body:
                require(data.get('rxId') == body['rxId'], '接收端身份不一致')
            count, valid = data['pathCount'], data['filteredPathCount']
            require(type(count) is int and type(valid) is int and 0 <= valid <= count, '服务路径计数无效')
            frame['inputPathCount'] = count
            if data['available'] is True:
                algorithms = data['algorithms']
                require(isinstance(algorithms, list) and len(algorithms) == 1, '需要一份明确的内置聚簇结果')
                result = copy.deepcopy(algorithms[0])
                require(isinstance(result, dict), '聚簇结果必须为对象')
                require(result.get('algorithm') == 'cluster_cdl_kmeans', '服务返回的聚簇算法不符')
                require(result['rawPaths'] == count and result['filteredPaths'] == valid, '聚簇与响应计数不一致')
                require(isinstance(result['paths'], list), '聚簇路径必须为数组')
                for path in result['paths']:
                    require(isinstance(path, dict), '聚簇路径必须为对象')
                    path.setdefault('dopplerHz', None)
                frame.update(status='clustered', clustering=result)
            else:
                reason = data.get('unavailableReason')
                require(data['available'] is False and reason in ('no_paths', 'no_valid_paths')
                        and data['algorithms'] == [] and valid == 0, '未知或失败状态不能冒充空帧')
                frame.update(status=reason, clustering=None)
            # 复用同一CE契约逐帧检查，不因一个坏帧丢掉其余请求证据。
            one = copy.deepcopy(output)
            one.pop('responses', None)
            one['frames'] = [dict(frame, sampleIndex=0)]
            one['timing']['timesSeconds'] = [frame['timeSeconds']]
            validate_trajectory(one)
            output['responses'].append(response)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            frame.update(status='failed', clustering=None, error=f'{type(exc).__name__}: {exc}')
            output['collectionStatus'] = 'incomplete'
            try:
                json.dumps(response, allow_nan=False)
                output['responses'].append(response)
            except (ValueError, TypeError):
                output['responses'].append({'invalidResponseRepr': repr(response)})
    if output['collectionStatus'] == 'complete':
        validate_trajectory(output)
    return output


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('拒绝重定向，请明确填写Lauraycs服务地址')


def http_request(base_url, authorization=None):
    parsed = urlsplit(base_url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment,
            '服务地址必须是明确HTTP(S)地址，不能夹带账号或查询参数')
    require(parsed.scheme == 'https' or parsed.hostname in ('localhost', '127.0.0.1', '::1'),
            '非本机服务须使用HTTPS')
    opener = build_opener(NoRedirect())
    def post(body):
        headers = {'Content-Type': 'application/json'}
        if authorization:
            headers['Authorization'] = authorization
        req = Request(base_url.rstrip('/') + ENDPOINT,
                      data=json.dumps(body, allow_nan=False).encode(), headers=headers, method='POST')
        with opener.open(req, timeout=60) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        require(len(raw) <= 16 * 1024 * 1024, '单帧响应超过读取限制')
        return json.loads(raw)
    return post


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ce-repo', type=Path)
    args = parser.parse_args()
    if args.ce_repo:
        sys.path.insert(0, str(args.ce_repo.resolve()))
    # 排除目标已存在后才计算，写出时仍使用独占创建，避免覆盖原始数据。
    require(not args.output.exists(), '输出文件已存在')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    output = collect(manifest, http_request(args.base_url, os.environ.get('LAURAYCS_AUTHORIZATION')))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({'collectionStatus': output['collectionStatus'], 'frames': len(output['frames']),
                      'hardwareEligible': False}, ensure_ascii=False))
    return 0 if output['collectionStatus'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
