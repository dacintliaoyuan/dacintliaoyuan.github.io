"""The mouse pointer's art as editable data: site/pointer-art.source.json, and the deterministic
site/pointer-art.js written from it by tools/build_pointer_assets.py.

The picture is 46 squares across and 27 down, one character a square in the palette ('.' clear); the
two of them are split into layers at SPLIT, their eyes and the 5x5 masks drawn over them, and Adachi's
blush deepened. pointer.js keeps the movement, the glyphs and the pointer's behaviour; this module only
reads and writes the art.

The source keeps the same shape as the JavaScript object in site/pointer-art.js:

    schemaVersion, width, height, colours, picture, split, skin, eyes, lids, shy, faces, layers

`layers` is null for each of the two when the layer is derived from `picture` and `split` as
pointer.js always did; a layer that is not null is the role's own 27 rows of 46 squares. The generated
file is `window.HOME_POINTER_ART = <source>;`, with no timestamp and nothing random, so that --check
can compare it byte for byte.

Usage: imported by tools/build_pointer_assets.py and the creative workbench; not a command itself.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Iterable

from PIL import Image


HOME = Path(__file__).resolve().parent.parent
SITE = HOME / "site"
SOURCE_PATH = SITE / "pointer-art.source.json"
GENERATED_PATH = SITE / "pointer-art.js"
POINTER_PATH = SITE / "pointer.js"

SCHEMA_VERSION = 1
WIDTH = 46
HEIGHT = 27
ROLES = ("shima", "adachi")
EXPRESSIONS = ("open", "shut", "happy", "squint")
FACE_NAMES = ("click", "press", "grabbing")
LID_NAMES = ("shut", "happy", "squint")
# New palette keys are taken in this order: the digits, then the capitals, then the small letters.
PALETTE_KEYS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
# Short arrays and objects stay on one line in the source and the generated file, so that a pair of eyes
# can find a row or an eye without counting lines; anything longer is broken one item a line.
INLINE_LIMIT = 120
TOP_KEYS = ("schemaVersion", "width", "height", "colours", "picture", "split", "skin", "eyes", "lids", "shy",
             "faces", "layers")

__all__ = [
    "PointerArtError", "SOURCE_PATH", "GENERATED_PATH", "POINTER_PATH", "SCHEMA_VERSION", "WIDTH", "HEIGHT",
    "ROLES", "EXPRESSIONS", "FACE_NAMES", "LID_NAMES", "PALETTE_KEYS", "hex_to_rgb", "rgb_to_hex",
    "assign_palette", "validate_source", "load_source", "load_generated", "save_source", "generate_js",
    "parse_pointer_text", "parse_pointer_js", "derive_layers", "layer_rows", "compose_layers", "compose",
    "render_full", "render_role", "render_preview", "rows_from_image", "source_from_png", "build_runtime",
]


try:
    # The creative workbench's own error, so that its server catches a bad source the same way it
    # catches the rest (tools/ is on sys.path when the workbench runs).
    from creative_workbench import PointerArtError as _WorkbenchPointerArtError
except Exception:   # the standalone tool (and its tests) without the workbench package
    class PointerArtError(ValueError):
        """The pointer art or the pointer's JavaScript does not have the shape this tool expects."""
else:
    class PointerArtError(_WorkbenchPointerArtError, ValueError):
        """The workbench's pointer error, and a ValueError for the standalone tool's callers."""


