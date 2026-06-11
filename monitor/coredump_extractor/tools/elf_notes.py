"""直接从 core dump ELF 文件中提取寄存器、信号和 faulting address。

绕过 GDB 全量加载，只解析 ELF 文件头和 PT_NOTE 段。
"""

import struct
from typing import Optional


_ELFCLASS64 = 2
_PT_NOTE = 7

_NT_PRSTATUS = 1
_NT_SIGINFO = 0x53494749

_X86_64_REG_NAMES = (
    "r15", "r14", "r13", "r12", "rbp", "rbx",
    "r11", "r10", "r9", "r8", "rax", "rcx",
    "rdx", "rsi", "rdi", "orig_rax", "rip",
    "cs", "eflags", "rsp", "ss", "fs_base",
    "gs_base", "ds", "es", "fs", "gs",
)

_USER_REGS_SIZE = len(_X86_64_REG_NAMES) * 8  # 216 bytes for x86_64

# 关注的关键寄存器（供上游 crash_type 分类使用）
_KEY_REGISTERS = frozenset({"rip", "rsp", "rbp", "rdi", "rsi", "rdx"})


class ElfNotesReader:
    """读取 ELF core dump 的 PT_NOTE 段，返回结构化崩溃元信息。"""

    def read(self, core_path: str) -> dict:
        """返回 {"registers": {reg: hex_str, ...}, "signal": int|None,
                  "faulting_address": str|None, "pid": int|None}"""
        with open(core_path, "rb") as fh:
            data = fh.read()

        if data[:4] != b"\x7fELF":
            raise ValueError(f"不是 ELF 文件: {core_path}")
        ei_class = data[4]
        if ei_class != _ELFCLASS64:
            return self._empty()

        notes = self._collect_notes(data)
        return self._parse_notes(notes)

    # ── ELF header / program header parsing ─────────────────────────────────

    @staticmethod
    def _collect_notes(data: bytes) -> bytearray:
        e_phoff = struct.unpack_from("<Q", data, 32)[0]
        e_phentsize = struct.unpack_from("<H", data, 54)[0]
        e_phnum = struct.unpack_from("<H", data, 56)[0]

        buf = bytearray()
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            p_type = struct.unpack_from("<I", data, off)[0]
            if p_type != _PT_NOTE:
                continue
            p_offset = struct.unpack_from("<Q", data, off + 8)[0]
            p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
            buf.extend(data[p_offset:p_offset + p_filesz])
        return buf

    # ── Note iteration ─────────────────────────────────────────────────────

    def _parse_notes(self, notes: bytearray) -> dict:
        result: dict = {
            "registers": {},
            "signal": None,
            "faulting_address": None,
            "pid": None,
        }
        offset = 0
        nt_prstatus_seen = 0
        while offset + 12 <= len(notes):
            n_namesz, n_descsz, n_type = struct.unpack_from("<III", notes, offset)
            offset += 12
            name_end = (offset + n_namesz + 3) & ~3
            name = bytes(notes[offset:offset + n_namesz]).rstrip(b"\x00").decode()
            offset = name_end

            desc = bytes(notes[offset:offset + n_descsz])
            offset = (offset + n_descsz + 3) & ~3

            if name != "CORE":
                continue

            if n_type == _NT_PRSTATUS:
                nt_prstatus_seen += 1
                if nt_prstatus_seen == 1:
                    self._parse_prstatus(desc, result)
            elif n_type == _NT_SIGINFO:
                self._parse_siginfo(desc, result)

        return result

    # ── NT_PRSTATUS (寄存器 + 信号) ─────────────────────────────────────────

    def _parse_prstatus(self, desc: bytes, result: dict) -> None:
        # pr_cursig 在 offset 16 处（紧跟 elf_siginfo 之后）
        if len(desc) >= 18:
            result["signal"] = struct.unpack_from("<H", desc, 16)[0]

        # pr_pid 在 offset 40 处
        if len(desc) >= 44:
            result["pid"] = struct.unpack_from("<i", desc, 40)[0]

        # pr_reg 在 elf_prstatus 的末尾，长度为 _USER_REGS_SIZE
        if len(desc) >= _USER_REGS_SIZE:
            reg_data = desc[-_USER_REGS_SIZE:]
            vals = struct.unpack_from(f"<{len(_X86_64_REG_NAMES)}Q", reg_data, 0)
            for name, val in zip(_X86_64_REG_NAMES, vals):
                if name in _KEY_REGISTERS:
                    result["registers"][name] = f"0x{val:x}"

    # ── NT_SIGINFO (faulting address) ───────────────────────────────────────

    def _parse_siginfo(self, desc: bytes, result: dict) -> None:
        # siginfo_t 的 si_addr 在 offset 16（跳过 si_signo/si_errno/si_code）
        if len(desc) >= 24:
            si_addr = struct.unpack_from("<Q", desc, 16)[0]
            result["faulting_address"] = f"0x{si_addr:x}"

    # ── Empty fallback ─────────────────────────────────────────────────────

    @staticmethod
    def _empty() -> dict:
        return {"registers": {}, "signal": None, "faulting_address": None, "pid": None}


# 模块级快捷函数
_default_reader = ElfNotesReader()


def read_elf_notes(core_path: str) -> dict:
    return _default_reader.read(core_path)
