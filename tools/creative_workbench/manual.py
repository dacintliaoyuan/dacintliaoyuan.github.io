"""Manual round trips: pointer sources, Piskel projects, and PNG imports/exports."""

from __future__ import annotations

import base64
import binascii
import copy
import io
import json
import shutil
from pathlib import Path

from PIL import Image

from . import (
    EDITORS,
    FEATHER_SIZE,
    POINTER_EXPRESSIONS,
    POINTER_HEIGHT,
    POINTER_LAYER_ROLES,
    POINTER_ROLES,
    POINTER_WIDTH,
    ROOT,
    CreativeError,
    PointerArtError,
    digest_bytes,
    new_id,
    now,
    relative_path,
    write_bytes_atomic,
    write_json_atomic,
)
from . import state as state_module

BASE64_PREFIX = "data:image/png;base64,"


def _art():
    """The shared pointer art tool; it owns validation, composition, and rendering."""
    try:
        import pointer_art
    except ImportError as error:  # pragma: no cover - shipped beside the package
        raise CreativeError("指针图样工具不可用: tools/pointer_art.py") from error
    return pointer_art


def validate_pointer_source(source):
    module = _art()
    try:
        return module.validate_source(source)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def load_pointer_source(path):
    module = _art()
    try:
        return module.load_source(path)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def parse_pointer_js(text):
    module = _art()
    try:
        return module.parse_pointer_text(text)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def derive_layers(source):
    module = _art()
    try:
        return module.derive_layers(source["picture"], source["split"])
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def materialized_layers(source):
    derived = derive_layers(source)
    layers = source.get("layers")
    if layers is None:
        return derived
    return {role: (list(layers[role]) if layers.get(role) is not None else derived[role])
            for role in POINTER_LAYER_ROLES}


def compose_rows(shima, adachi):
    module = _art()
    try:
        return module.compose_layers({"shima": shima, "adachi": adachi})
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def _rgb(value):
    text = value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def render_rows(source, rows, shy=False):
    """Paint rows as a 46×27 RGBA image, a square to a pixel."""
    image = Image.new("RGBA", (POINTER_WIDTH, POINTER_HEIGHT), (0, 0, 0, 0))
    pixels = image.load()
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == ".":
                continue
            value = source["shy"] if shy and char == "G" else source["colours"][char]
            red, green, blue = _rgb(value)
            pixels[x, y] = (red, green, blue, 255)
    return image


def render_pointer(source, role=None, expression="open", shy=False):
    """Render the full picture, or one role slice, as an RGBA image."""
    module = _art()
    try:
        if role is None:
            return module.render_full(source, expression, shy)
        return module.render_role(source, role, expression, shy)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def _decode_png(data):
    """Return (RGBA image, has alpha channel, has transparent pixels)."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PointerArtError("PNG 为空")
    try:
        with Image.open(io.BytesIO(bytes(data))) as probe:
            if probe.format != "PNG":
                raise PointerArtError("不是实际 PNG")
            if getattr(probe, "n_frames", 1) != 1:
                raise PointerArtError("只接受单帧 PNG")
            has_alpha = "A" in probe.mode or (probe.mode == "P"
                                              and "transparency" in probe.info)
            probe.verify()
        with Image.open(io.BytesIO(bytes(data))) as image:
            image.load()
            rgba = image.convert("RGBA")
    except PointerArtError:
        raise
    except Exception as error:
        raise PointerArtError(f"PNG 无法完整解码: {error}") from error
    transparent = rgba.getchannel("A").getextrema()[0] < 255
    return rgba, has_alpha, transparent


def _decode_image(data, label="图片"):
    """Decode a single-frame image of any supported format to RGBA."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise CreativeError(f"{label}为空")
    try:
        with Image.open(io.BytesIO(bytes(data))) as probe:
            if getattr(probe, "n_frames", 1) != 1:
                raise CreativeError(f"{label}必须是单帧图片")
            image_format = probe.format
            has_alpha = "A" in probe.mode or (probe.mode == "P"
                                              and "transparency" in probe.info)
            probe.verify()
        with Image.open(io.BytesIO(bytes(data))) as image:
            image.load()
            rgba = image.convert("RGBA")
    except CreativeError:
        raise
    except Exception as error:
        raise CreativeError(f"{label}无法完整解码: {error}") from error
    if image_format not in ("PNG", "WEBP", "JPEG"):
        raise CreativeError(f"不支持的图片格式: {image_format or '未知'}")
    transparent = rgba.getchannel("A").getextrema()[0] < 255
    return rgba, image_format, has_alpha, transparent