def _fail(message: str) -> None:
    raise PointerArtError(message)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_pair(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2


def _rows(value, width: int, height: int, colours: dict, where: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) != height:
        _fail(f"{where} 必须是 {height} 行")
    rows = []
    for y, line in enumerate(value):
        if not isinstance(line, str) or len(line) != width:
            _fail(f"{where} 第 {y + 1} 行必须是 {width} 个字符")
        for x, ch in enumerate(line):
            if ch != "." and ch not in colours:
                _fail(f"{where} 第 {y + 1} 行第 {x + 1} 列的颜色 {ch!r} 不在调色板里")
        rows.append(line)
    return rows


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """'#rrggbb' as (r, g, b)."""
    if not isinstance(value, str) or not HEX.match(value):
        _fail(f"颜色 {value!r} 不是 #rrggbb")
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def rgb_to_hex(rgb: Iterable[int]) -> str:
    """(r, g, b) as '#rrggbb', the palette's own spelling."""
    r, g, b = (int(v) for v in rgb)
    if not all(0 <= v <= 255 for v in (r, g, b)):
        _fail(f"颜色 {r, g, b} 超出 0..255")
    return f"#{r:02x}{g:02x}{b:02x}"


def assign_palette(colours: dict[str, str], rgb: tuple[int, int, int]) -> str:
    """The key for an opaque (r, g, b) in `colours`, adding the first free key when it is new.

    An existing colour is reused whatever its case; a new one is written in lower-case hex. The palette is
    changed in place. New keys are taken in PALETTE_KEYS order, digits first.
    """
    if not isinstance(colours, dict):
        _fail("调色板必须是对象")
    wanted = rgb_to_hex(rgb)
    for key, value in colours.items():
        if isinstance(value, str) and value.lower() == wanted:
            return key
    for key in PALETTE_KEYS:
        if key not in colours:
            colours[key] = wanted
            return key
    _fail("调色板已满，无法加入新颜色")


def validate_source(source) -> dict:
    """Check a source against schema 1 and return it in canonical key order.

    Raises PointerArtError with the field and the reason when it cannot be used. Tuples are accepted for
    the pairs and rows JSON writes as lists.
    """
    if not isinstance(source, dict):
        _fail("来源必须是对象")
    extra = [key for key in source if key not in TOP_KEYS]
    if extra:
        _fail(f"来源有未知字段：{', '.join(map(str, extra))}")
    missing = [key for key in TOP_KEYS if key not in source]
    if missing:
        _fail(f"来源缺少字段：{', '.join(missing)}")
    if not _is_int(source["schemaVersion"]) or source["schemaVersion"] != SCHEMA_VERSION:
        _fail(f"schemaVersion 必须是 {SCHEMA_VERSION}")
    if not _is_int(source["width"]) or source["width"] != WIDTH:
        _fail(f"width 必须是 {WIDTH}")
    if not _is_int(source["height"]) or source["height"] != HEIGHT:
        _fail(f"height 必须是 {HEIGHT}")

    raw_colours = source["colours"]
    if not isinstance(raw_colours, dict) or not raw_colours:
        _fail("colours 必须是非空对象")
    colours: dict[str, str] = {}
    for key, value in raw_colours.items():
        if not isinstance(key, str) or len(key) != 1 or key == "." or key not in PALETTE_KEYS:
            _fail(f"调色板键 {key!r} 必须是 0-9、A-Z、a-z 中的单个字符")
        if not isinstance(value, str) or not HEX.match(value):
            _fail(f"调色板 {key!r} 的值 {value!r} 不是 #rrggbb")
        colours[key] = value
    if len(colours) > len(PALETTE_KEYS):
        _fail(f"调色板最多 {len(PALETTE_KEYS)} 色")

    picture = _rows(source["picture"], WIDTH, HEIGHT, colours, "picture")
    split = source["split"]
    if not isinstance(split, (list, tuple)) or len(split) != HEIGHT:
        _fail(f"split 必须是 {HEIGHT} 个整数")
    if not all(_is_int(cut) and 1 <= cut <= WIDTH for cut in split):
        _fail(f"split 的每一项必须是 1..{WIDTH} 的整数")
    split = [int(cut) for cut in split]

    skin = source["skin"]
    if not isinstance(skin, str) or skin not in colours:
        _fail("skin 必须是调色板的键")

    eyes = source["eyes"]
    if not isinstance(eyes, dict) or set(eyes) != set(ROLES):
        _fail("eyes 必须恰好是 shima 和 adachi")
    eyes_out: dict[str, list[list[int]]] = {}
    for role in ROLES:
        value = eyes[role]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            _fail(f"eyes.{role} 必须是两只眼睛")
        pairs = []
        for side, pair in enumerate(value):
            if not _is_pair(pair) or not all(_is_int(n) for n in pair):
                _fail(f"eyes.{role} 第 {side + 1} 只眼睛必须是两个整数")
            ex, ey = pair
            if ex < 0 or ey < 0 or ex + 5 > WIDTH or ey + 5 > HEIGHT:
                _fail(f"eyes.{role} 第 {side + 1} 只眼睛的 5×5 遮罩超出画面")
            pairs.append([int(ex), int(ey)])
        eyes_out[role] = pairs

    lids = source["lids"]
    if not isinstance(lids, dict) or set(lids) != set(LID_NAMES):
        _fail("lids 必须恰好是 shut、happy 和 squint")
    lids_out: dict[str, list[str]] = {}
    for name in LID_NAMES:
        mask = lids[name]
        if not isinstance(mask, (list, tuple)) or len(mask) != 5:
            _fail(f"lids.{name} 必须是 5 行")
        rows = []
        for y, line in enumerate(mask):
            if not isinstance(line, str) or len(line) != 5:
                _fail(f"lids.{name} 第 {y + 1} 行必须是 5 个字符")
            for x, ch in enumerate(line):
                if ch != "." and ch not in colours:
                    _fail(f"lids.{name} 第 {y + 1} 行第 {x + 1} 列的颜色 {ch!r} 不在调色板里")
            rows.append(line)
        lids_out[name] = rows

    shy = source["shy"]
    if not isinstance(shy, str) or not HEX.match(shy):
        _fail("shy 必须是 #rrggbb")

    faces = source["faces"]
    if not isinstance(faces, dict) or set(faces) != set(FACE_NAMES):
        _fail("faces 必须恰好是 click、press 和 grabbing")
    faces_out: dict[str, list] = {}
    for name in FACE_NAMES:
        face = faces[name]
        if not isinstance(face, (list, tuple)) or len(face) != 3:
            _fail(f"faces.{name} 必须是 [表情, 表情, 是否脸红]")
        if face[0] not in EXPRESSIONS or face[1] not in EXPRESSIONS:
            _fail(f"faces.{name} 的表情必须是 {'/'.join(EXPRESSIONS)}")
        if not isinstance(face[2], bool):
            _fail(f"faces.{name} 的第三项必须是布尔值")
        faces_out[name] = [face[0], face[1], face[2]]

    layers = source["layers"]
    if layers is None:
        layers = {"shima": None, "adachi": None}
    if not isinstance(layers, dict) or set(layers) - set(ROLES):
        _fail("layers 只能有 shima 和 adachi")
    layers_out: dict[str, list[str] | None] = {}
    for role in ROLES:
        value = layers.get(role)
        if value is None:
            layers_out[role] = None
        else:
            layers_out[role] = _rows(value, WIDTH, HEIGHT, colours, f"layers.{role}")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "width": WIDTH,
        "height": HEIGHT,
        "colours": colours,
        "picture": picture,
        "split": split,
        "skin": skin,
        "eyes": eyes_out,
        "lids": lids_out,
        "shy": shy,
        "faces": faces_out,
        "layers": layers_out,
    }


