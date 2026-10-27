"""GPT Image / research / motion job packages, receipts, and late results."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from . import (
    FEATHER_SIZE,
    JOB_KINDS,
    JOB_OPERATIONS,
    POINTER_SIZE,
    ROOT,
    CreativeError,
    digest_bytes,
    digest_file,
    new_id,
    now,
    read_json,
    write_bytes_atomic,
    write_json_atomic,
)
from . import manual, normalization, research
from . import state as state_module

SCAN_STATUSES = ("waiting", "rejected", "cancelled", "superseded")
RESULT_NAMES = {"image": "result.png", "research": "report.md", "motion": "motion.md"}
RECEIPT_NAME = "receipt.json"


def _unique(prefix, existing):
    for _ in range(64):
        candidate = new_id(prefix)
        if candidate not in existing:
            return candidate
    raise CreativeError("无法分配制作区 id；请检查状态")


def _canonical_json(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _inspect_png(path):
    """Fully decode a PNG and report its hash, size, and transparency."""
    path = Path(path)
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise CreativeError("文件不是实际 PNG")
            image.verify()
        with Image.open(path) as image:
            image.load()
            size = list(image.size)
            mode = image.mode
            has_alpha = "A" in mode or (mode == "P" and "transparency" in image.info)
            transparent = False
            if has_alpha:
                alpha = image.convert("RGBA").getchannel("A")
                transparent = alpha.getextrema()[0] < 255
    except CreativeError:
        raise
    except Exception as error:
        raise CreativeError(f"PNG 无法完整解码: {error}") from error
    return {"sha256": digest_file(path), "size": size,
            "hasAlpha": has_alpha, "transparent": transparent}


def _input_entry(store, project, version_id):
    version = state_module.find_version(project, version_id)
    if project["objectKind"] == "pointer":
        relative = version.get("previewPath")
        if version.get("format") != "JSON" or not relative:
            raise CreativeError("指针任务输入必须是带渲染预览的指针版本")
    else:
        if version.get("format") != "PNG":
            raise CreativeError("任务输入版本必须是 PNG")
        relative = version["path"]
    path = store.root / relative
    if not path.is_file():
        raise CreativeError("输入版本文件不存在；请重新选择输入")
    info = _inspect_png(path)
    if info["sha256"] != version.get("sha256") and project["objectKind"] != "pointer":
        raise CreativeError("输入版本文件已变化；请先恢复或重建版本")
    if project["objectKind"] == "pointer" and info["size"] != list(version["size"]):
        raise CreativeError("指针输入预览尺寸与版本尺寸不一致")
    return {
        "kind": "version",
        "path": relative,
        "sha256": info["sha256"],
        "size": info["size"],
        "format": "PNG",
        "versionId": version["versionId"],
        "versionSha256": version.get("sha256"),
        "versionPath": version.get("path"),
    }


def _output_size(project, kind, input_entry, value):
    if kind in ("research", "motion"):
        if value is not None:
            raise CreativeError("调查/动效任务不接受输出尺寸")
        return None
    if value is None:
        if project["objectKind"] == "pointer":
            value = list(POINTER_SIZE)
        elif project["objectKind"] == "feather":
            value = list(FEATHER_SIZE)
        elif input_entry:
            value = list(input_entry["size"])
        else:
            raise CreativeError("生成任务必须给出输出尺寸")
    if not isinstance(value, list) or len(value) != 2:
        raise CreativeError("输出尺寸必须是两个正整数")
    for part in value:
        if not isinstance(part, int) or isinstance(part, bool) or part <= 0:
            raise CreativeError("输出尺寸必须是两个正整数")
    value = [int(value[0]), int(value[1])]
    if project["objectKind"] == "pointer" and tuple(value) != POINTER_SIZE:
        raise CreativeError("指针输出尺寸必须是 46×27")
    if project["objectKind"] == "feather" and tuple(value) != FEATHER_SIZE:
        raise CreativeError("羽毛输出尺寸必须是 350×512")
    return value


def _require_alpha(project, value):
    if value is not None and not isinstance(value, bool):
        raise CreativeError("requireAlpha 必须为布尔值")
    if project["objectKind"] in ("pointer", "feather"):
        if value is False:
            raise CreativeError("指针/羽毛任务必须保留透明通道")
        return True
    return True if value is None else value


def _painted_fill(operation, value):
    if value is not None and not isinstance(value, bool):
        raise CreativeError("paintedFill 必须为布尔值")
    if operation == "inpaint":
        if value is not True:
            raise CreativeError("补画任务必须标记 paintedFill: true")
        return True
    if value:
        raise CreativeError("只有补画任务可以标记 paintedFill")
    return False


def _reference_hashes(project, reference_ids):
    references = {reference["referenceId"]: reference
                  for reference in project.get("references") or []}
    return {reference_id: references[reference_id].get("sha256")
            for reference_id in reference_ids}


def instruction_text(project, job, job_dir):
    job_dir = Path(job_dir).resolve()
    kind = job["kind"]
    result_name = RESULT_NAMES[kind]
    lines = [
        f"# 制作任务 {job['jobId']}",
        "",
        f"- 仓库绝对路径：`{ROOT}`",
        f"- 项目：`{project['projectId']}`（{project['name']}）",
        f"- 对象类型：`{project['objectKind']}`",
        f"- 任务类型：`{kind}` / `{job['operation']}`",
        f"- 任务 revision：`{job['revision']}`",
        f"- 任务目录：`{job_dir}`",
    ]
    if job.get("input"):
        lines.append(f"- 输入：`{job_dir / 'input' / 'source.png'}`")
    else:
        lines.append("- 输入：无（按允许范围生成）")
    if job.get("maskPath"):
        lines.append(f"- 修改区遮罩：`{job_dir / job['maskPath']}`"
                     "（只允许遮罩内修改；遮罩外必须与输入逐像素一致）")
    contract = kind == "image" and job.get("contract") == "original-delivery-v1"
    if contract:
        lines += [
            f"- 生成原图：`{job_dir / 'output' / 'original.<实际扩展名>'}`（保留工具实际格式、尺寸和内容）",
            f"- 交付图：`{job_dir / 'output' / result_name}`",
            f"- 规格记录：`{job_dir / 'output' / 'normalization.json'}`",
            f"- 回执：`{job_dir / 'output' / RECEIPT_NAME}`",
            "",
            "## 参考（只读）",
            "",
        ]
    else:
        lines += [
            f"- 输出：`{job_dir / 'output' / result_name}`",
            f"- 回执：`{job_dir / 'output' / RECEIPT_NAME}`",
            "",
            "## 参考（只读）",
            "",
        ]
    if job.get("referenceIds"):
        for reference_id in job["referenceIds"]:
            reference = state_module.get_reference(project, reference_id)
            if reference is None:
                continue
            relative = reference.get("path")
            target = f"`{job_dir / 'references' / (reference_id + Path(relative).suffix)}`" if relative else "仅链接"
            lines.append(f"- `{reference_id}` — {reference.get('title') or ''} — "
                          f"{target} — sha256 `{reference.get('sha256')}`")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 允许修改",
        "",
    ]
    lines += [f"- {item}" for item in job.get("allowedChanges") or []] or ["- （无）"]
    lines += [
        "",
        "## 必须保留",
        "",
    ]
    lines += [f"- {item}" for item in job.get("preserved") or []] or ["- （无）"]
    lines += [
        "",
        "## 要求",
        "",
        "1. 只读取本任务的输入、参考和本说明；不要读取或改写其他项目、图库和正式站点。",
        ("2. 只写入本任务的 `output/original.<实际扩展名>`、`output/result.png`、"
         "`output/normalization.json` 和 `output/receipt.json`；不要覆盖生成原图。"
         if contract else
         f"2. 只写入本任务的 `output/{result_name}` 和 `output/{RECEIPT_NAME}`。"),
        "3. 不要修改 `site/`、`site/assets/`、`site/ornaments/` 或 `.local/output/homepage-images/`。",
        "4. 不要提交 Git、不推送、不发布；不要调用任何付费 API 或下载模型。",
    ]
    if kind == "image":
        size = job.get("outputSize") or []
        if contract:
            resampling = "nearest" if project.get("objectKind") == "pointer" else "lanczos"
            original_target = job_dir / "output" / "original.<扩展名>"
            result_target = job_dir / "output" / "result.png"
            record_target = job_dir / "output" / "normalization.json"
            command = (f'python tools/normalize_delivery.py --original "{original_target}" '
                       f'--result "{result_target}" --size {size[0]}x{size[1]} '
                       f'--resampling {resampling} --record "{record_target}"')
            if job.get("maskPath"):
                source_target = job_dir / "input" / "source.png"
                mask_target = job_dir / "input" / "mask.png"
                command = (f'python tools/normalize_delivery.py --original "{original_target}" '
                           f'--source "{source_target}" --mask "{mask_target}" '
                           f'--result "{result_target}" --size {size[0]}x{size[1]} '
                           f'--resampling {resampling} --record "{record_target}"')
            lines += [
                "5. 实际调用已有图像工具生成原图；把工具实际输出原样保存为 "
                "`output/original.<实际扩展名>`，不改尺寸、格式或内容，单独记录路径和 SHA-256。",
                f"6. 交付图 `output/result.png` 必须是真实 PNG，尺寸 {size[0]}×{size[1]}；"
                "允许等比缩放和透明补边，禁止拉伸、裁掉图案；不要用适配后的文件冒充原图。",
                "   补画任务允许生成原图与 input/source.png 尺寸不同；规格整理会先等比对齐到输入画布，"
                "并记录 `alignmentScale`、`alignmentPadding`；`alignedSize` 是缩放后的内容尺寸，"
                "`alignedSize + alignmentPadding = 输入画布`，再在遮罩内合成。",
                "7. 用确定性规格整理生成交付图（不覆盖原图）：",
                f"   `{command}`",
                "   （把 `<扩展名>` 换成实际后缀，例如 `original.png`；原图是 WebP 就写 `original.webp`。）",
                "   规格整理不得覆盖原图；"
                + ("遮罩外像素必须与 input/source.png 逐像素一致。"
                   if job.get("maskPath") else
                   "不要用适配后的文件冒充原图。"),
                "8. 回执 JSON 必须包含：`schemaVersion`（1）、`taskId`、`inputSha256`、"
                "`referenceSha256`、`outputSha256`、`size`、`format`（PNG）、`hasAlpha`、"
                "`summary`、`completedAt`，以及 `originalPath`、`originalSha256`、"
                "`originalSize`、`originalFormat`、`deliverySize`、`scale`、`padding`、"
                "`scaledSize`、`cropped`（false）、`stretch`（false）、"
                "`normalizationPath`、`normalizationSha256`。",
            ]
            if job.get("maskPath"):
                lines.append("   补画任务的回执还要填 `alignedSize`、`alignmentScale`、"
                             "`alignmentPadding`。")
            if job.get("requireAlpha"):
                lines.append("9. 必须保留透明通道，并至少有一个透明像素。")
            if job.get("paintedFill"):
                lines.append("10. 这是补画任务：保留原像素，只补允许的区域，回执写 `\"paintedFill\": true`。")
        else:
            lines += [
                f"5. 输出必须是真实 PNG，尺寸 {size[0]}×{size[1]}；不得拉伸或裁切。",
            ]
            if job.get("requireAlpha"):
                lines.append("6. 必须保留透明通道，并至少有一个透明像素。")
            if job.get("paintedFill"):
                lines.append("7. 这是补画任务：保留原像素，只补允许的区域，回执写 `\"paintedFill\": true`。")
            lines += [
                "8. 回执 JSON 必须包含：`schemaVersion`（1）、`taskId`、`inputSha256`、"
                "`referenceSha256`、`outputSha256`、`size`、`format`（PNG）、`hasAlpha`、"
                "`summary`、`completedAt`。",
            ]
    elif kind == "research":
        lines += [
            "5. 输出是 `output/report.md`：写明来源、形态要点、不确定处；不要写用户确认，不要产生素材版本。",
            "6. 回执 JSON 必须包含：`schemaVersion`（1）、`taskId`、`summary`、`completedAt`。",
        ]
    else:
        lines += [
            "5. 输出是 `output/motion.md`：写明动作、时序和网页接入建议；不要改代码、不要改正式站点。",
            "6. 回执 JSON 必须包含：`schemaVersion`（1）、`taskId`、`summary`、`completedAt`。",
        ]
    lines += [
        "",
        ("完成后回到工作台点“扫描回传”；原图、交付图、规格记录和回执必须同时写入，缺一保持等待。"
         if contract else
         "完成后回到工作台点“扫描回传”；结果和回执必须同时写入，缺一保持等待。"),
        "",
    ]
    return "\n".join(lines)


def _prepare_job(store, project, kind, operation, input_version_id, reference_ids,
                  allowed_changes, preserved, output_size, require_alpha,
                  painted_fill, revision=None):
    """Validate a job request, write its package, and return the job record."""
    project_id = project["projectId"]
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能创建制作任务")
    if kind not in JOB_KINDS:
        raise CreativeError(f"任务类型不合法: {kind}")
    if operation not in JOB_OPERATIONS[kind]:
        raise CreativeError(f"任务操作不合法: {operation}")
    reference_ids = research.string_list(reference_ids, "参考清单")
    if len(set(reference_ids)) != len(reference_ids):
        raise CreativeError("参考清单重复")
    allowed_changes = research.string_list(allowed_changes, "允许改动")
    preserved = research.string_list(preserved, "保留项")
    if project["objectKind"] == "bird" and kind in ("image", "motion"):
        raise CreativeError("青鸟尚未接入正式主页；本轮不创建制作任务")
    confirmation = None
    if kind in ("image", "motion"):
        confirmation = research.gate(project, reference_ids, allowed_changes, preserved)
    if kind == "image" and operation in ("edit", "inpaint") and not input_version_id:
        raise CreativeError("编辑/补画任务必须给出输入版本")
    input_entry = None
    if input_version_id:
        input_entry = _input_entry(store, project, input_version_id)
    size = _output_size(project, kind, input_entry, output_size)
    if kind == "image":
        alpha = _require_alpha(project, require_alpha)
    elif require_alpha is None:
        alpha = True
    elif isinstance(require_alpha, bool):
        alpha = require_alpha
    else:
        raise CreativeError("requireAlpha 必须为布尔值")
    painted = _painted_fill(operation, painted_fill)

    job_id = _unique("job", {job["jobId"] for job in project["jobs"]})
    job_relative = f"projects/{project_id}/jobs/{job_id}"
    job_dir = store.path_for(job_relative)
    try:
        (job_dir / "input").mkdir(parents=True, exist_ok=False)
        (job_dir / "references").mkdir()
        (job_dir / "output").mkdir()
        if input_entry is not None:
            copy = job_dir / "input" / "source.png"
            write_bytes_atomic(copy, (store.root / input_entry["path"]).read_bytes())
            if digest_file(copy) != input_entry["sha256"]:
                raise CreativeError("输入副本校验失败；请重新生成任务")
            input_entry["path"] = f"{job_relative}/input/source.png"
        mask_relative = None
        mask_sha = None
        if operation == "inpaint":
            if input_entry is None:
                raise CreativeError("补画任务必须有输入版本")
            with Image.open(job_dir / "input" / "source.png") as probe:
                probe.load()
                source_image = probe.convert("RGBA")
            mask = Image.new("L", source_image.size, 0)
            alpha_channel = source_image.getchannel("A")
            values = (alpha_channel.get_flattened_data()
                      if hasattr(alpha_channel, "get_flattened_data")
                      else alpha_channel.getdata())
            mask.putdata([255 if value > 0 else 0 for value in values])
            mask_path = job_dir / "input" / "mask.png"
            mask.save(mask_path, format="PNG")
            mask_relative = "input/mask.png"
            mask_sha = digest_file(mask_path)
        for reference_id in reference_ids:
            reference = state_module.get_reference(project, reference_id)
            if reference is None or not reference.get("path"):
                continue
            suffix = Path(reference["path"]).suffix or ".png"
            copy = job_dir / "references" / f"{reference_id}{suffix}"
            write_bytes_atomic(copy, (store.root / reference["path"]).read_bytes())
            if digest_file(copy) != reference.get("sha256"):
                raise CreativeError(f"参考副本校验失败: {reference_id}")
        if revision is None:
            revision = 1 + max((int(job.get("revision") or 0)
                                 for job in project["jobs"]), default=0)
        expected_name = RESULT_NAMES[kind]
        contract = "original-delivery-v1" if kind == "image" else None
        job = {
            "jobId": job_id,
            "kind": kind,
            "operation": operation,
            "status": "waiting",
            "revision": int(revision),
            "inputVersionId": input_entry["versionId"] if input_entry else None,
            "inputSha256": input_entry["sha256"] if input_entry else None,
            "input": input_entry,
            "referenceIds": list(reference_ids),
            "referenceHashes": _reference_hashes(project, reference_ids),
            "confirmationId": (confirmation["confirmationId"]
                                if confirmation is not None else None),
            "allowedChanges": list(allowed_changes),
            "preserved": list(preserved),
            "outputSize": size,
            "deliverySize": size if kind == "image" else None,
            "requireAlpha": alpha,
            "paintedFill": painted,
            "contract": contract,
            "resampling": "nearest" if project.get("objectKind") == "pointer" else "lanczos",
            "maskPath": mask_relative,
            "maskSha256": mask_sha,
            "maskRequired": operation == "inpaint",
            "allowScale": True,
            "allowPadding": True,
            "preserveOriginal": True,
            "stretch": False,
            "crop": False,
            "selectedVersionIdAtCreation": project.get("selectedVersionId"),
            "jobPath": job_relative,
            "createdAt": now(),
            "completedAt": None,
            "error": None,
            "receipt": None,
            "resultSha256": None,
            "resultPath": None,
            "conflictSha256": None,
            "rejectedFingerprint": None,
            "attempts": [],
            "lateAt": None,
            "note": None,
        }
        expected = {"result": f"output/{expected_name}", "receipt": "output/receipt.json"}
        if contract:
            expected.update({"original": "output/original.*",
                             "normalization": "output/normalization.json"})
        if operation == "inpaint":
            expected["mask"] = "input/mask.png"
        document = dict(job)
        document.update({
            "schemaVersion": 1,
            "root": str(ROOT),
            "projectPath": f"projects/{project_id}",
            "contract": contract,
            "expected": expected,
            "instructionPath": f"{job_relative}/instruction.md",
        })
        write_json_atomic(job_dir / "job.json", document)
        (job_dir / "instruction.md").write_text(
            instruction_text(project, job, job_dir), encoding="utf-8")
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return job, job_dir


def create_job(store, project_id, kind, operation, input_version_id=None,
               reference_ids=None, allowed_changes=None, preserved=None,
               output_size=None, require_alpha=None, painted_fill=False):
    project = state_module.find_project(store.read(), project_id)
    job, job_dir = _prepare_job(
        store, project, kind, operation, input_version_id, reference_ids,
        allowed_changes, preserved, output_size, require_alpha, painted_fill)

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；不能创建制作任务")
        project["jobs"].append(job)
        if job["kind"] == "research":
            if project["status"] == "draft":
                project["status"] = "research"
            state_module.touch(project)
        else:
            state_module.transition_project(project, "awaiting-image")
        return job

    try:
        return store.mutate(add)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


def job_instruction(store, job_id):
    for project in store.read().get("projects") or []:
        job = state_module.get_job(project, job_id)
        if job is None:
            continue
        path = store.root / job["jobPath"] / "instruction.md"
        if not path.is_file():
            raise CreativeError(f"任务说明不存在: {job_id}", status=404)
        return path.read_text(encoding="utf-8")
    raise CreativeError(f"找不到任务: {job_id}", status=404)


def cancel_job(store, project_id, job_id):
    def cancel(state):
        project = state_module.find_project(state, project_id)
        job = state_module.find_job(project, job_id)
        if job["status"] not in ("waiting", "rejected"):
            raise CreativeError(f"任务当前状态不能取消: {job['status']}")
        job["status"] = "cancelled"
        job["error"] = None
        job["note"] = "用户取消任务"
        if project["status"] == "awaiting-image" and not any(
                item.get("status") == "waiting" for item in project["jobs"]):
            project["status"] = "review"
        state_module.touch(project)
        return job

    return store.mutate(cancel)


def rebuild_job(store, project_id, job_id):
    project = state_module.find_project(store.read(), project_id)
    old = state_module.find_job(project, job_id)
    if old["status"] == "superseded":
        raise CreativeError("任务已被替换；不能再次重建")
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能重建任务")
    if old["kind"] in ("image", "motion"):
        research.gate(project, old["referenceIds"], old["allowedChanges"], old["preserved"])
    job, job_dir = _prepare_job(
        store, project, old["kind"], old["operation"], old["inputVersionId"],
        old["referenceIds"], old["allowedChanges"], old["preserved"],
        old["outputSize"], old["requireAlpha"], old["paintedFill"],
        revision=int(old["revision"]) + 1)

    def replace(state):
        project = state_module.find_project(state, project_id)
        current = state_module.find_job(project, job_id)
        if current["status"] == "superseded":
            raise CreativeError("任务已被替换；不能再次重建")
        current["status"] = "superseded"
        current["note"] = "任务已重建"
        project["jobs"].append(job)
        if job["kind"] != "research":
            state_module.transition_project(project, "awaiting-image")
        else:
            state_module.touch(project)
        return job

    try:
        return store.mutate(replace)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


def _late_reason(job, project, check_selection):
    if job.get("status") in ("cancelled", "superseded"):
        return "任务已取消或已被替换；迟到结果保留在任务目录，不接入版本"
    if not check_selection:
        return None
    created = job.get("selectedVersionIdAtCreation")
    current = project.get("selectedVersionId")
    if created != current:
        return "用户已换过选中版本；迟到结果保留在任务目录，不接入版本"
    if job.get("inputVersionId") and current and current != job["inputVersionId"]:
        return "用户已切走任务输入版本；迟到结果保留在任务目录，不接入版本"
    return None


def _receipt_error(receipt, job, result_hash, size, has_alpha):
    if not isinstance(receipt, dict):
        return "回执必须是 JSON 对象"
    if receipt.get("schemaVersion") != 1:
        return "回执 schemaVersion 必须为 1"
    if receipt.get("taskId") != job["jobId"]:
        return "回执 taskId 与任务不一致"
    if receipt.get("inputSha256") != job.get("inputSha256"):
        return "回执输入 SHA-256 与任务不一致"
    if receipt.get("referenceSha256") != job.get("referenceHashes"):
        return "回执参考 SHA-256 与任务不一致"
    if receipt.get("outputSha256") != result_hash:
        return "回执输出 SHA-256 与结果文件不一致"
    if receipt.get("size") != size:
        return f"回执尺寸 {receipt.get('size')} 与任务输出 {size} 不一致"
    if str(receipt.get("format", "")).upper() != "PNG":
        return "回执格式必须为 PNG"
    if receipt.get("hasAlpha") is not has_alpha:
        return "回执 hasAlpha 与实际结果不一致"
    if job.get("paintedFill"):
        if receipt.get("paintedFill") is not True:
            return "补画任务回执必须标记 paintedFill: true"
    elif receipt.get("paintedFill") is True:
        return "非补画任务回执不能标记 paintedFill: true"
    if not isinstance(receipt.get("summary"), str) or not receipt["summary"].strip():
        return "回执缺少处理摘要"
    if not isinstance(receipt.get("completedAt"), str) or not receipt["completedAt"].strip():
        return "回执缺少完成时间"
    return None


def _inside_job(job_dir, value, label):
    if not isinstance(value, str) or not value.strip():
        raise CreativeError(f"{label}路径不能为空")
    root = Path(job_dir).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        raise CreativeError(f"{label}路径越界")
    if path.is_symlink() or not path.is_file():
        raise CreativeError(f"{label}不存在")
    return path


def _contract_error(receipt, job, job_dir, result_hash, size):
    """Check the original/delivery contract; old jobs without it keep their old rules."""
    try:
        original_file = _inside_job(job_dir, receipt.get("originalPath"), "生成原图")
        original_bytes = original_file.read_bytes()
        original_image, original_format = normalization.decode(original_bytes, "生成原图")
    except CreativeError as error:
        return str(error)
    original_hash = digest_bytes(original_bytes)
    original_size = list(original_image.size)
    source_bytes = None
    mask_bytes = None
    source_size = None
    mask_size = None
    if job.get("maskPath"):
        try:
            source_file = _inside_job(job_dir, "input/source.png", "输入原图")
            mask_file = _inside_job(job_dir, job.get("maskPath"), "修改区遮罩")
            source_bytes = source_file.read_bytes()
            mask_bytes = mask_file.read_bytes()
            source_image, _ = normalization.decode(source_bytes, "输入原图")
            mask_image, _ = normalization.decode(mask_bytes, "修改区遮罩")
        except CreativeError as error:
            return str(error)
        if source_image.size != mask_image.size:
            return "输入原图和遮罩必须同尺寸"
        source_size = list(source_image.size)
        mask_size = list(mask_image.size)
        if digest_bytes(mask_bytes) != job.get("maskSha256"):
            return "任务遮罩已变化；请重建任务"
    if receipt.get("originalSha256") != original_hash:
        return "回执 originalSha256 与生成原图不一致"
    if receipt.get("originalSize") != original_size:
        return f"回执 originalSize {receipt.get('originalSize')} 与生成原图 {original_size} 不一致"
    if str(receipt.get("originalFormat", "")).upper() != original_format:
        return "回执 originalFormat 与生成原图不一致"
    if receipt.get("deliverySize") != size:
        return f"回执 deliverySize {receipt.get('deliverySize')} 与交付图 {size} 不一致"
    if receipt.get("cropped") is not False:
        return "回执 cropped 必须为 false；禁止裁切图案"
    if receipt.get("stretch") is not False:
        return "回执 stretch 必须为 false；禁止拉伸"
    scale = receipt.get("scale")
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale <= 0:
        return "回执 scale 必须是正数"
    padding = receipt.get("padding")
    if (not isinstance(padding, list) or len(padding) != 4
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0
                   for item in padding)):
        return "回执 padding 必须是四个非负整数"
    scaled = receipt.get("scaledSize")
    if (not isinstance(scaled, list) or len(scaled) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0
                   for item in scaled)):
        return "回执 scaledSize 必须是两个正整数"
    base_size = source_size if source_size is not None else original_size
    if job.get("maskPath"):
        aligned_size = receipt.get("alignedSize")
        if (not isinstance(aligned_size, list) or len(aligned_size) != 2
                or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0
                       for item in aligned_size)):
            return "回执 alignedSize 必须是两个正整数"
        alignment_scale = receipt.get("alignmentScale")
        if (isinstance(alignment_scale, bool)
                or not isinstance(alignment_scale, (int, float))
                or alignment_scale <= 0):
            return "回执 alignmentScale 必须是正数"
        alignment_padding = receipt.get("alignmentPadding")
        if (not isinstance(alignment_padding, list) or len(alignment_padding) != 4
                or any(isinstance(item, bool) or not isinstance(item, int) or item < 0
                       for item in alignment_padding)):
            return "回执 alignmentPadding 必须是四个非负整数"
        if (abs(aligned_size[0] - round(original_size[0] * alignment_scale)) > 1
                or abs(aligned_size[1] - round(original_size[1] * alignment_scale)) > 1):
            return "回执生成图对齐比例与生成原图不一致"
        if (aligned_size[0] + alignment_padding[0] + alignment_padding[2] != base_size[0]
                or aligned_size[1] + alignment_padding[1] + alignment_padding[3] != base_size[1]):
            return "回执生成图对齐与补边之和不等于输入画布"
    else:
        aligned_size = original_size
        alignment_scale = 1
        alignment_padding = [0, 0, 0, 0]
    if (abs(scaled[0] - round(base_size[0] * scale)) > 1
            or abs(scaled[1] - round(base_size[1] * scale)) > 1):
        return "回执缩放比例与交付基准不一致"
    if (scaled[0] + padding[0] + padding[2] != size[0]
            or scaled[1] + padding[1] + padding[3] != size[1]):
        return "回执缩放与补边之和不等于交付尺寸"
    if scaled[0] > size[0] or scaled[1] > size[1]:
        return "回执缩放尺寸超过交付尺寸；疑似拉伸或裁切"
    if base_size == size and (abs(scale - 1) > 1e-6 or padding != [0, 0, 0, 0]):
        return "同尺寸交付必须 scale=1、padding=[0,0,0,0]"
    try:
        expected_outcome = normalization.normalize(
            original_bytes, list(job.get("outputSize") or []),
            require_alpha=bool(job.get("requireAlpha")),
            resampling=job.get("resampling", "lanczos"),
            source_bytes=source_bytes, mask_bytes=mask_bytes)
    except CreativeError as error:
        return f"交付图无法按任务规格复核: {error}"
    expected_record = expected_outcome["record"]
    if expected_record["deliverySha256"] != result_hash:
        return "交付图不是由生成原图按任务规格整理得到；请用 normalize_delivery.py 重新生成"
    if expected_record["scale"] != scale or expected_record["padding"] != padding:
        return "回执缩放/补边与确定性整理结果不一致"
    if job.get("maskPath"):
        if expected_record.get("alignedSize") != aligned_size:
            return "规格记录的生成图对齐尺寸与回执不一致"
        if expected_record.get("alignmentScale") != alignment_scale:
            return "规格记录的生成图对齐比例与回执不一致"
        if expected_record.get("alignmentPadding") != alignment_padding:
            return "规格记录的生成图对齐补边与回执不一致"
        if expected_record.get("maskSha256") != job.get("maskSha256"):
            return "规格记录的遮罩哈希与任务不一致"
        if expected_record.get("outsideUnchanged") is not True:
            return "规格记录必须确认遮罩外像素未变"
    try:
        normalization_file = _inside_job(job_dir, receipt.get("normalizationPath"), "规格记录")
        document = read_json(normalization_file, "规格记录")
    except CreativeError as error:
        return str(error)
    if digest_file(normalization_file) != receipt.get("normalizationSha256"):
        return "回执 normalizationSha256 与规格记录不一致"
    if not isinstance(document, dict):
        return "规格记录必须是 JSON 对象"
    expected = {
        "originalSha256": original_hash,
        "originalSize": original_size,
        "deliverySha256": result_hash,
        "deliverySize": size,
        "scale": scale,
        "padding": padding,
        "scaledSize": scaled,
        "cropped": False,
        "stretch": False,
    }
    if job.get("maskPath"):
        expected.update({
            "sourceSha256": digest_bytes(source_bytes),
            "sourceSize": source_size,
            "maskSha256": digest_bytes(mask_bytes),
            "maskSize": mask_size,
            "alignedSize": aligned_size,
            "alignmentScale": alignment_scale,
            "alignmentPadding": alignment_padding,
            "outsideUnchanged": True,
        })
    for key, value in expected.items():
        if document.get(key) != value:
            return f"规格记录 {key} 与回执不一致"
    return None


def _evaluate_image(store, project, job, job_dir, result, receipt_path, result_hash):
    try:
        document = read_json(job_dir / "job.json", "任务 job.json")
    except CreativeError as error:
        return {"status": "rejected", "error": str(error)}
    if (document.get("jobId") != job["jobId"]
            or document.get("revision") != job["revision"]
            or document.get("contract") != job.get("contract")
            or (document.get("input") or {}).get("sha256") != job.get("inputSha256")
            or document.get("referenceHashes") != job.get("referenceHashes")):
        return {"status": "rejected", "error": "任务包身份或哈希与状态不一致；请重建任务"}
    if job.get("input"):
        copy = job_dir / "input" / "source.png"
        if not copy.is_file() or digest_file(copy) != job["inputSha256"]:
            return {"status": "rejected", "error": "任务输入副本已变化；请重建任务"}
    try:
        info = _inspect_png(result)
    except CreativeError as error:
        return {"status": "rejected", "error": str(error)}
    if info["sha256"] != result_hash:
        return {"status": "rejected", "error": "结果文件在读取期间发生变化；请重新扫描"}
    if job.get("outputSize") and info["size"] != job["outputSize"]:
        return {"status": "rejected",
                "error": f"结果尺寸 {info['size']} 与任务输出 {job['outputSize']} 不一致"}
    if job.get("requireAlpha"):
        if not info["hasAlpha"]:
            return {"status": "rejected", "error": "结果缺少透明通道"}
        if not info["transparent"]:
            return {"status": "rejected", "error": "结果没有透明像素"}
    try:
        receipt = read_json(receipt_path, "任务回执")
    except CreativeError as error:
        return {"status": "rejected", "error": str(error)}
    error = _receipt_error(receipt, job, result_hash, info["size"], info["hasAlpha"])
    if error:
        return {"status": "rejected", "error": error}
    original = None
    normalization_record = None
    if job.get("contract") == "original-delivery-v1":
        error = _contract_error(receipt, job, job_dir, result_hash, info["size"])
        if error:
            return {"status": "rejected", "error": error}
        try:
            original_file = _inside_job(job_dir, receipt.get("originalPath"), "生成原图")
            original_bytes = original_file.read_bytes()
            original_image, original_format = normalization.decode(original_bytes, "生成原图")
            normalization_file = _inside_job(job_dir, receipt.get("normalizationPath"), "规格记录")
            normalization_record = read_json(normalization_file, "规格记录")
        except CreativeError as error:
            return {"status": "rejected", "error": str(error)}
        original = {
            "path": original_file.relative_to(Path(job_dir).resolve()).as_posix(),
            "sha256": digest_bytes(original_bytes),
            "size": list(original_image.size),
            "format": original_format,
        }
    return {"status": "done", "receipt": receipt, "resultSha256": result_hash,
            "resultSize": info["size"], "hasAlpha": info["hasAlpha"],
            "original": original, "normalization": normalization_record}


def _evaluate_report(store, project, job, job_dir, result, receipt_path, result_hash):
    try:
        receipt = read_json(receipt_path, "任务回执")
    except CreativeError as error:
        return {"status": "rejected", "error": str(error)}
    if not isinstance(receipt, dict):
        return {"status": "rejected", "error": "回执必须是 JSON 对象"}
    if receipt.get("schemaVersion") != 1:
        return {"status": "rejected", "error": "回执 schemaVersion 必须为 1"}
    if receipt.get("taskId") != job["jobId"]:
        return {"status": "rejected", "error": "回执 taskId 与任务不一致"}
    if not isinstance(receipt.get("summary"), str) or not receipt["summary"].strip():
        return {"status": "rejected", "error": "回执缺少处理摘要"}
    if not isinstance(receipt.get("completedAt"), str) or not receipt["completedAt"].strip():
        return {"status": "rejected", "error": "回执缺少完成时间"}
    try:
        data = result.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {"status": "rejected", "error": f"报告无法读取为 UTF-8 文本: {error}"}
    if not text.strip():
        return {"status": "rejected", "error": "报告为空"}
    key = "researchReports" if job["kind"] == "research" else "motionNotes"
    return {"status": "done", "receipt": receipt, "resultSha256": result_hash,
            "text": text, "bytes": data, "reportKey": key}


def _evaluate(store, project, job):
    job_dir = store.root / job["jobPath"]
    kind = job["kind"]
    result = job_dir / "output" / RESULT_NAMES[kind]
    receipt_path = job_dir / "output" / RECEIPT_NAME
    if not result.is_file() or not receipt_path.is_file():
        return {"status": "waiting"}
    late = _late_reason(job, project, kind in ("image", "motion"))
    if late:
        return {"status": "late", "error": late}
    result_hash = digest_file(result)
    if job.get("resultSha256"):
        if result_hash == job["resultSha256"]:
            return {"status": "done", "unchanged": True}
        return {"status": "conflict", "sha256": result_hash,
                "error": "同一任务已登记另一份不同结果；请重建任务"}
    if kind == "image":
        return _evaluate_image(store, project, job, job_dir, result, receipt_path, result_hash)
    return _evaluate_report(store, project, job, job_dir, result, receipt_path, result_hash)


def _pointer_template(project):
    selected = state_module.get_version(project, project.get("selectedVersionId"))
    if selected is not None and selected.get("pointerSource"):
        return selected["pointerSource"]
    for version in reversed(project.get("versions") or []):
        if version.get("pointerSource"):
            return version["pointerSource"]
    return None


def _persist_image(store, project, job, outcome, written):
    result = store.root / job["jobPath"] / "output" / "result.png"
    data = result.read_bytes()
    if digest_bytes(data) != outcome["resultSha256"]:
        raise CreativeError("结果文件在校验后发生变化；请重新扫描")
    project_id = project["projectId"]
    version_id = _unique("ver", {version["versionId"] for version in project["versions"]})
    evidence = None
    if outcome.get("original"):
        evidence = {
            "original": outcome["original"],
            "normalization": outcome.get("normalization"),
        }
    if project["objectKind"] == "pointer":
        template = _pointer_template(project)
        if template is None:
            raise CreativeError("缺少指针模板；请先建立指针初始版本")
        source = manual.pointer_source_from_png(data, template)
        relative = f"projects/{project_id}/versions/{version_id}.json"
        payload = _canonical_json({"schemaVersion": 1, "pointerSource": source})
        write_bytes_atomic(store.root / relative, payload)
        written.append(store.root / relative)
        preview_relative = f"projects/{project_id}/versions/{version_id}.png"
        write_bytes_atomic(store.root / preview_relative,
                            manual.png_bytes(manual.render_pointer(source)))
        written.append(store.root / preview_relative)
        version = {
            "versionId": version_id,
            "parentVersionId": job.get("inputVersionId"),
            "source": "gpt-image-inpaint" if job["paintedFill"] else "gpt-image",
            "path": relative,
            "sha256": digest_file(store.root / relative),
            "size": list(POINTER_SIZE),
            "format": "JSON",
            "hasAlpha": True,
            "jobId": job["jobId"],
            "pointerSource": source,
            "previewPath": preview_relative,
            "manual": None,
            "paintedFill": job["paintedFill"],
            "createdAt": now(),
            "note": None,
            "evidence": evidence,
        }
        return {"version": version, "written": written}
    relative = f"projects/{project_id}/versions/{version_id}.png"
    write_bytes_atomic(store.root / relative, data)
    written.append(store.root / relative)
    version = {
        "versionId": version_id,
        "parentVersionId": job.get("inputVersionId"),
        "source": "gpt-image-inpaint" if job["paintedFill"] else "gpt-image",
        "path": relative,
        "sha256": digest_file(store.root / relative),
        "size": list(outcome["resultSize"]),
        "format": "PNG",
        "hasAlpha": outcome["hasAlpha"],
        "jobId": job["jobId"],
        "pointerSource": None,
        "previewPath": None,
        "manual": None,
        "paintedFill": job["paintedFill"],
        "createdAt": now(),
        "note": None,
        "evidence": evidence,
    }
    return {"version": version, "written": written}


def _persist_report(store, project, job, outcome, written):
    project_id = project["projectId"]
    folder = "reports" if job["kind"] == "research" else "motion"
    relative = f"projects/{project_id}/{folder}/{job['jobId']}.md"
    payload = outcome.get("bytes")
    payload = bytes(payload) if isinstance(payload, (bytes, bytearray)) else outcome["text"].encode("utf-8")
    if digest_bytes(payload) != outcome["resultSha256"]:
        raise CreativeError("报告在校验后发生变化；请重新扫描")
    write_bytes_atomic(store.root / relative, payload)
    written.append(store.root / relative)
    report = {
        "jobId": job["jobId"],
        "summary": outcome["receipt"].get("summary") or "",
        "path": relative,
        "sha256": digest_file(store.root / relative),
        "createdAt": now(),
    }
    return {"report": report, "reportKey": outcome["reportKey"], "written": written}


def _apply_outcome(store, project_id, snapshot, outcome):
    written = []
    payload = {}
    fingerprint = _fingerprint(store.root / snapshot["jobPath"], snapshot["kind"])
    try:
        if outcome["status"] == "done":
            try:
                project = state_module.find_project(store.read(), project_id)
                if snapshot["kind"] == "image":
                    payload = _persist_image(store, project, snapshot, outcome, written)
                else:
                    payload = _persist_report(store, project, snapshot, outcome, written)
            except (CreativeError, OSError) as error:
                for path in written:
                    path.unlink(missing_ok=True)
                written.clear()
                outcome = {"status": "rejected", "error": f"结果无法登记: {error}"}

        def apply(state):
            project = state_module.find_project(state, project_id)
            job = state_module.find_job(project, snapshot["jobId"])
            if job.get("status") == "done":
                if outcome["status"] != "conflict":
                    return {"jobId": job["jobId"], "status": job["status"],
                            "error": None, "versionId": None, "unchanged": True}
            elif job.get("status") not in SCAN_STATUSES:
                return {"jobId": job["jobId"], "status": job["status"],
                        "error": None, "versionId": None, "unchanged": True}
            if outcome["status"] == "done":
                if payload.get("version"):
                    project["versions"].append(payload["version"])
                if payload.get("report"):
                    project[payload["reportKey"]].append(payload["report"])
                job.update({
                    "status": "done",
                    "resultSha256": outcome["resultSha256"],
                    "resultPath": (payload["version"]["path"] if payload.get("version")
                                   else payload["report"]["path"]),
                    "completedAt": now(),
                    "receipt": outcome["receipt"],
                    "error": None,
                    "note": None,
                    "rejectedFingerprint": None,
                })
                if project["status"] != "archived":
                    if project["status"] == "review":
                        state_module.touch(project)
                    else:
                        state_module.transition_project(project, "review")
                return {"jobId": job["jobId"], "status": "done", "error": None,
                        "versionId": (payload["version"]["versionId"]
                                      if payload.get("version") else None)}
            job["status"] = outcome["status"]
            job["error"] = outcome.get("error")
            job["note"] = ("迟到结果保留在任务目录，不接入版本"
                           if outcome["status"] in ("late", "conflict")
                           else outcome.get("error"))
            job["attempts"] = list(job.get("attempts") or [])
            job["attempts"].append({"at": now(), "status": outcome["status"],
                                     "error": outcome.get("error")})
            if outcome["status"] == "rejected":
                job["rejectedFingerprint"] = fingerprint
            if outcome["status"] == "late":
                job["lateAt"] = now()
            if outcome["status"] == "conflict":
                job["conflictSha256"] = outcome.get("sha256")
            state_module.touch(project)
            return {"jobId": job["jobId"], "status": outcome["status"],
                    "error": outcome.get("error"), "versionId": None}

        return store.mutate(apply)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


def _apply_waiting(store, project_id, job_id, recovery):
    def apply(state):
        project = state_module.find_project(state, project_id)
        job = state_module.find_job(project, job_id)
        if job.get("status") not in ("waiting", "rejected"):
            return {"jobId": job_id, "status": job.get("status"), "error": None,
                    "versionId": None, "unchanged": True}
        if job["status"] == "rejected":
            job["status"] = "waiting"
            job["error"] = None
            job["rejectedFingerprint"] = None
        job["note"] = "服务重启后等待完整回传" if recovery else "等待结果和回执同时写入"
        state_module.touch(project)
        return {"jobId": job_id, "status": "waiting", "error": None, "versionId": None}

    return store.mutate(apply)


def _fingerprint(job_dir, kind):
    parts = []
    names = [RESULT_NAMES[kind], RECEIPT_NAME, "normalization.json"]
    for name in names:
        path = Path(job_dir) / "output" / name
        try:
            stat = path.stat()
            parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:missing")
    for path in sorted((Path(job_dir) / "output").glob("original.*")):
        try:
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{path.name}:missing")
    mask = Path(job_dir) / "input" / "mask.png"
    try:
        stat = mask.stat()
        parts.append(f"mask.png:{stat.st_size}:{stat.st_mtime_ns}")
    except OSError:
        parts.append("mask.png:missing")
    return "|".join(parts)


def scan_project(store, project_id, recovery=False):
    """Check one project's job folders; attach only validated results."""
    project = state_module.find_project(store.read(), project_id)
    changes = []
    for snapshot in list(project.get("jobs") or []):
        status = snapshot.get("status")
        if status not in SCAN_STATUSES and status != "done":
            continue
        job_dir = store.root / snapshot["jobPath"]
        if status == "done":
            # A finished job is only re-read to catch a replaced result file.
            result = job_dir / "output" / RESULT_NAMES[snapshot["kind"]]
            if not result.is_file():
                continue
            current = digest_file(result)
            if current == snapshot.get("resultSha256"):
                continue
            outcome = {"status": "conflict", "sha256": current,
                       "error": "同一任务已登记另一份不同结果；请重建任务"}
            changes.append(_apply_outcome(store, project_id, snapshot, outcome))
            continue
        fingerprint = _fingerprint(job_dir, snapshot["kind"])
        if (snapshot["status"] == "rejected"
                and snapshot.get("rejectedFingerprint") == fingerprint):
            continue
        outcome = _evaluate(store, project, snapshot)
        if outcome["status"] == "waiting":
            if snapshot["status"] == "rejected":
                changes.append(_apply_waiting(store, project_id, snapshot["jobId"], recovery))
            elif recovery and snapshot.get("note") != "服务重启后等待完整回传":
                partial = ((job_dir / "output" / RESULT_NAMES[snapshot["kind"]]).exists()
                           or (job_dir / "output" / RECEIPT_NAME).exists())
                if partial:
                    changes.append(_apply_waiting(store, project_id, snapshot["jobId"], True))
            continue
        if outcome["status"] == "done" and outcome.get("unchanged"):
            continue
        changes.append(_apply_outcome(store, project_id, snapshot, outcome))
    return changes


def recover_jobs(store):
    changes = []
    for project in store.read().get("projects") or []:
        if any(job.get("status") in ("waiting", "rejected")
               for job in project.get("jobs") or []):
            changes.extend(scan_project(store, project["projectId"], recovery=True))
    return changes
