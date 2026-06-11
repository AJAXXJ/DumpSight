import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class SymbolStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MismatchPattern:
    """
    mismatch 检测规则

    匹配逻辑（AND）：
      1. substrings  — 所有子串必须出现在 err 中
      2. pattern     — 正则匹配（可选）
    """

    key: str
    category: Literal[
        "binary",
        "symbol",
        "debug_info",
        "runtime",
        "core",
        "architecture",
        "gdb",
    ]
    severity: Literal["fatal", "non_fatal"]

    substrings: tuple[str, ...] = field(default_factory=tuple)
    pattern: re.Pattern[str] | None = None

    def __post_init__(self) -> None:
        if not self.substrings and self.pattern is None:
            raise ValueError(
                f"Rule '{self.key}' must define at least one of: substrings, pattern"
            )

    @classmethod
    def from_strings(
        cls,
        key: str,
        category: Literal[
            "binary",
            "symbol",
            "debug_info",
            "runtime",
            "core",
            "architecture",
            "gdb",
        ],
        severity: Literal["fatal", "non_fatal"],
        substrings: tuple[str, ...] = (),
        regex: str | None = None,
        flags: re.RegexFlag = re.IGNORECASE,
    ) -> "MismatchPattern":
        compiled = re.compile(regex, flags) if regex else None
        return cls(
            key=key,
            category=category,
            severity=severity,
            substrings=substrings,
            pattern=compiled,
        )

    def matches(self, err: str) -> bool:
        return all(s in err for s in self.substrings) and (
            self.pattern is None or bool(self.pattern.search(err))
        )


_BINARY_PATTERNS: list[MismatchPattern] = [
    MismatchPattern(
        key="binary_identity_mismatch",
        category="binary",
        severity="fatal",
        substrings=("build-id", "does not match core file"),
    ),
    MismatchPattern.from_strings(
        key="shared_library_identity_mismatch",
        category="binary",
        severity="fatal",
        substrings=("build-id",),
        regex=r"(shared library|\.so).*does not match",
    ),
    MismatchPattern.from_strings(
        key="relocation_address_mismatch",
        category="binary",
        severity="non_fatal",
        regex=r"loaded at (0x[0-9a-f]+).*expected (0x[0-9a-f]+)",
    ),
    MismatchPattern.from_strings(
        key="address_space_randomization_issue",
        category="binary",
        severity="non_fatal",
        regex=r"(add-symbol-file|address.*relocation|kaslr|pie.*offset)",
    ),
    MismatchPattern.from_strings(
        key="binary_checksum_mismatch",
        category="binary",
        severity="fatal",
        substrings=("crc mismatch",),
        regex=r"(checksum mismatch|checksum does not match|crc mismatch)",
    ),
    MismatchPattern.from_strings(
        key="shared_library_load_failure",
        category="binary",
        severity="non_fatal",
        regex=r"(cannot find|could not load|skipping).*shared librar",
    ),
    MismatchPattern.from_strings(
        key="shared_library_symbol_resolution_failure",
        category="binary",
        severity="non_fatal",
        substrings=("could not load shared library symbols",),
    ),
]

_SYMBOL_PATTERNS: list[MismatchPattern] = [
    MismatchPattern(
        key="library_version_mismatch",
        category="symbol",
        severity="fatal",
        substrings=("wrong library or version mismatch",),
    ),
    MismatchPattern.from_strings(
        key="symbol_version_mismatch",
        category="symbol",
        severity="fatal",
        regex=r"(requires version|no symbol version)",
    ),
]

_DEBUG_INFO_PATTERNS: list[MismatchPattern] = [
    MismatchPattern.from_strings(
        key="debug_info_missing",
        category="debug_info",
        severity="non_fatal",
        regex=r"(could not find|cannot find|no such file).*\.debug",
    ),
    MismatchPattern.from_strings(
        key="debug_info_missing",
        category="debug_info",
        severity="non_fatal",
        regex=r"(missing|not found).*(debuginfo|debug.info|debug.symbol)",
    ),
    MismatchPattern(
        key="symbol_table_missing",
        category="debug_info",
        severity="non_fatal",
        substrings=("no debugging symbols found",),
    ),
    MismatchPattern(
        key="symbol_table_missing",
        category="debug_info",
        severity="non_fatal",
        substrings=("no symbol table is loaded",),
    ),
]

