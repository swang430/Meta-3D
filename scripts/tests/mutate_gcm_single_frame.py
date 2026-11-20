"""在临时目录逐一变异并实跑测试，不改工作树实现。"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = (
    ('材料独立性两处被同时绕过', 'all(not path.samefile(previous) for previous in paths)', 'True'),
    ('来源文件覆盖保护被绕过', "args.output.resolve() != path.resolve() and not (args.output.exists() and path.exists() and args.output.samefile(path))", 'True'),
    ('真实材料核验被跳过', "            _validate_real_source(frame)", "            pass"),
    ('TDD限制被绕过', "common['DLFREQUENCY'] == common['ULFREQUENCY']", 'True'),
    ('旋转被跳过', 'sum(row[j]*vector[j]/norm for j in range(3))', 'vector[matrix.index(row)]/norm'),
    ('方向反转被跳过', '(-1 if reverse else 1)', '1'),
    ('成员功率权重被抹平', '10**((_power_db(paths[m])-peak)/10)', '1'),
    ('方位中心改成普通均值', 'azimuth = math.degrees(math.atan2(y, x))', 'azimuth = sum(w*a for (a, _), w in zip(angles, weights))/total'),
    ('扩展被置零', 'az_spread, ze_spread\n', '0, 0\n'),
    ('簇功率被替换', '(cid, power, delay, a[0]', '(cid, -80, delay, a[0]'),
    ('绝对时延被替换', '(cid, power, delay, a[0]', '(cid, power, 1, a[0]'),
    ('同批校验被绕过', "path['batch_id'] == source['batch_id']", 'True'),
    ('簇同批校验被绕过', "cluster['batch_id'] == source['batch_id']", 'True'),
    ('成员覆盖校验被绕过', 'used == set(paths)', 'True'),
    ('功率时延范围被绕过', 'power < 0 and delay > 0', 'True'),
    ('直达条件被绕过', "frame['propagation'] in ('LOS', 'NLOS') and (0 in ids) == (frame['propagation'] == 'LOS')", 'True'),
    ('非直达数量被绕过', 'len(ids - {0}) <= 24', 'True'),
    ('扩展范围被绕过', 'a[2] <= 104 and d[2] <= 104 and a[3] <= 52 and d[3] <= 52', 'True'),
    ('镜像反射被接受', 'abs(determinant-1) < 1e-9', 'True'),
    ('正交性被绕过', 'abs(sum(matrix[k][i]*matrix[k][j] for k in range(3)) - (i == j)) < 1e-9', 'True'),
    ('重复成员被接受', "all(isinstance(m, str) and m in paths and m not in used for m in members) and len(set(members)) == len(members)", "all(isinstance(m, str) and m in paths for m in members)"),
    ('来源说明被移除', "result['INFO'] = source['kind'] + '-' + source['direction']", "result['INFO'] = ''"),
    ('时间格式被绕过', "isinstance(value, str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\\.[0-9]{3}', value)", 'True'),
    ('有限数校验被绕过', "type(value) in (int, float) and math.isfinite(value)", 'True'),
    ('编号上限被绕过', 'type(common[key]) is int and 1 <= common[key] <= maximum', 'True'),
    ('频率范围被绕过', '0 < common[key] < 100000', 'True'),
    ('来源必填被绕过', "isinstance(source[key], str) and bool(source[key].strip())", 'True'),
    ('位置范围被绕过', 'max(math.hypot(*bs), math.hypot(*ue)) < 100000', 'True'),
    ('链路距离被绕过', 'math.dist(bs, ue) < 100000', 'True'),
    ('上下行角度角色交换被跳过', "if source['direction'] == 'uplink':", 'if False:'),
    ('退化圆周中心被接受', 'math.hypot(x, y)/total > 1e-12', 'True'),
)


def main():
    source = (ROOT/'gcm_single_frame.py').read_text()
    killed = 0
    for name, old, new in MUTATIONS:
        if source.count(old) != 1:
            raise RuntimeError('变异锚点必须唯一：'+name)
        with tempfile.TemporaryDirectory() as temp:
            scripts = Path(temp)/'scripts'
            (scripts/'tests').mkdir(parents=True)
            shutil.copytree(ROOT/'fixtures', scripts/'fixtures')
            shutil.copy(ROOT/'tests/test_gcm_single_frame.py', scripts/'tests')
            mutated = source.replace(old, new)
            if name == '材料独立性两处被同时绕过':
                assert mutated.count('digest not in hashes') == 1
                mutated = mutated.replace('digest not in hashes', 'True')
            (scripts/'gcm_single_frame.py').write_text(mutated)
            run = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(scripts/'tests'), '-p', 'test_gcm_single_frame.py'], capture_output=True, text=True)
            # 仅行为断言失败算检出；导入或语法错误不能冒充红测试。
            detected = run.returncode != 0 and 'FAIL:' in run.stderr and 'ERROR:' not in run.stderr
            print(('检出' if detected else '未检出')+'：'+name)
            if not detected:
                print(run.stderr)
            killed += detected
    print(f'变异验证：{killed}/{len(MUTATIONS)} 项由行为断言检出')
    return 0 if killed == len(MUTATIONS) else 1


if __name__ == '__main__':
    sys.exit(main())
