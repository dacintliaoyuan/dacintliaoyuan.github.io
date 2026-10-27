"""Builds the mouse pointer's art file from its editable source, or renders a slice of it.

The art lives in site/pointer-art.source.json (schema 1, 46x27 squares); site/pointer-art.js is the
deterministic `window.HOME_POINTER_ART = <source>;` written from it. site/pointer.js reads that global
and keeps the movement, the glyphs and the pointer's behaviour.

Usage:
  python tools/build_pointer_assets.py --check
      Compare site/pointer-art.js with the source; exit 0 only when it is up to date.
  python tools/build_pointer_assets.py --write
      Write site/pointer-art.js from the source.
  python tools/build_pointer_assets.py --render ROLE EXPRESSION OUT.png [--scale N] [--shy]
      Render shima, adachi or full at open/shut/happy/squint; nearest neighbour when scaled.
  python tools/build_pointer_assets.py --seed [--from POINTER.js] [--source PATH]
      Read a pointer.js that still holds the constants and write the editable source (one-time seed).

Paths are relative to the current directory; --source and --output default to the formal site files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pointer_art
from pointer_art import PointerArtError


def _first_difference(expected: str, actual: str) -> str:
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    for number, (want, got) in enumerate(zip(expected_lines, actual_lines), 1):
        if want != got:
            return f"第 {number} 行不同：期望 {want!r}，实际 {got!r}"
    return f"行数不同：期望 {len(expected_lines)} 行，实际 {len(actual_lines)} 行"


def _check(source_path: Path, output_path: Path) -> int:
    source = pointer_art.load_source(source_path)
    expected = pointer_art.generate_js(source)
    if not output_path.is_file():
        print(f"缺少 {output_path}；先运行 --write", file=sys.stderr)
        return 1
    actual = output_path.read_text(encoding="utf-8")
    if actual != expected:
        print(f"{output_path} 与来源不一致：{_first_difference(expected, actual)}", file=sys.stderr)
        return 1
    print(f"{output_path} 与 {source_path} 一致")
    return 0


def _write(source_path: Path, output_path: Path) -> int:
    source = pointer_art.load_source(source_path)
    text = pointer_art.generate_js(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"已写入 {output_path}")
    return 0


def _render(source_path: Path, role: str, expression: str, out: Path, scale: int, shy: bool) -> int:
    source = pointer_art.load_source(source_path)
    if role == "full":
        image = pointer_art.render_full(source, expression, shy=shy)
    else:
        image = pointer_art.render_role(source, role, expression, shy=shy)
    if scale != 1:
        image = pointer_art.render_preview(image, scale)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"已渲染 {role} {expression} -> {out}（{image.width}×{image.height}）")
    return 0


def _seed(from_path: Path | None, source_path: Path) -> int:
    if from_path is None:
        baseline = pointer_art.HOME / ".local" / "tmp" / "pointer-baseline.js"
        from_path = baseline if baseline.is_file() else pointer_art.POINTER_PATH
    source = pointer_art.parse_pointer_js(from_path)
    pointer_art.save_source(source, source_path)
    print(f"已从 {from_path} 提取来源到 {source_path}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the mouse pointer's art from its editable source.")
    parser.add_argument("--source", type=Path, default=pointer_art.SOURCE_PATH,
                        help=f"editable source (default: {pointer_art.SOURCE_PATH})")
    parser.add_argument("--output", type=Path, default=pointer_art.GENERATED_PATH,
                        help=f"generated JavaScript (default: {pointer_art.GENERATED_PATH})")
    parser.add_argument("--check", action="store_true", help="compare the generated file with the source")
    parser.add_argument("--write", action="store_true", help="write the generated file")
    parser.add_argument("--render", nargs=3, metavar=("ROLE", "EXPRESSION", "OUT"),
                        help="render shima, adachi or full at open, shut, happy or squint")
    parser.add_argument("--scale", type=int, default=1, help="whole-square enlargement for --render (default 1)")
    parser.add_argument("--shy", action="store_true", help="deepen Adachi's blush for --render")
    parser.add_argument("--seed", action="store_true", help="extract the source from a pointer.js with constants")
    parser.add_argument("--from", dest="from_path", type=Path, default=None,
                        help="pointer.js to seed from (default: .local/tmp/pointer-baseline.js, else site/pointer.js)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    actions = [args.check, args.write, bool(args.render), args.seed]
    if sum(actions) != 1:
        parser.error("需要且只能给一个：--check、--write、--render、--seed")
    try:
        if args.check:
            return _check(args.source, args.output)
        if args.write:
            return _write(args.source, args.output)
        if args.render:
            role, expression, out = args.render
            if role not in ("shima", "adachi", "full"):
                parser.error("--render 的角色必须是 shima、adachi 或 full")
            if expression not in pointer_art.EXPRESSIONS:
                parser.error("--render 的表情必须是 open、shut、happy 或 squint")
            return _render(args.source, role, expression, Path(out), args.scale, args.shy)
        return _seed(args.from_path, args.source)
    except (PointerArtError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
