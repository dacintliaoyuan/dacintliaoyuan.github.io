"""One-off local migration commands for the image workbench.

Usage:
  python tools/image_workbench_migrate.py enabled
  python tools/image_workbench_migrate.py deletion-manifest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_workbench import migration, state


def main(argv=None):
    parser = argparse.ArgumentParser(description="图片工作台迁移与删除清单（只在本机运行）")
    parser.add_argument("command", choices=("enabled", "deletion-manifest"))
    parser.add_argument("--library", type=Path, default=state.LIBRARY)
    parser.add_argument("--old-library", type=Path, default=migration.OLD_LIBRARY)
    parser.add_argument("--site", type=Path, default=state.ROOT / "site")
    parser.add_argument("--approved", type=Path)
    parser.add_argument("--tags", type=Path)
    parser.add_argument("--formal-manifest", type=Path)
    parser.add_argument("--pipeline", type=Path)
    args = parser.parse_args(argv)
    store = state.StateStore(args.library)
    try:
        if args.command == "enabled":
            report = migration.migrate_enabled(
                store,
                approved_path=args.approved,
                tags_path=args.tags,
                library=args.library,
                old_library=args.old_library,
                formal_manifest=args.formal_manifest,
                site=args.site,
            )
            print(f"[migrate] 已复制并核对 {report['count']} 张母版，"
                  f"共 {report['copiedBytes']} 字节")
            print(f"[migrate] 草稿 {report['draftId']}："
                  f"{report['draftSceneCount']} 张场景")
            print(f"[migrate] 正式主页未修改；报告：{args.library / 'migration-report.json'}")
        else:
            manifest = migration.build_deletion_manifest(
                store,
                pipeline_path=args.pipeline,
                approved_path=args.approved,
                library=args.library,
                old_library=args.old_library,
                root=state.ROOT,
            )
            print(f"[deletion] 待确认 {manifest['totals']['files']} 个文件，"
                  f"{manifest['totals']['bytes']} 字节")
            print(f"[deletion] 未删除任何文件；清单：{args.library / 'deletion-manifest.json'}")
    except (ValueError, OSError, RuntimeError) as error:
        print(f"失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
