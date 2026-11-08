"""PC14核心逆变异：唯一片段替换，finally逆向恢复，不覆盖并行编辑。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SINGLE = ROOT / 'app/services/calibration/fixed_route_jobs.py'
BATCH = ROOT / 'app/services/calibration/route_batch_jobs.py'
SINGLE_API = ROOT / 'app/api/fixed_route_acquisition.py'
BATCH_API = ROOT / 'app/api/route_batch.py'
READ = 'tests/test_pc04a14_status_read_race.py'
START = 'tests/test_pc04a14_start_ownership.py'
ASGI = 'tests/test_pc04a14_status_asgi.py'
MUTATIONS = [
    ('skip_single_reread', [(SINGLE_API,
        'return jobs.read_record(db, row)',
        'return jobs.record(row, batch_context=batch_child_context(db, row))')],
        [READ+'::test_single_committed_terminal_beats_callers_stale_running',
         ASGI+'::test_asgi_thread_old_read_overlaps_real_terminal_commit[progress-False]']),
    ('skip_batch_reread', [(BATCH_API,
        'BatchJobRecord.model_validate(jobs.read_record(db,row))',
        'BatchJobRecord.model_validate(jobs.record(db,row))')],
        [READ+'::test_batch_parent_and_child_read_same_committed_finalization',
         ASGI+'::test_asgi_thread_old_read_overlaps_real_terminal_commit[progress-True]']),
    ('publish_before_registration', [
        (SINGLE, '        _running[run_id] = (task, cancel)\n        db.commit()',
                 '        db.commit()\n        _running[run_id] = (task, cancel)'),
        (BATCH, '        _running[ident]=active\n        db.commit()',
                '        db.commit()\n        _running[ident]=active')],
        [START+'::test_running_commit_is_never_visible_without_registered_task']),
    ('release_on_response_failure', [
        (SINGLE, '    db.refresh(row)\n    return record(row)',
                 '    try:\n        db.refresh(row)\n        return record(row)\n    except BaseException:\n        release_unsafe_diagnostic(token)\n        raise'),
        (BATCH, '    # 提交后由后台任务负责最终持久化与释放；序列化失败不释放占位。\n    return record(db,row)',
                '    # 提交后由后台任务负责最终持久化与释放；序列化失败不释放占位。\n    try:\n        return record(db,row)\n    except BaseException:\n        release_unsafe_diagnostic(token)\n        raise')],
        [START+'::test_committed_job_keeps_guard_if_response_parsing_fails']),
    ('denied_is_not_parent_exit', [(SINGLE,
        "bool(context and context.get('job_id') and context.get('active') is False)",
        "bool(context and context.get('active') is False)")],
        [READ+'::test_denied_old_child_context_does_not_invent_parent_exit']),
]


def main():
    for name, edits, tests in MUTATIONS:
        applied = []
        try:
            for path, before, after in edits:
                original = path.read_text()
                if original.count(before) != 1 or after in original:
                    raise RuntimeError(f'{name}: 替换锚点不唯一或变异已存在')
                path.write_text(original.replace(before, after, 1))
                applied.append((path, before, after, original))
            with tempfile.TemporaryDirectory(prefix='pc14-mutation-') as directory:
                env = dict(os.environ, DATABASE_URL=f'sqlite:///{directory}/test.db',
                    USE_MOCK_INSTRUMENTS='true', PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=f'{directory}/pycache')
                result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '--tb=short', *tests],
                    cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                Path(f'/tmp/pc14-mutation-{name}.log').write_text(result.stdout)
                summaries = [line for line in result.stdout.splitlines() if ' failed' in line or ' passed' in line]
                print(name, 'exit='+str(result.returncode), summaries[-1:], flush=True)
                if result.returncode != 1 or ' failed' not in result.stdout:
                    raise RuntimeError(f'{name}: 未被行为断言杀死')
        finally:
            for path, before, after, original in reversed(applied):
                current = path.read_text()
                if current.count(after) != 1:
                    raise RuntimeError(f'{name}: 发生并行编辑，拒绝覆盖')
                restored = current.replace(after, before, 1)
                path.write_text(restored)
                if restored != original:
                    raise RuntimeError(f'{name}: 恢复与原文不同')
    print('5 mutations killed; all source fragments restored', flush=True)


if __name__ == '__main__':
    main()
