#!/usr/bin/env python3
"""Disassemble an ESP8266 non-OS V2 user-bin slice and annotate literals."""

import argparse
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile


IROM_BASE = 0x40200000
IROM_FILE_OFFSET = 0x10


def file_to_vma(offset: int) -> int:
    return IROM_BASE + offset - IROM_FILE_OFFSET


def vma_to_file(address: int) -> int:
    return address - IROM_BASE + IROM_FILE_OFFSET


def absolute_irom_pointer_to_file(address: int) -> int:
    """Map an absolute linked irom pointer to this extracted V2 user-bin.

    The V2 header shifts instruction bytes by 0x10 for disassembly, but
    absolute pointers embedded by the linker use the unshifted irom offset.
    Keeping these mappings separate avoids annotating valid field names as
    unrelated strings ten bytes later in the image.
    """
    return address - IROM_BASE


def cstring(data: bytes, offset: int, limit: int = 120) -> str | None:
    if not 0 <= offset < len(data):
        return None
    end = data.find(b"\0", offset, min(offset + limit, len(data)))
    if end < 0:
        return None
    try:
        value = data[offset:end].decode("ascii")
    except UnicodeDecodeError:
        return None
    if value and all(32 <= ord(char) < 127 or char in "\t\r\n" for char in value):
        return value
    return None


def find_tool(explicit: str | None, names: tuple[str, ...]) -> str:
    if explicit is not None:
        return explicit
    for name in names:
        if path := shutil.which(name):
            return path
    raise SystemExit(f"required tool not found: {' or '.join(names)}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("image", type=Path)
    result.add_argument("file_offset", type=lambda value: int(value, 0))
    result.add_argument("length", type=lambda value: int(value, 0))
    result.add_argument("--objdump", help="Xtensa objdump executable")
    result.add_argument("--objcopy", help="Xtensa objcopy executable")
    return result


def main() -> None:
    args = parser().parse_args()
    image = args.image
    start = args.file_offset
    length = args.length
    data = image.read_bytes()
    chunk = data[start : start + length]
    base = file_to_vma(start)
    objcopy = find_tool(
        args.objcopy,
        ("xtensa-linux-gnu-objcopy", "xtensa-lx106-elf-objcopy"),
    )
    objdump = find_tool(
        args.objdump,
        ("xtensa-linux-gnu-objdump", "xtensa-lx106-elf-objdump"),
    )
    with tempfile.TemporaryDirectory(prefix="petkit-disasm-") as directory:
        raw = Path(directory) / "slice.bin"
        elf = Path(directory) / "slice.elf"
        raw.write_bytes(chunk)
        subprocess.run(
            [
                objcopy,
                "-I", "binary",
                "-O", "elf32-xtensa-le",
                "-B", "xtensa",
                "--set-section-flags", ".data=alloc,load,code,contents",
                "--change-section-address", f".data={base:#x}",
                str(raw), str(elf),
            ],
            check=True,
        )
        output = subprocess.check_output([objdump, "-d", str(elf)], text=True)
    for line in output.splitlines():
        match = re.search(r"l32r\s+\w+,\s+([0-9a-f]+)", line)
        annotation = ""
        if match:
            target = int(match.group(1), 16)
            offset = vma_to_file(target)
            if 0 <= offset <= len(data) - 4:
                value = struct.unpack_from("<I", data, offset)[0]
                annotation = f" ; *[{target:#x}]={value:#x}"
                pointer_text = cstring(data, absolute_irom_pointer_to_file(value))
                if pointer_text is not None:
                    annotation += f" -> {pointer_text!r}"
                shifted_text = cstring(data, vma_to_file(value))
                if shifted_text is not None and shifted_text != pointer_text:
                    annotation += f" [payload+0x10: {shifted_text!r}]"
        print(line + annotation)


if __name__ == "__main__":
    main()
