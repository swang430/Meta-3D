"""从全部源帧识别端口，检查每一帧的完整收发矩阵。"""
from itertools import product
from numbers import Integral


def port_layout(frames, transmit, receive):
    if any(not isinstance(v, Integral) or v < 0 for col in (transmit, receive) for v in col):
        raise ValueError("收发端口编号必须为非负整数")
    tx = sorted(set(map(int, transmit)))
    rx = sorted(set(map(int, receive)))
    if not tx or not rx:
        raise ValueError("传播数据没有收发端口")
    expected = set(product(tx, rx))
    observed = {}
    for frame, t, r in zip(frames, transmit, receive, strict=True):
        pairs = observed.setdefault(int(frame), set())
        if (t, r) in pairs:
            raise ValueError(f"源帧 {frame} 重复发射端口 {t} 到接收端口 {r} 的链路")
        pairs.add((t, r))
    for frame, pairs in sorted(observed.items()):
        if missing := sorted(expected - pairs):
            t, r = missing[0]
            raise ValueError(f"源帧 {frame} 缺少发射端口 {t} 到接收端口 {r} 的链路")
    return tx, rx
