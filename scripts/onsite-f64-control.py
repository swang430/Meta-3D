#!/usr/bin/env python3
"""现场 F64 控制权交接与 `.smu` 自动加载工具。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_API = "http://127.0.0.1:8000/api/v1"


def request_json(url: str, *, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接后台服务: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="交还/取得 F64 控制权，或自动加载指定的 F64 本机 .smu 文件",
    )
    parser.add_argument(
        "--api",
        default=os.environ.get("MIMO_API_BASE", DEFAULT_API),
        help=f"API 根地址（默认 {DEFAULT_API}，也可用 MIMO_API_BASE）",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="查看控制权状态（不发送 SCPI）")
    sub.add_parser("local", help="释放 ATE socket，暂停轮询，交还前面板")
    sub.add_parser("remote", help="显式重新取得远程控制并恢复连接")
    load = sub.add_parser("load", help="取得 Remote、加载 .smu 并做 STATE? 回读确认")
    load.add_argument("file_path", help=r"F64 本机上的完整路径，例如 D:\User Emulations\x.smu")
    args = parser.parse_args()

    base = args.api.rstrip("/") + "/instruments/channelEmulator"
    try:
        if args.command == "status":
            result = request_json(base + "/control-ownership")
        elif args.command == "local":
            result = request_json(
                base + "/control-ownership", body={"action": "release_local"}
            )
        elif args.command == "remote":
            result = request_json(
                base + "/control-ownership", body={"action": "acquire_remote"}
            )
        else:
            if not args.file_path.lower().endswith(".smu"):
                parser.error("load 只接受 .smu 文件")
            result = request_json(base + "/load-smu", body={"file_path": args.file_path})
    except RuntimeError as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