def _rows_from_rgba(image, palette):
    module = _art()
    try:
        return module.rows_from_image(image, palette)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


def pointer_source_from_png(data, template):
    """Derive a pointer source from a 46×27 RGBA PNG and a template."""
    module = _art()
    image, has_alpha, transparent = _decode_png(data)
    if image.size != (POINTER_WIDTH, POINTER_HEIGHT):
        raise PointerArtError(
            f"指针图片必须是 46×27；实际 {image.width}×{image.height}")
    if not has_alpha:
        raise PointerArtError("指针图片必须保留透明通道")
    try:
        return module.source_from_png(image, template)
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error


# --- versions -------------------------------------------------------------

def _unique_version(project):
    existing = {version["versionId"] for version in project["versions"]}
    for _ in range(64):
        candidate = new_id("ver")
        if candidate not in existing:
            return candidate
    raise CreativeError("无法分配版本 id")


def _canonical(document):
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def save_pointer_version(store, project, source, parent_version_id=None,
                          source_kind="original", manual=None, note=None):
    """Write an immutable pointer version (JSON plus rendered preview PNG)."""
    source = validate_pointer_source(source)
    version_id = _unique_version(project)
    project_id = project["projectId"]
    relative = f"projects/{project_id}/versions/{version_id}.json"
    preview_relative = f"projects/{project_id}/versions/{version_id}.png"
    payload = _canonical({"schemaVersion": 1, "pointerSource": source})
    written = []
    try:
        write_bytes_atomic(store.root / relative, payload)
        written.append(store.root / relative)
        write_bytes_atomic(store.root / preview_relative, png_bytes(render_pointer(source)))
        written.append(store.root / preview_relative)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {
        "versionId": version_id,
        "parentVersionId": parent_version_id,
        "source": source_kind,
        "path": relative,
        "sha256": digest_bytes(payload),
        "size": [POINTER_WIDTH, POINTER_HEIGHT],
        "format": "JSON",
        "hasAlpha": True,
        "jobId": None,
        "pointerSource": source,
        "previewPath": preview_relative,
        "manual": manual,
        "paintedFill": False,
        "createdAt": now(),
        "note": note,
    }


def _append(store, project_id, version):
    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；不能新增版本")
        project["versions"].append(version)
        if project["status"] == "review":
            state_module.touch(project)
        else:
            state_module.transition_project(project, "review")
        return version

    return store.mutate(add)


def _append_version(store, project_id, version):
    try:
        return _append(store, project_id, version)
    except Exception:
        (store.root / version["path"]).unlink(missing_ok=True)
        if version.get("previewPath"):
            (store.root / version["previewPath"]).unlink(missing_ok=True)
        raise


# --- export ---------------------------------------------------------------

def _scope(project):
    active = [item for item in project.get("confirmations") or []
              if item.get("status") == "active"]
    if not active:
        return [], []
    scope = active[-1].get("scope") or {}
    return (list(scope.get("allowedChanges") or []),
            list(scope.get("preserved") or []))


