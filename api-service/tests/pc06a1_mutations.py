"""Task6核心撤门变异：仅当前pytest进程替换函数code，finally恢复，不改生产文件。"""
import importlib
import inspect
import sys
import textwrap
import pytest

CASES = {
    'exclusion': ('app.services.calibration.route_batch_jobs', 'start',
        'token=try_acquire_unsafe_diagnostic(TARGET)', 'token=object()',
        'tests/test_pc06a1_batch_jobs.py::test_serial_batches_hold_guard_across_manual_wait_and_reenter'),
    'switch_error': ('app.services.calibration.route_batch_switch', 'apply_batch_switch_steps',
        ("if before['error']:", "if receipt['error']:"), ('if False:', 'if False:'),
        'tests/test_pc06a1_batch_safety.py::test_switch_failure_pauses_without_collect_and_continue_explicitly_skips'),
    'cleanup': ('app.services.calibration.route_batch_jobs', '_execute',
        ("if result.status=='cleanup_unconfirmed' or (result.status!='simulated' and result.cleanup_confirmed is not True):",
         "if results and not clean and any(r.status!='simulated' for r in results):"),
        ('if False:', 'if False:'),
        'tests/test_pc06a1_batch_safety.py::test_cleanup_unknown_blocks_manual_permanently_and_overrides_cancel'),
    'restart': ('app.services.calibration.route_batch_jobs', 'record',
        "if value['status'] in ACTIVE and row.id not in _running:", 'if False:',
        'tests/test_pc06a1_batch_jobs.py::test_active_child_and_restart_use_parent_not_single_registry'),
    'mock_adoption': ('app.services.calibration.fixed_route_evidence', 'check_fixed_route_evidence',
        "return 'simulated',['simulated_measurement']", "return 'real',[]",
        'tests/test_pc04a2_route_eligibility.py::test_mock_and_legacy_captures_are_not_eligible_and_other_lab_cannot_read_preview'),
}

class Mutation:
    def __init__(self, case):
        self.case=case; self.original=None; self.function=None
    def pytest_runtest_call(self, item):
        module,name,needle,replacement,_=CASES[self.case]
        self.function=getattr(importlib.import_module(module),name)
        source=textwrap.dedent(inspect.getsource(self.function))
        pairs=zip(needle,replacement) if isinstance(needle,tuple) else [(needle,replacement)]
        for old,new in pairs:
            assert source.count(old)==1, '变异锚点必须精确命中一次'
            source=source.replace(old,new)
        namespace={}
        exec(compile(source,f'<pc06a1-{self.case}-mutation>','exec'),self.function.__globals__,namespace)
        self.original=self.function.__code__
        self.function.__code__=namespace[name].__code__
    def restore(self):
        if self.original is not None:
            self.function.__code__=self.original
            print('MUTATION_RESTORED=True')

if __name__=='__main__':
    case=sys.argv[1]
    plugin=Mutation(case)
    try:
        result=pytest.main([CASES[case][-1],'-q','-o','log_cli=false','--show-capture=no'],plugins=[plugin])
        print(f'MUTATION_TEST_EXIT={int(result)}')
        assert result==1, '撤门后必须是行为断言失败，不得空转或导入错误'
    finally:
        plugin.restore()