def load_source(path=SOURCE_PATH) -> dict:
    """Read and validate a source JSON file."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        _fail(f"读不到 {path}：{exc}")
    except json.JSONDecodeError as exc:
        _fail(f"{path} 不是合法 JSON：{exc}")
    return validate_source(data)


def load_generated(path=GENERATED_PATH) -> dict:
    """Read and validate a generated pointer-art.js."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"读不到 {path}：{exc}")
    prefix = "window.HOME_POINTER_ART = "
    if not text.startswith(prefix):
        _fail(f"{path} 不是 window.HOME_POINTER_ART = ...;")
    body = text[len(prefix):].strip()
    if not body.endswith(";"):
        _fail(f"{path} 缺少结尾的 `;`")
    try:
        data = json.loads(body[:-1])
    except json.JSONDecodeError as exc:
        _fail(f"{path} 不是合法 JSON：{exc}")
    return validate_source(data)


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def _pretty(value, indent: int = 0) -> str:
    """JSON with short arrays and objects on one line, the long ones one item a line."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        compact = _compact(value)
        if len(compact) <= INLINE_LIMIT:
            return compact
        lines = [f"{pad}  {json.dumps(key, ensure_ascii=False)}: {_pretty(item, indent + 1)}"
                 for key, item in value.items()]
        return "{\n" + ",\n".join(lines) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        compact = _compact(value)
        if len(compact) <= INLINE_LIMIT:
            return compact
        lines = [f"{pad}  {_pretty(item, indent + 1)}" for item in value]
        return "[\n" + ",\n".join(lines) + f"\n{pad}]"
    return _compact(value)


def save_source(source, path=SOURCE_PATH) -> None:
    """Write a source in the one canonical form --write and the workbench use."""
    source = validate_source(source)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_pretty(source) + "\n", encoding="utf-8", newline="\n")


def generate_js(source) -> str:
    """The deterministic site/pointer-art.js: window.HOME_POINTER_ART = <source>;"""
    source = validate_source(source)
    return "window.HOME_POINTER_ART = " + _pretty(source) + ";\n"


def _strip_comments(text: str) -> str:
    """Remove JavaScript comments outside strings, so the constants can be parsed."""
    out: list[str] = []
    i = 0
    quote = None
    while i < len(text):
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < len(text) and text[i + 1] == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


class _LiteralParser:
    """Just enough JavaScript for the object and array literals pointer.js holds."""

    def __init__(self, text: str, pos: int = 0):
        self.text = text
        self.i = pos

    def error(self, message: str):
        _fail(f"pointer.js 偏移 {self.i}：{message}")

    def skip(self) -> None:
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ""

    def statement_value(self):
        value = self.value()
        self.skip()
        if self.peek() != ";":
            self.error("缺少 `;`")
        return value

    def value(self):
        self.skip()
        c = self.peek()
        if c == "{":
            return self.object()
        if c == "[":
            return self.array()
        if c in "'\"":
            return self.string()
        if c == "-" or c.isdigit():
            return self.number()
        for word, value in (("true", True), ("false", False), ("null", None)):
            if self.text.startswith(word, self.i):
                self.i += len(word)
                return value
        self.error(f"无法解析 {c!r}")

    def object(self) -> dict:
        self.i += 1   # {
        out: dict = {}
        self.skip()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            self.skip()
            key = self.key()
            self.skip()
            if self.peek() != ":":
                self.error("缺少 `:`")
            self.i += 1
            out[key] = self.value()
            self.skip()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.skip()
                if self.peek() == "}":
                    self.i += 1
                    return out
                continue
            if c == "}":
                self.i += 1
                return out
            self.error("缺少 `,` 或 `}`")

    def key(self) -> str:
        if self.peek() in "'\"":
            return self.string()
        start = self.i
        while self.i < len(self.text) and (self.text[self.i].isalnum() or self.text[self.i] in "_$"):
            self.i += 1
        if self.i == start:
            self.error("缺少键")
        return self.text[start:self.i]

    def array(self) -> list:
        self.i += 1   # [
        out: list = []
        self.skip()
        if self.peek() == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value())
            self.skip()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.skip()
                if self.peek() == "]":
                    self.i += 1
                    return out
                continue
            if c == "]":
                self.i += 1
                return out
            self.error("缺少 `,` 或 `]`")

    def string(self) -> str:
        quote = self.text[self.i]
        self.i += 1
        out: list[str] = []
        while self.i < len(self.text):
            c = self.text[self.i]
            if c == "\\":
                self.i += 1
                if self.i >= len(self.text):
                    self.error("字符串未结束")
                e = self.text[self.i]
                simple = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0",
                          "\\": "\\", "'": "'", '"': '"'}
                if e in simple:
                    out.append(simple[e])
                    self.i += 1
                elif e in ("x", "u"):
                    size = 2 if e == "x" else 4
                    digits = self.text[self.i + 1:self.i + 1 + size]
                    if len(digits) != size or not all(ch in "0123456789abcdefABCDEF" for ch in digits):
                        self.error(f"坏的 \\{e} 转义")
                    out.append(chr(int(digits, 16)))
                    self.i += 1 + size
                else:
                    out.append(e)
                    self.i += 1
                continue
            if c == quote:
                self.i += 1
                return "".join(out)
            if c == "\n":
                self.error("字符串未结束")
            out.append(c)
            self.i += 1
        self.error("字符串未结束")

    def number(self):
        match = re.match(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", self.text[self.i:])
        if not match:
            self.error("缺少数字")
        token = match.group(0)
        self.i += len(token)
        return int(token) if re.fullmatch(r"-?\d+", token) else float(token)


def _find_const(text: str, name: str):
    """The value of `const NAME = ...;`, found outside strings."""
    i = 0
    quote = None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            i += 1
            continue
        if text.startswith("const", i) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_$")):
            j = i + 5
            while j < len(text) and text[j].isspace():
                j += 1
            start = j
            while j < len(text) and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            if text[start:j] == name:
                k = j
                while k < len(text) and text[k].isspace():
                    k += 1
                if k < len(text) and text[k] == "=":
                    return _LiteralParser(text, k + 1).statement_value()
            i = max(j, i + 1)
            continue
        i += 1
    _fail(f"pointer.js 里找不到 const {name} = ...;")


def parse_pointer_text(text: str) -> dict:
    """The source pointer.js's constants (COLOURS, PICTURE, SPLIT, SKIN, EYES, LIDS, SHY, FACES)."""
    text = _strip_comments(text)
    values = {name: _find_const(text, name)
              for name in ("COLOURS", "PICTURE", "SPLIT", "SKIN", "EYES", "LIDS", "SHY", "FACES")}
    return validate_source({
        "schemaVersion": SCHEMA_VERSION,
        "width": WIDTH,
        "height": HEIGHT,
        "colours": values["COLOURS"],
        "picture": values["PICTURE"],
        "split": values["SPLIT"],
        "skin": values["SKIN"],
        "eyes": values["EYES"],
        "lids": values["LIDS"],
        "shy": values["SHY"],
        "faces": values["FACES"],
        "layers": {"shima": None, "adachi": None},
    })