def _readme(project, version, role, expression, editor, allowed, preserved):
    size = version.get("size") or [POINTER_WIDTH, POINTER_HEIGHT]
    lines = [
        "手改导出说明（creative workbench）",
        "",
        f"- 项目：{project['projectId']}（{project['name']}）",
        f"- 版本：{version['versionId']}，尺寸 {size[0]}×{size[1]}，来源 {version['source']}",
        f"- 角色：{role}",
        f"- 表情：{expression}",
        f"- 编辑器：{editor}",
        "",
        "步骤",
        "1. 在 Piskel 打开 sprite.piskel（两层：shima、adachi，各一帧 46×27）；"
        "或用像素编辑器打开 source.png（整图）。",
        f"2. 只改允许的范围：{'、'.join(allowed) or '（未确认范围）'}；"
        f"保留：{'、'.join(preserved) or '（未确认保留项）'}。",
        "3. 不要改画布尺寸（46×27）；透明处保持全透明，不要用半透明。",
        "4. 改完导出 PNG，保持 46×27；不要放大或缩小。",
        "5. 回到工作台导入：整图改动用 role=full；只改一个人用 role=shima 或 "
        "role=adachi，角色切片之外必须透明。",
        "6. 导入会生成新版本，不会自动采用；确认后再点“采用”。",
        "",
        "注意",
        "- 不要覆盖 source.png 或正式站点；工作台会为新版本单独保存文件。",
        "- 导入不接受放大图；需要放大编辑时请在工作台外自行放大，再缩回 46×27。",
        "",
    ]
    return "\n".join(lines)


def _layer_document(project, source, layers):
    def layer(name, rows):
        payload = png_bytes(render_rows(source, rows))
        encoded = base64.b64encode(payload).decode("ascii")
        return json.dumps({
            "name": name,
            "opacity": 1,
            "frameCount": 1,
            "chunks": [{"layout": [[0]], "base64PNG": BASE64_PREFIX + encoded}],
        }, ensure_ascii=False, separators=(",", ":"))
    return {
        "modelVersion": 2,
        "piskel": {
            "name": f"pointer-{project['projectId']}",
            "description": "creative workbench manual export",
            "fps": 12,
            "height": POINTER_HEIGHT,
            "width": POINTER_WIDTH,
            "layers": [layer("shima", layers["shima"]), layer("adachi", layers["adachi"])],
        },
    }


def export_manual(store, project_id, version_id, role="full", expression="open",
                  editor="piskel"):
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能导出手改文件")
    version = state_module.find_version(project, version_id)
    pointer = project["objectKind"] == "pointer"
    if role not in POINTER_ROLES:
        raise CreativeError(f"角色必须是 shima / adachi / full；实际 {role}")
    if expression not in POINTER_EXPRESSIONS:
        raise CreativeError(f"表情必须是 open / shut / happy / squint；实际 {expression}")
    if editor not in EDITORS:
        raise CreativeError(f"编辑器必须是 piskel 或 krita；实际 {editor}")
    allowed, preserved = _scope(project)
    export_id = new_id("mx")
    relative = f"projects/{project_id}/manual/{export_id}"
    directory = store.path_for(relative)
    directory.mkdir(parents=True, exist_ok=False)
    files = []
    try:
        if pointer:
            if version.get("format") != "JSON" or not version.get("pointerSource"):
                raise CreativeError("指针版本缺少 pointerSource；不能手改导出")
            if expression != "open":
                raise CreativeError("指针导出使用 open；表情由 lids 生成")
            source = version["pointerSource"]
            layers = materialized_layers(source)
            write_bytes_atomic(directory / "source.png", png_bytes(render_pointer(source)))
            files.append("source.png")
            write_bytes_atomic(directory / "shima.png",
                                png_bytes(render_rows(source, layers["shima"])))
            files.append("shima.png")
            write_bytes_atomic(directory / "adachi.png",
                                png_bytes(render_rows(source, layers["adachi"])))
            files.append("adachi.png")
            write_json_atomic(directory / "source.json", {
                "schemaVersion": 1,
                "role": role,
                "expression": expression,
                "pointerSource": source,
            })
            files.append("source.json")
            write_json_atomic(directory / "sprite.piskel",
                                _layer_document(project, source, layers))
            files.append("sprite.piskel")
        else:
            if role != "full":
                raise CreativeError("非指针项目只能用 role=full 导出")
            if version.get("format") != "PNG":
                raise CreativeError("版本必须是 PNG 才能手改导出")
            payload = (store.root / version["path"]).read_bytes()
            write_bytes_atomic(directory / "source.png", payload)
            files.append("source.png")
            write_json_atomic(directory / "source.json", {
                "schemaVersion": 1,
                "versionId": version["versionId"],
                "sha256": version["sha256"],
                "size": version["size"],
                "format": version["format"],
            })
            files.append("source.json")
        write_json_atomic(directory / "guide.json", {
            "schemaVersion": 1,
            "projectId": project_id,
            "versionId": version_id,
            "size": list(version["size"]),
            "scale": 1,
            "role": role,
            "expression": expression,
            "canvasOrigin": [0, 0],
            "allowedChanges": allowed,
            "preserved": preserved,
            "editor": editor,
        })
        files.append("guide.json")
        (directory / "README.txt").write_text(
            _readme(project, version, role, expression, editor, allowed, preserved),
            encoding="utf-8")
        files.append("README.txt")
        export = {
            "exportId": export_id,
            "projectId": project_id,
            "versionId": version_id,
            "role": role,
            "expression": expression,
            "editor": editor,
            "path": relative,
            "files": files,
            "piskelVerified": None,
            "createdAt": now(),
        }
        write_json_atomic(directory / "export.json", export)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；不能导出手改文件")
        project["manualExports"].append(export)
        state_module.touch(project)
        return export

    return store.mutate(add)


