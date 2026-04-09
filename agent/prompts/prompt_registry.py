import logging
from functools import lru_cache
from pathlib import Path
import yaml


logger = logging.getLogger(__name__)


_PROMPTS_ROOT = Path(__file__).parent
_SYSTEM_DIR = _PROMPTS_ROOT / "system"
_TEMPLATE_DIR = _PROMPTS_ROOT / "templates"
_FEW_SHOT_DIR = _PROMPTS_ROOT / "few_shots"
_VERSIONS_DIR = _PROMPTS_ROOT / "versions"


SYSTEM_KEYS: frozenset[str] = frozenset(
    {
        "base_system",
        "fault_analyst",
        "realtime_monitor",
        "case_builder",
    }
)

TEMPLATE_KEYS: frozenset[str] = frozenset(
    {
        "fault_analysis",
        "anomaly_detection",
        "case_ingestion",
        "root_cause_reasoning",
        "alert_generation",
        "repair_suggestion",
    }
)

FEW_SHOT_KEYS: frozenset[str] = frozenset(
    {
        "crash_examples",
        "anomaly_examples",
        "repair_examples",
    }
)


class PromptRegistry:
    """
    加载并缓存三类 prompt 资源：
      - system   : .md 文件，纯文本系统角色定义
      - template : .j2  文件，Jinja2 模板（含变量占位符）
      - few_shots: .yaml 文件，示例输入-输出对列表

    所有加载结果在进程生命周期内 LRU 缓存，避免重复 IO。
    调用 invalidate() 可清除缓存用于热重载场景
    """

    def __init__(self, version=None):
        """
        Args:
            version: 指定加载历史版本，如 "v1"、"v2"。
                     None 表示使用当前版本（prompts/ 根目录）。
        """
        self._version = version
        self._root = self._resolve_root(version)
        logger.info(
            "PromptRegistry initialized | root=%s version=%s",
            self._root,
            version or "current",
        )

    def get_system(self, key):
        """返回系统级 prompt 的原始字符串（不含变量，直接使用）。"""
        self._validate(key, SYSTEM_KEYS, "system")
        return self._load_markdown(self._root / "system" / f"{key}.md")

    def get_template(self, key):
        """返回 Jinja2 模板的原始字符串（交给 PromptBuilder 渲染）。"""
        self._validate(key, TEMPLATE_KEYS, "template")
        return self._load_text(self._root / "templates" / f"{key}.j2")

    def get_few_shots(self, key):
        """返回 few-shot 示例列表，每项为 {input: ..., output: ...} 字典。"""
        self._validate(key, FEW_SHOT_KEYS, "few_shots")
        return self._load_yaml(self._root / "few_shots" / f"{key}.yaml")

    def list_versions(self):
        """返回 versions/ 目录下所有可用的历史版本名称。"""
        if not _VERSIONS_DIR.exists():
            return []
        return sorted(p.name for p in _VERSIONS_DIR.iterdir() if p.is_dir())

    def invalidate(self):
        """清除 LRU 缓存，下次调用重新从磁盘读取（热重载用）。"""
        self._load_markdown.cache_clear()
        self._load_text.cache_clear()
        self._load_yaml.cache_clear()
        logger.info("PromptRegistry cache invalidated")

    def _resolve_root(self, version=None):
        if version is None:
            return _PROMPTS_ROOT
        version_root = _VERSIONS_DIR / version
        if not version_root.exists():
            available = self.list_versions()
            raise FileNotFoundError(
                f"Prompt version '{version}' not found. " f"Available: {available}"
            )
        return version_root

    @staticmethod
    def _validate(key, valid_keys, category):
        if key not in valid_keys:
            raise KeyError(
                f"Unknown {category} prompt key: '{key}'. "
                f"Valid keys: {sorted(valid_keys)}"
            )

    @lru_cache(maxsize=64)
    def _load_markdown(self, path):
        return self._load_text(path)

    @lru_cache(maxsize=64)
    def _load_text(self, path):
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        content = path.read_text(encoding="utf-8").strip()
        logger.debug("Loaded prompt | path=%s chars=%d", path, len(content))
        return content

    @lru_cache(maxsize=32)
    def _load_yaml(self, path):
        if not path.exists():
            raise FileNotFoundError(f"Few-shot file not found: {path}")
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, list):
            raise ValueError(f"Few-shot YAML must be a list, got {type(data)}: {path}")
        logger.debug("Loaded few-shots | path=%s count=%d", path, len(data))
        return data


_default_registry: PromptRegistry | None = None


def get_registry(version=None):
    """
    返回默认单例 PromptRegistry version=None
    若需历史版本 传入 version 参数 将返回独立实例
    """
    global _default_registry
    if version is not None:
        return PromptRegistry(version=version)
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry
