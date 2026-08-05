#!/usr/bin/env python3
"""Incrementally merge repo ``config/app.json`` into the deploy target's app.json.

保留部署侧既有配置（运维可能在首次部署后修改过 app.json，CLAUDE.md 部署要求 3：
不要覆盖 config/app.json），仅补齐仓库新增的键（深合并：缺失键补齐，已有键保留
部署侧值）。用于 Jenkins 部署流水线。

Usage:
    merge_app_config.py <deploy_app.json> <repo_app.json>

Exit codes: 0 成功；2 参数错误。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def merge(base: dict, new: dict) -> dict:
    """Deep-merge ``new`` into ``base``: add missing keys, keep existing values."""
    for k, v in new.items():
        if k not in base:
            base[k] = v
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        # else: keep existing deploy value (do not overwrite)
    return base


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: merge_app_config.py <deploy_app.json> <repo_app.json>", file=sys.stderr)
        return 2
    deploy_path = Path(sys.argv[1])
    repo_path = Path(sys.argv[2])
    repo_cfg = json.loads(repo_path.read_text(encoding="utf-8"))

    if not deploy_path.exists():
        deploy_path.parent.mkdir(parents=True, exist_ok=True)
        deploy_path.write_text(
            json.dumps(repo_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"首次部署：写入默认 {deploy_path}")
        return 0

    deploy_cfg = json.loads(deploy_path.read_text(encoding="utf-8"))
    merge(deploy_cfg, repo_cfg)
    deploy_path.write_text(
        json.dumps(deploy_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已增量合并 {deploy_path} 新键（保留部署侧既有配置）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
