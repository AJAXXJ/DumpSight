import json
from pathlib import Path

from tools.logger import logger

from .analyzer import analyze_core_dump
from .constant import FILE_STABLE_TIMEOUT
from .utils import wait_file_stable, is_probable_executable


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def resolve_input_files(input_paths):
    """
    严格识别 core / exe / log：
    - core: 必须且仅 1 个（文件名以 core. 开头）
    - log : 可选且最多 1 个（.log）
    - exe : 可选且最多 1 个（需满足可执行特征）
    """
    core_candidates = []
    log_candidates = []
    exe_candidates = []
    unknown = []

    for raw in input_paths:
        p = Path(raw)
        name = p.name

        if name.startswith("core."):
            core_candidates.append(str(p))
        elif name.lower().endswith(".log"):
            log_candidates.append(str(p))
        elif is_probable_executable(str(p)):
            exe_candidates.append(str(p))
        else:
            unknown.append(str(p))

    if len(core_candidates) != 1:
        raise ValueError(f"core 文件数量非法（期望 1，实际 {len(core_candidates)}）: {core_candidates}")
    if len(log_candidates) > 1:
        raise ValueError(f"log 文件数量非法（最多 1）: {log_candidates}")
    if len(exe_candidates) > 1:
        raise ValueError(f"exe 文件数量非法（最多 1）: {exe_candidates}")
    if unknown:
        raise ValueError(f"存在无法识别的输入文件，请显式提供 core/log/exe: {unknown}")

    return {
        "core_path": core_candidates[0],
        "exe_path": exe_candidates[0] if exe_candidates else None,
        "log_path": log_candidates[0] if log_candidates else None,
    }


def run_core_extractor(input_paths, output_dir):
    """
    统一入口：
    1) 识别输入
    2) 调用 analyzer 编排流程
    3) 统一写出 *.meta.json 与 *.context.json
    """
    files = resolve_input_files(input_paths)
    core_path = files["core_path"]

    if not wait_file_stable(core_path, timeout=FILE_STABLE_TIMEOUT):
        logger.warning(f"警告: {core_path} 写入超时，仍继续分析")

    meta, context = analyze_core_dump(
        core_file=core_path,
        exe_path=files["exe_path"],
        log_path=files["log_path"],
    )

    out_dir = Path(output_dir)
    base = Path(core_path).name
    meta_file = out_dir / f"{base}.meta.json"
    context_file = out_dir / f"{base}.context.json"

    _write_json(meta_file, meta)
    _write_json(context_file, context)

    return {
        "meta": meta,
        "context": context,
        "inputs": files,
        "output_dir": str(out_dir),
        "meta_file": str(meta_file),
        "context_file": str(context_file),
    }