# --- import ---------------------------------------------------------------

def _import_pointer(store, project, parent, data, role, expression, editor, note):
    if role not in POINTER_ROLES:
        raise CreativeError(f"角色必须是 shima / adachi / full；实际 {role}")
    if expression not in POINTER_EXPRESSIONS:
        raise CreativeError(f"表情必须是 open / shut / happy / squint；实际 {expression}")
    parent_source = parent.get("pointerSource")
    if not isinstance(parent_source, dict):
        raise CreativeError("父版本缺少指针数据；不能手改导入")
    image, has_alpha, transparent = _decode_png(data)
    if image.size != (POINTER_WIDTH, POINTER_HEIGHT):
        raise CreativeError("指针图片必须是 46×27；不得拉伸")
    if not has_alpha:
        raise CreativeError("透明通道必须保留")
    if not transparent:
        raise CreativeError("指针图样必须至少有一个透明像素")
    module = _art()
    try:
        if role == "full":
            source = module.source_from_png(image, parent_source)
        else:
            palette = dict(parent_source["colours"])
            rows = module.rows_from_image(image, palette)
            base = materialized_layers(parent_source)
            layer = base[role]
            for y in range(POINTER_HEIGHT):
                for x in range(POINTER_WIDTH):
                    if layer[y][x] == "." and rows[y][x] != ".":
                        raise CreativeError("角色切片之外有像素；请用该角色切片或 role=full")
            layers = {"shima": list(base["shima"]), "adachi": list(base["adachi"])}
            layers[role] = rows
            picture = module.compose_layers(layers)
            source = dict(parent_source)
            source.update({"colours": palette, "picture": picture, "layers": layers})
    except module.PointerArtError as error:
        raise PointerArtError(str(error)) from error
    version = save_pointer_version(
        store, project, source, parent["versionId"],
        source_kind="manual-piskel" if editor == "piskel" else "manual-krita",
        manual={"role": role, "expression": expression, "editor": editor,
                "note": note or "", "parentVersionId": parent["versionId"]},
        note=note)
    return _append_version(store, project["projectId"], version)