def parse_pointer_js(path=POINTER_PATH) -> dict:
    """Read a pointer.js and return the art it holds, in source form.

    A pointer.js that consumes window.HOME_POINTER_ART is read from the source beside it
    (pointer-art.source.json, else pointer-art.js), so the workbench can seed after the split.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"读不到 {path}：{exc}")
    if "window.HOME_POINTER_ART" in text and not re.search(r"const\s+PICTURE\s*=\s*\[", text):
        source = path.with_name("pointer-art.source.json")
        if source.is_file():
            return load_source(source)
        generated = path.with_name("pointer-art.js")
        if generated.is_file():
            return load_generated(generated)
        _fail(f"{path} 消费 window.HOME_POINTER_ART，但同目录没有 pointer-art.source.json")
    return parse_pointer_text(text)


def _derive_one(picture: list[str], split: list[int], role: str) -> list[str]:
    rows = []
    for line, cut in zip(picture, split):
        row = list(line)
        if role == "shima":
            # The two squares at the cut copy the square before it, so that neither leaves a hole
            # when the other bobs (pointer.js's layer).
            for x in range(cut, len(row)):
                row[x] = row[cut - 1] if x < cut + 2 else "."
        else:
            for x in range(cut):
                row[x] = "."
        rows.append("".join(row))
    return rows


def derive_layers(picture, split, width: int = WIDTH, height: int = HEIGHT) -> dict[str, list[str]]:
    """The two layers from a full picture and the split, exactly as pointer.js derives them."""
    if not isinstance(picture, list) or len(picture) != height:
        _fail(f"picture 必须是 {height} 行")
    if not all(isinstance(line, str) and len(line) == width for line in picture):
        _fail(f"picture 每行必须是 {width} 个字符")
    if not isinstance(split, list) or len(split) != height:
        _fail(f"split 必须是 {height} 个整数")
    if not all(_is_int(cut) and 1 <= cut <= width for cut in split):
        _fail(f"split 的每一项必须是 1..{width} 的整数")
    return {role: _derive_one(picture, split, role) for role in ROLES}


def _apply_expression(rows: list[list[str]], eye_pairs, mask: list[str], skin: str) -> list[list[str]]:
    # The first eye takes the mask as drawn, the second its mirror (pointer.js's `side` is the eye).
    for side, [ex, ey] in enumerate(eye_pairs):
        for y, line in enumerate(mask):
            for x, ch in enumerate(line):
                rows[ey + y][ex + (4 - x if side else x)] = skin if ch == "." else ch
    return rows


def layer_rows(source, role: str, expression: str = "open") -> list[list[str]]:
    """One role's rows at an expression: its own layer when it has one, else derived from picture."""
    source = validate_source(source)
    if role not in ROLES:
        _fail(f"角色必须是 {'/'.join(ROLES)}")
    if expression not in EXPRESSIONS:
        _fail(f"表情必须是 {'/'.join(EXPRESSIONS)}")
    base = source["layers"][role]
    if base is None:
        rows = [list(line) for line in _derive_one(source["picture"], source["split"], role)]
    else:
        rows = [list(line) for line in base]
    if expression != "open":
        _apply_expression(rows, source["eyes"][role], source["lids"][expression], source["skin"])
    return rows