_ARCHITECTURE_PATTERNS: list[MismatchPattern] = [
    MismatchPattern.from_strings(
        key="architecture_mismatch",
        category="architecture",
        severity="fatal",
        regex=r"(wrong architecture|elf class mismatch|not.*elf.*format)",
    ),
    MismatchPattern.from_strings(
        key="architecture_bitwidth_mismatch",
        category="architecture",
        severity="fatal",
        regex=r"(32.bit.*64.bit|64.bit.*32.bit|elf32.*elf64|elf64.*elf32)",
    ),
    MismatchPattern.from_strings(
        key="abi_endianness_mismatch",
        category="architecture",
        severity="fatal",
        regex=r"(abi mismatch|wrong endian|endianness mismatch)",
    ),
]

_CORE_PATTERNS: list[MismatchPattern] = [
    MismatchPattern.from_strings(
        key="core_file_truncated",
        category="core",
        severity="fatal",
        regex=r"(truncated|incomplete).*(core|coredump)",
    ),
    MismatchPattern.from_strings(
        key="core_file_invalid_format",
        category="core",
        severity="fatal",
        regex=r"(not a core file|invalid core|unrecognized.*core)",
    ),
    MismatchPattern(
        key="core_register_access_failure",
        category="core",
        severity="non_fatal",
        substrings=("can't fetch registers from this type of core file",),
    ),
]

_RUNTIME_PATTERNS: list[MismatchPattern] = [
    MismatchPattern.from_strings(
        key="thread_state_unavailable",
        category="runtime",
        severity="non_fatal",
        regex=r"(cannot find|unable to find|failed to read).*(thread|lwp)",
    ),
    MismatchPattern.from_strings(
        key="register_read_failure",
        category="runtime",
        severity="non_fatal",
        regex=r"(register|pc|sp|fp).*(unavailable|not available|could not read)",
    ),
]

_GDB_PATTERNS: list[MismatchPattern] = [
    MismatchPattern.from_strings(
        key="gdb_python_printer_exception",
        category="gdb",
        severity="non_fatal",
        regex=r"python exception.*gdb\.(Value|Type|Frame|Block)",
    ),
]

_MISMATCH_PATTERNS: list[MismatchPattern] = [
    *_BINARY_PATTERNS,
    *_SYMBOL_PATTERNS,
    *_DEBUG_INFO_PATTERNS,
    *_ARCHITECTURE_PATTERNS,
    *_CORE_PATTERNS,
    *_RUNTIME_PATTERNS,
    *_GDB_PATTERNS,
]


class SymbolQualityAssessor:
    """
    根据 GDB returncode 和 stderr 评估符号解析质量。
    """

    def __init__(self, patterns: list[MismatchPattern] = _MISMATCH_PATTERNS) -> None:
        self._patterns = patterns

    def assess(
        self,
        returncode: int | None,
        stderr: str | None,
    ) -> tuple[SymbolStatus, list[str]]:
        err = (stderr or "").lower().strip()
        triggered = [p for p in self._patterns if p.matches(err)]

        # 去重，保持首次命中顺序
        warnings: list[str] = list(dict.fromkeys(p.key for p in triggered))

        if any(p.severity == "fatal" for p in triggered):
            return SymbolStatus.INVALID, warnings
        if triggered:
            return SymbolStatus.DEGRADED, warnings
        if returncode is None:
            warnings.append("gdb_returncode_unknown")
            return SymbolStatus.UNKNOWN, warnings
        if returncode != 0:
            warnings.append(f"gdb_returncode_{returncode}")
            return SymbolStatus.DEGRADED, warnings

        return SymbolStatus.VALID, warnings


# ── Backward-compatible free function ─────────────────────────────────────

_default_assessor = SymbolQualityAssessor()


def assess_symbol_status(
    returncode: int | None,
    stderr: str | None,
) -> tuple[SymbolStatus, list[str]]:
    return _default_assessor.assess(returncode, stderr)