def _import_image(store, project, parent, data, role, expression, editor, note):
    if role != "full":
        raise CreativeError("非指针项目只能用 role=full 导入")
    if expression not in POINTER_EXPRESSIONS:
        raise CreativeError(f"表情必须是 open / shut / happy / squint；实际 {expression}")
    image, has_alpha, transparent = _decode_png(data)
    expected = list(parent.get("size") or [])
    actual = [image.width, image.height]
    if actual != expected:
        raise CreativeError(
            f"尺寸 {actual[0]}×{actual[1]} 与父版本 "
            f"{expected[0] if expected else '?'}×{expected[1] if len(expected) > 1 else '?'}"
            " 不一致；不得拉伸")
    if not has_alpha:
        raise CreativeError("透明通道必须保留")
    version_id = _unique_version(project)
    relative = f"projects/{project['projectId']}/versions/{version_id}.png"
    write_bytes_atomic(store.root / relative, bytes(data))
    version = {
        "versionId": version_id,
        "parentVersionId": parent["versionId"],
        "source": "manual-piskel" if editor == "piskel" else "manual-krita",
        "path": relative,
        "sha256": digest_bytes(bytes(data)),
        "size": actual,
        "format": "PNG",
        "hasAlpha": has_alpha,
        "jobId": None,
        "pointerSource": None,
        "previewPath": None,
        "manual": {"role": role, "expression": expression, "editor": editor,
                    "note": note or "", "parentVersionId": parent["versionId"]},
        "paintedFill": False,
        "createdAt": now(),
        "note": note,
    }
    return _append_version(store, project["projectId"], version)


def import_manual(store, project_id, parent_version_id, data, role="full",
                    expression="open", editor="piskel", note=None):
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能导入手改结果")
    parent = state_module.find_version(project, parent_version_id)
    if editor not in EDITORS:
        raise CreativeError(f"编辑器必须是 piskel 或 krita；实际 {editor}")
    if project["objectKind"] == "pointer":
        return _import_pointer(store, project, parent, data, role, expression, editor, note)
    return _import_image(store, project, parent, data, role, expression, editor, note)


def _piskel_layers(piskel):
    if not isinstance(piskel, dict):
        raise CreativeError("Piskel 工程必须是 JSON 对象")
    if "modelVersion" in piskel:
        model_version = piskel.get("modelVersion")
        body = piskel.get("piskel")
    else:
        model_version = 2
        body = piskel
    if model_version not in (1, 2):
        raise CreativeError("只支持 Piskel modelVersion 1 或 2")
    if not isinstance(body, dict):
        raise CreativeError("Piskel 工程缺少 piskel 对象")
    if body.get("width") != POINTER_WIDTH or body.get("height") != POINTER_HEIGHT:
        raise CreativeError("Piskel 工程必须是 46×27")
    layers = body.get("layers")
    if not isinstance(layers, list) or not layers:
        raise CreativeError("Piskel 工程没有图层")
    result = []
    for index, layer in enumerate(layers):
        if isinstance(layer, str):
            try:
                layer = json.loads(layer)
            except json.JSONDecodeError as error:
                raise CreativeError(f"Piskel 图层 {index} 无法解析: {error}") from error
        if not isinstance(layer, dict):
            raise CreativeError(f"Piskel 图层 {index} 不合法")
        if layer.get("frameCount") != 1:
            raise CreativeError("只支持单帧单块 Piskel 工程")
        chunks = layer.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise CreativeError(f"Piskel 图层 {index} 没有内容块")
        chunk = chunks[0]
        if not isinstance(chunk, dict) or chunk.get("layout") != [[0]]:
            raise CreativeError("只支持单帧单块 Piskel 工程")
        encoded = chunk.get("base64PNG")
        if not isinstance(encoded, str) or not encoded.startswith(BASE64_PREFIX):
            raise CreativeError(f"Piskel 图层 {index} 缺少 base64PNG")
        try:
            payload = base64.b64decode(encoded[len(BASE64_PREFIX):], validate=True)
        except (binascii.Error, ValueError) as error:
            raise CreativeError(f"Piskel 图层 {index} base64 解码失败: {error}") from error
        image, has_alpha, transparent = _decode_png(payload)
        if image.size != (POINTER_WIDTH, POINTER_HEIGHT):
            raise CreativeError(f"Piskel 图层 {index} 必须是 46×27")
        result.append((layer.get("name") or f"layer-{index}", image))
    return result