def compose_layers(layers: dict[str, list[list[str]]], width: int = WIDTH, height: int = HEIGHT) -> list[str]:
    """Adachi in front of Shimamura: her squares cover, clear ones let Shimamura through."""
    out = []
    for y in range(height):
        row = []
        for x in range(width):
            ch = layers["adachi"][y][x]
            row.append(layers["shima"][y][x] if ch == "." else ch)
        out.append("".join(row))
    return out


def compose(source, expression: str = "open") -> list[str]:
    """The full picture with a face: both roles layered, Adachi in front."""
    source = validate_source(source)
    layers = {role: layer_rows(source, role, expression) for role in ROLES}
    return compose_layers(layers, source["width"], source["height"])


def _paint(image: Image.Image, rows, colours: dict[str, str], shy: bool = False, shy_colour: str = "#ecb1a5") -> None:
    pixels = image.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            value = colours[ch]
            if shy and ch == "G":
                value = shy_colour
            r, g, b = hex_to_rgb(value)
            pixels[x, y] = (r, g, b, 255)


def render_full(source, expression: str = "open", shy: bool = False) -> Image.Image:
    """The full 46x27 picture as an RGBA image, a square to a pixel."""
    source = validate_source(source)
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    _paint(image, layer_rows(source, "shima", expression), source["colours"])
    _paint(image, layer_rows(source, "adachi", expression), source["colours"], shy=shy, shy_colour=source["shy"])
    return image


