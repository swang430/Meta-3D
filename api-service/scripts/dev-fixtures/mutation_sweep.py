"""系统性变异: 把模块里每一个 if 的条件逐个改成 False, 看测试红不红。
红 = 该分支被断言保护; 绿 = 空转 (那道闸拿掉也没人发现)。"""
import ast, pathlib, subprocess, sys

SRC = pathlib.Path("app/diagnostics/sequences/propsim_f64_state_machine.py")
TESTS = ["tests/test_f64_state_machine_sequence.py"]
orig = SRC.read_text()
tree = ast.parse(orig)

ifs = [n for n in ast.walk(tree) if isinstance(n, ast.If)]
print(f"模块里共 {len(ifs)} 个 if 分支\n")

# ⚠ 整个循环包在 try/finally 里: 45 次扫描耗时数分钟, **人工 Ctrl-C 是现实场景**;
# pytest 起不来 / subprocess 抛异常也一样。不兜的话工作区会留下一个被 ast.unparse
# 全量重写、且带 `if False` 的生产源文件 —— 注释全没了, 还是个被改坏的版本。
# (Codex #229 第七轮 P2 — 这个脚本是我自己写的, 同一天里我刚在别处强调过
#  "恢复必须是所有退出路径的共同出口", 写工具时又忘了。)
dead, alive = [], []
try:
  for i in range(len(ifs)):
      t = ast.parse(orig)
      targets = [n for n in ast.walk(t) if isinstance(n, ast.If)]
      node = targets[i]
      label = f"L{node.lineno}: {ast.unparse(node.test)[:70]}"
      node.test = ast.Constant(False)
      SRC.write_text(ast.unparse(t))
      r = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "--no-header",
                          "-p", "no:cacheprovider"], capture_output=True, text=True)
      (alive if "failed" in r.stdout[-400:] or "error" in r.stdout[-400:] else dead).append(label)
      SRC.write_text(orig)

finally:
    SRC.write_text(orig)   # 任何退出路径都还原

print(f"✅ 被断言保护 {len(alive)} 个")
print(f"❌ 空转(拿掉没人发现) {len(dead)} 个")
if dead:
    print("\n--- 空转的分支 ---")
    for d in dead:
        print("  ", d)