def import_piskel(store, project_id, parent_version_id, piskel, role="full",
                   expression="open", editor="piskel", note=None):
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能导入 Piskel 工程")
    if project["objectKind"] != "pointer":
        raise CreativeError("只有指针项目可以导入 Piskel 工程")
    parent = state_module.find_version(project, parent_version_id)
    if parent.get("format") != "JSON" or not parent.get("pointerSource"):
        raise CreativeError("父版本缺少指针数据；不能导入 Piskel 工程")
    if role not in POINTER_ROLES:
        raise CreativeError(f"角色必须是 shima / adachi / full；实际 {role}")
    if expression not in POINTER_EXPRESSIONS:
        raise CreativeError(f"表情必须是 open / shut / happy / squint；实际 {expression}")
    if editor not in EDITORS:
        raise CreativeError(f"编辑器必须是 piskel 或 krita；实际 {editor}")
    layers = _piskel_layers(piskel)
    if role == "full":
        canvas = Image.new("RGBA", (POINTER_WIDTH, POINTER_HEIGHT), (0, 0, 0, 0))
        for _, image in layers:
            canvas.alpha_composite(image)
        composed = canvas
    else:
        selected = [image for name, image in layers if name == role]
        if not selected:
            raise CreativeError(f"Piskel 工程缺少图层: {role}")
        composed = selected[0]
    return _import_pointer(store, project, parent, png_bytes(composed),
                            role, expression, editor, note)


# --- pointer seed and lids --------------------------------------------------

def _site_template(site_root):
    site_root = Path(site_root).resolve()
    source = site_root / "pointer-art.source.json"
    if source.is_file():
        try:
            return load_pointer_source(source)
        except PointerArtError:
            pass
    script = site_root / "pointer.js"
    if script.is_file():
        try:
            return parse_pointer_js(script.read_text(encoding="utf-8"))
        except PointerArtError:
            return None
    return None


def _read_source_bytes(store, site_root, source_path):
    text = relative_path(source_path, "指针来源")
    for root in (Path(site_root).resolve(), store.root):
        candidate = (root / text).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    raise CreativeError(f"找不到指针来源: {source_path}", status=404)


def seed_pointer(store, project_id, source_path=None, site_root=None):
    """Create the initial pointer version without writing the formal site."""
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能建立初始版本")
    if project["objectKind"] != "pointer":
        raise CreativeError("只有指针项目可以建立指针初始版本")
    site_root = Path(site_root or ROOT / "site").resolve()
    template = _site_template(site_root)
    if template is None:
        raise CreativeError("找不到 site/pointer-art.source.json 或 site/pointer.js；"
                            "请先建立指针来源")
    if source_path:
        path = _read_source_bytes(store, site_root, source_path)
        if path.suffix.lower() == ".json":
            source = load_pointer_source(path)
        else:
            source = pointer_source_from_png(path.read_bytes(), template)
    else:
        source = validate_pointer_source(copy.deepcopy(template))
    version = save_pointer_version(store, project, source, parent_version_id=None,
                                    source_kind="original", manual=None,
                                    note="初始指针版本")
    return _append_version(store, project_id, version)


def _image_reference(project, reference_id=None):
    """Return the requested local image reference, or the first one."""
    references = [item for item in project.get("references") or []
                  if item.get("kind") in ("image", "film-frame")
                  and item.get("path") and not item.get("missing")]
    if reference_id:
        reference = state_module.get_reference(project, reference_id)
        if reference is None:
            raise CreativeError(f"找不到参考: {reference_id}", status=404)
        if (reference.get("kind") not in ("image", "film-frame")
                or not reference.get("path")):
            raise CreativeError("参考没有本地图片；不能建立初始版本")
        if reference.get("missing"):
            raise CreativeError("参考文件缺失；请先恢复参考")
        return reference
    if not references:
        raise CreativeError("没有本地图片参考；请先加参考")
    return references[0]