def render_role(source, role: str, expression: str = "open", shy: bool = False) -> Image.Image:
    """One role's 46x27 slice as an RGBA image, everything else transparent."""
    source = validate_source(source)
    if role not in ROLES:
        _fail(f"角色必须是 {'/'.join(ROLES)}")
    if expression not in EXPRESSIONS:
        _fail(f"表情必须是 {'/'.join(EXPRESSIONS)}")
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    _paint(image, layer_rows(source, role, expression), source["colours"], shy=shy and role == "adachi",
           shy_colour=source["shy"])
    return image


def render_preview(image: Image.Image, scale: int = 10) -> Image.Image:
    """The image enlarged by whole squares, nearest neighbour, for looking at it (not for the site)."""
    if not _is_int(scale) or scale < 1:
        _fail("放大倍数必须是正整数")
    return image.resize((image.width * scale, image.height * scale), Image.NEAREST)


def _image_from(image) -> Image.Image:
    """A PIL image or PNG bytes as RGBA; the image must carry an alpha channel."""
    if isinstance(image, Image.Image):
        if image.mode not in ("RGBA", "LA", "PA") and not (image.mode == "P" and "transparency" in image.info):
            _fail("图像必须保留透明通道（RGBA）")
        return image.convert("RGBA")
    if not isinstance(image, (bytes, bytearray)) or not image:
        _fail("需要 PIL 图像或 PNG 字节")
    try:
        with Image.open(io.BytesIO(bytes(image))) as probe:
            if probe.format != "PNG":
                _fail("不是实际 PNG")
            if getattr(probe, "n_frames", 1) != 1:
                _fail("只接受单帧 PNG")
            mode = probe.mode
            info = dict(probe.info)
            probe.load()
            rgba = probe.convert("RGBA")
    except PointerArtError:
        raise
    except Exception as exc:
        _fail(f"PNG 无法完整解码：{exc}")
    if mode not in ("RGBA", "LA", "PA") and not (mode == "P" and "transparency" in info):
        _fail("图像必须保留透明通道（RGBA）")
    return rgba


