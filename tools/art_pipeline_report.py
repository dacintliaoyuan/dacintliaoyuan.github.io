"""Render a local, read-only artwork queue with explicitly exported human decisions."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from PIL import Image, ImageOps

TEMPLATE = Path(__file__).with_name("art_pipeline_review.html")
REPORT_KIND = "art-pipeline-review"
ANALYSIS_LABELS = {"exactDuplicates": "完全重复分组", "similarCandidates": "相似画面提名",
                   "monochromeCandidates": "黑白候选", "lowResolution": "低清候选", "errors": "检查错误"}
DECISIONS = {"pending", "selected", "paused", "excluded"}
PRIORITY = ("adopted", "enhanced", "cropped", "clean", "source", "original")
DECISION_LABELS = {"pending": "待选择", "selected": "已选择", "paused": "暂停", "excluded": "不采用"}
SOURCE_LABELS = {"pending": "未检查", "unchecked": "未检查", "checked": "已检查", "found": "已取得原稿",
                 "acquired": "已取得原稿", "downloaded": "已取得原稿", "blocked": "访问受限",
                 "restricted": "访问受限", "small-only": "只有小图", "preview-only": "只有预览",
                 "not-found": "暂未找到", "unavailable": "暂不可用", "not_checked": "未检查",
                 "access_restricted": "访问受限", "only_preview": "只有预览", "original_found": "已取得原稿",
                 "no_match_found": "暂未找到"}


def _digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _identity(value, label):
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{label} 必须是非空文本，不能包含控制字符或首尾空白")
    return value


def _external(value):
    if not isinstance(value, str) or any(ord(char) < 32 for char in value) or "\\" in value:
        return ""
    try:
        url = urlsplit(value)
        if url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return ""


def _href(path, directory):
    return quote(Path(os.path.relpath(path, directory)).as_posix(), safe="/")


def _artifact(value, library, directory):
    """Expose image URLs only after validating the actual image and its recorded identity."""
    if not isinstance(value, dict):
        raise ValueError("图片记录必须是 JSON 对象")
    relative = value.get("path")
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute() or any(part in {"..", "."} for part in relative.split("/"))):
        raise ValueError("图片路径必须是图库内的相对 POSIX 路径")
    path = (library / relative).resolve()
    if path == library or not path.is_relative_to(library):
        raise ValueError(f"图片路径越出图库: {relative}")
    if path.is_relative_to(directory):
        raise ValueError("报告自己的派生文件不能作为素材输入")
    size = value.get("size")
    checksum = value.get("sha256")
    if (not isinstance(size, list) or len(size) != 2 or any(type(axis) is not int or axis <= 0 for axis in size)
            or not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum)):
        raise ValueError(f"图片缺少有效尺寸或 SHA-256: {relative}")
    result = {"path": relative, "size": list(size), "sha256": checksum, "valid": False,
              "href": "", "thumbHref": "", "warning": ""}
    if not path.is_file():
        result["warning"] = "文件不存在；请恢复原文件或重新处理后再验收。"
        return result, None
    try:
        with Image.open(path) as image:
            actual_size = list(image.size)
            image.verify()
        actual_sha = _digest(path)
    except (OSError, ValueError) as error:
        result["warning"] = f"文件无法作为图片读取：{error}"
        return result, None
    if actual_size != size or actual_sha != checksum:
        result["warning"] = "文件尺寸或 SHA-256 已变化；旧记录失效，请重新登记和验收。"
        return result, None
    result.update(valid=True, href=_href(path, directory))
    return result, path


def _atomic_text(path, value):
    handle, name = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _markdown(report):
    lines = ["# 素材处理与验收报告", "", "本报告不修改素材、处理队列或网站。选择与验收须导出 JSON 后显式导入。", "",
             f"素材 {len(report['items'])} 项；来源覆盖记录 {len(report['sources'])} 项。", "", "## 来源覆盖", ""]
    for source in report["sources"]:
        lines.extend([f"### {source['id']} · {source['title']}", "",
                      f"类别：{source['category']}；状态：{source['statusLabel']}；检查时间：{source['checkedAt'] or '未记录'}", "",
                      f"页面：{source['pageUrl'] or '未提供可用 HTTP(S) 链接'}", "",
                      f"原因／说明：{source['note'] or '未记录'}", "", f"证据：{source['evidence'] or '未记录'}", "",
                      f"关联素材：{'、'.join(source['artworkIds']) or '无'}", ""])
    if "analysis" in report:
        lines.extend(["## 程序检查提名", "", "这些仅供人工选择，不自动排除、采用或验收任何素材。", ""])
        for name, label in ANALYSIS_LABELS.items():
            rows = report["analysis"].get(name, [])
            lines.extend([f"### {label}（{len(rows)}）", ""])
            lines.extend(f"- {_text(row)}" for row in rows)
            lines.append("")
        lines.extend(["检查参数：" + _text(report["analysis"].get("parameters", {})), ""])
    lines.extend(["## 素材任务", ""])
    for item in report["items"]:
        lines.extend([f"### {item['number']} · {item['title']}", "", f"ID：{item['id']}", "",
                      f"选择：{DECISION_LABELS[item['decision']['status']]}；验收：{item['approvalLabel']}", "",
                      f"当前版本：{item['currentVersion'] or '无'}；配方：{item['pipelineKey'] or '未提供'}", ""])
        for name, artifact in item["variants"].items():
            lines.extend([f"- {name}：{artifact['path']} · {'×'.join(map(str, artifact['size']))} · "
                          f"{'校验通过' if artifact['valid'] else artifact['warning']}"])
        lines.extend(["", f"阶段：{_text(item['stages'])}", "", f"最近处理：{_text(item['lastRun'])}", "",
                      f"处理配方：{_text(item['recipe'])}", ""])
    return "\n".join(lines)


def build_report(state: dict, library: Path, directory: Path) -> dict:
    """Create only report-owned derivatives. Do not mutate or save the supplied state."""
    if (not isinstance(state, dict) or type(state.get("schemaVersion")) is not int or state.get("schemaVersion") != 1
            or not isinstance(state.get("sources"), list) or not isinstance(state.get("items"), list)):
        raise ValueError("处理队列必须为 schemaVersion=1，包含 sources 和 items 数组")
    library, directory = Path(library).resolve(), Path(directory).resolve()
    if not library.is_dir() or directory == library:
        raise ValueError("图库必须存在；报告必须写入独立子目录或其他专用目录")
    report = {"schemaVersion": 1, "reportKind": REPORT_KIND, "sources": [], "items": []}
    paths = {}
    artifact_cache = {}
    source_ids, item_ids = set(), set()
    for row in state["sources"]:
        if not isinstance(row, dict):
            raise ValueError("来源覆盖记录必须是 JSON 对象")
        identity = _identity(row.get("id"), "来源 id")
        if identity in source_ids:
            raise ValueError(f"来源 id 重复: {identity}")
        source_ids.add(identity)
        status = _text(row.get("status") or "pending")
        artwork_ids = row.get("artworkIds", [])
        if not isinstance(artwork_ids, list) or any(not isinstance(value, str) for value in artwork_ids):
            raise ValueError("artworkIds 必须是文本数组")
        report["sources"].append({"id": identity, "category": _text(row.get("category")),
                                  "title": _text(row.get("title") or identity), "status": status,
                                  "statusLabel": SOURCE_LABELS.get(status, status), "pageUrl": _external(row.get("pageUrl")),
                                  "checkedAt": _text(row.get("checkedAt")), "note": _text(row.get("note")),
                                  "evidence": _text(row.get("evidence")), "artworkIds": list(artwork_ids)})
    for row in state["items"]:
        if not isinstance(row, dict):
            raise ValueError("素材记录必须是 JSON 对象")
        identity = _identity(row.get("id"), "素材 id")
        if identity in item_ids:
            raise ValueError(f"素材 id 重复: {identity}")
        item_ids.add(identity)
        decision = row.get("decision", {})
        status = decision.get("status", "pending") if isinstance(decision, dict) else None
        if status not in DECISIONS:
            raise ValueError(f"不支持的素材选择状态: {identity}")
        variants = row.get("variants", {})
        if not isinstance(variants, dict):
            raise ValueError("variants 必须是 JSON 对象")
        variant_inputs = {"source": row["source"]} if row.get("source") else {}
        variant_inputs.update(variants)
        checked = {}
        for name, artifact in variant_inputs.items():
            _identity(name, "版本名称")
            cache_key = json.dumps(artifact, sort_keys=True, allow_nan=False)
            if cache_key not in artifact_cache:
                artifact_cache[cache_key] = _artifact(artifact, library, directory)
            checked[name], path = artifact_cache[cache_key]
            if path:
                paths[checked[name]["sha256"]] = path
        current = next((name for name in PRIORITY if name in checked), next(iter(checked), ""))
        current_artifact = checked.get(current)
        key = _text(row.get("pipelineKey"))
        approval = row.get("approval", {})
        valid_approval = (isinstance(approval, dict) and approval.get("status") == "approved" and bool(key)
                          and approval.get("recipeKey") == key and bool(current_artifact and current_artifact["valid"])
                          and approval.get("artifactSha256") == current_artifact["sha256"] and status == "selected")
        label = "已验收" if valid_approval else "待验收"
        if isinstance(approval, dict) and approval.get("status") == "approved" and not valid_approval:
            label = "旧验收已失效"
        last_run = row.get("lastRun", {})
        recipe = row.get("recipe", {})
        processing_ready = (isinstance(recipe, dict) and recipe.get("imported") is True
                            or isinstance(last_run, dict) and last_run.get("status") in {"awaiting_review", "approved"}
                            or valid_approval)
        report["items"].append({"id": identity, "number": _text(row.get("number") or identity),
                                "title": _text(row.get("title") or identity), "artist": _text(row.get("artist") or "画师待核对"),
                                "official": row.get("official") is True, "link": _external(row.get("link")),
                                "sourceLabel": _text(row.get("sourceLabel", "")),
                                "variants": checked, "currentVersion": current, "pipelineKey": key,
                                "decision": {"status": status, "note": _text(decision.get("note") or decision.get("reason"))},
                                "recipe": recipe, "stages": row.get("stages", {}), "lastRun": last_run,
                                "approvalValid": bool(valid_approval), "approvalLabel": label,
                                "canApprove": bool(current_artifact and current_artifact["valid"] and key and processing_ready),
                                "integrated": row.get("integrated", {})})
    report["sourceCounts"] = dict(Counter(source["statusLabel"] for source in report["sources"]))
    report["decisionCounts"] = dict(Counter(item["decision"]["status"] for item in report["items"]))
    report["reportId"] = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    if "analysis" in state:
        analysis = state["analysis"]
        if (not isinstance(analysis, dict)
                or any(not isinstance(analysis.get(name, []), list) for name in ANALYSIS_LABELS)
                or not isinstance(analysis.get("parameters", {}), dict)):
            raise ValueError("analysis 必须包含检查结果数组和 parameters 对象")
        # Analysis is advisory: rerunning it must not reset a user's otherwise current browser draft.
        report["analysis"] = json.loads(json.dumps(analysis, ensure_ascii=False, allow_nan=False))
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "report.json"
    if any((directory / name).exists() for name in ("index.html", "detail.html", "report.json", "report.md", "thumbnails")):
        try:
            managed = json.loads(marker.read_text(encoding="utf-8")).get("reportKind") == REPORT_KIND
        except (OSError, ValueError, AttributeError):
            managed = False
        if not managed:
            raise ValueError("报告目录中已有非本工具生成的文件；请使用新的专用目录")
    thumbnails = directory / "thumbnails"
    if thumbnails.is_symlink() or any((directory / name).is_symlink() for name in ("index.html", "detail.html", "report.json", "report.md")):
        raise ValueError("报告输出文件及缩略图目录不能是符号链接")
    thumbnails.mkdir(exist_ok=True)
    for checksum, path in paths.items():
        thumb = thumbnails / (checksum + ".jpg")
        if thumb.is_symlink():
            raise ValueError("报告缩略图不能是符号链接")
        if not thumb.exists():
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                handle, name = tempfile.mkstemp(prefix=".thumb-", suffix=".tmp", dir=thumbnails)
                os.close(handle)
                temporary = Path(name)
                try:
                    image.save(temporary, format="JPEG", quality=88)
                    os.replace(temporary, thumb)
                finally:
                    temporary.unlink(missing_ok=True)
    for item in report["items"]:
        for artifact in item["variants"].values():
            if artifact["valid"]:
                artifact["thumbHref"] = "thumbnails/" + artifact["sha256"] + ".jpg"
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    embedded = serialized.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = TEMPLATE.read_text(encoding="utf-8")
    for mode, filename in (("list", "index.html"), ("detail", "detail.html")):
        _atomic_text(directory / filename, template.replace("__PAGE_MODE__", mode).replace("__REPORT_JSON__", embedded))
    _atomic_text(directory / "report.md", _markdown(report))
    _atomic_text(marker, serialized)
    return {"index": str(directory / "index.html"), "detail": str(directory / "detail.html"),
            "json": str(marker), "markdown": str(directory / "report.md"),
            "fileCount": 4 + len(paths), "thumbnailCount": len(paths)}


def main():
    parser = argparse.ArgumentParser(description="生成本地选图与验收报告；不改处理队列、原图或网站")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_report(json.loads(args.state.read_text(encoding="utf-8")), args.library, args.directory)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(f"素材报告生成失败: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