def seed_reference(store, project_id, reference_id, note=None):
    """Create the first image version from a local reference.

    The reference is copied into an immutable PNG version so a later edit/inpaint
    job has a real input.  The formal site and the selected version are untouched.
    """
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能建立初始版本")
    kind = project["objectKind"]
    if kind == "pointer":
        raise CreativeError("指针项目请用指针初始版本")
    if kind == "bird":
        raise CreativeError("青鸟尚未接入正式主页；本轮不建立初始版本")
    reference = _image_reference(project, reference_id)
    data = (store.root / reference["path"]).read_bytes()
    if digest_bytes(data) != reference.get("sha256"):
        raise CreativeError("参考文件已变化；请先重新确认参考")
    label = f"参考 {reference['referenceId']}"
    rgba, image_format, has_alpha, transparent = _decode_image(data, label)
    size = [rgba.width, rgba.height]
    if kind == "feather":
        if tuple(size) != FEATHER_SIZE:
            raise CreativeError(
                f"羽毛初始版本必须是 {FEATHER_SIZE[0]}×{FEATHER_SIZE[1]}；"
                f"实际 {size[0]}×{size[1]}")
        if not has_alpha:
            raise CreativeError("羽毛初始版本必须保留透明通道")
        if not transparent:
            raise CreativeError("羽毛初始版本必须至少有一个透明像素")
    version_id = _unique_version(project)
    relative = f"projects/{project_id}/versions/{version_id}.png"
    payload = png_bytes(rgba)
    write_bytes_atomic(store.root / relative, payload)
    version = {
        "versionId": version_id,
        "parentVersionId": None,
        "source": "original",
        "path": relative,
        "sha256": digest_bytes(payload),
        "size": size,
        "format": "PNG",
        "hasAlpha": has_alpha,
        "jobId": None,
        "pointerSource": None,
        "previewPath": None,
        "manual": None,
        "paintedFill": False,
        "createdAt": now(),
        "note": note or f"从{label}建立初始版本（{image_format} 转 PNG）",
    }
    return _append_version(store, project_id, version)


def update_lids(store, project_id, expression, rows, note=None):
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能修改眼睛遮罩")
    if project["objectKind"] != "pointer":
        raise CreativeError("只有指针项目有眼睛遮罩")
    if expression not in ("shut", "happy", "squint"):
        raise CreativeError("表情只能是 shut / happy / squint；open 表示不覆盖")
    if (not isinstance(rows, list) or len(rows) != 5
            or any(not isinstance(row, str) or len(row) != 5 for row in rows)):
        raise CreativeError("眼睛遮罩必须是 5×5")
    parent = _latest_pointer(project)
    if parent is None:
        raise CreativeError("项目还没有指针版本；请先建立初始版本")
    source = copy.deepcopy(parent["pointerSource"])
    for row in rows:
        for char in row:
            if char != "." and char not in source["colours"]:
                raise CreativeError(f"眼睛遮罩字符不在调色板: {char}")
    source["lids"][expression] = list(rows)
    version = save_pointer_version(
        store, project, source, parent["versionId"], "generated",
        manual={"role": "full", "expression": expression, "editor": "workbench",
                "note": note or "", "parentVersionId": parent["versionId"]},
        note=note)
    return _append_version(store, project_id, version)


def _latest_pointer(project):
    selected = state_module.get_version(project, project.get("selectedVersionId"))
    if selected is not None and selected.get("pointerSource"):
        return selected
    for version in reversed(project.get("versions") or []):
        if version.get("pointerSource"):
            return version
    return None