def rows_from_image(image, colours: dict[str, str]) -> list[str]:
    """Read a 46x27 RGBA image (or PNG bytes) into rows; alpha must be 0 or 255."""
    rgba = _image_from(image)
    if rgba.size != (WIDTH, HEIGHT):
        _fail(f"图像必须是 {WIDTH}×{HEIGHT}，实际 {rgba.width}×{rgba.height}")
    pixels = rgba.load()
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            r, g, b, a = pixels[x, y]
            if a == 0:
                row.append(".")
            elif a == 255:
                row.append(assign_palette(colours, (r, g, b)))
            else:
                _fail(f"像素 ({x}, {y}) 的 alpha 是 {a}，只接受 0 或 255")
        rows.append("".join(row))
    return rows


def source_from_png(image, template) -> dict:
    """A source from a 46x27 RGBA image or PNG bytes, keeping the template's split, eyes, masks and faces."""
    template = validate_source(template)
    colours = dict(template["colours"])
    picture = rows_from_image(image, colours)
    source = {
        "schemaVersion": SCHEMA_VERSION,
        "width": WIDTH,
        "height": HEIGHT,
        "colours": colours,
        "picture": picture,
        "split": list(template["split"]),
        "skin": template["skin"],
        "eyes": {role: [list(pair) for pair in template["eyes"][role]] for role in ROLES},
        "lids": {name: list(template["lids"][name]) for name in LID_NAMES},
        "shy": template["shy"],
        "faces": {name: list(template["faces"][name]) for name in FACE_NAMES},
        "layers": {"shima": None, "adachi": None},
    }
    return validate_source(source)


def build_runtime(pointer_text: str | None = None) -> str:
    """The formal pointer.js runtime, checked to consume window.HOME_POINTER_ART.

    After the art was split out, pointer.js is the runtime itself; there is no runtime text transform. This
    returns its text after checking the three things a preview must keep: the global, figure(), and no picture
    constants left in it.
    """
    if pointer_text is None:
        try:
            pointer_text = POINTER_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"读不到 {POINTER_PATH}：{exc}")
    if "window.HOME_POINTER_ART" not in pointer_text:
        _fail("pointer.js 没有消费 window.HOME_POINTER_ART")
    if "function figure()" not in pointer_text:
        _fail("pointer.js 缺少 function figure()")
    if re.search(r"const\s+PICTURE\s*=\s*\[", pointer_text):
        _fail("pointer.js 仍内嵌 PICTURE")
    return pointer_text
