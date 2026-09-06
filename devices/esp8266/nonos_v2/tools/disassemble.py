#!/usr/bin/env python3
"""Disassemble an ESP8266 non-OS V2 user-bin slice and annotate literals."""

from pathlib import Path
import re
import struct
import subprocess
import sys


OBJDUMP = "/usr/bin/xtensa-linux-gnu-objdump"
OBJCOPY = "/usr/bin/xtensa-linux-gnu-objcopy"
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


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(f"usage: {sys.argv[0]} IMAGE FILE_OFFSET LENGTH")
    image = Path(sys.argv[1])
    start = int(sys.argv[2], 0)
    length = int(sys.argv[3], 0)
    data = image.read_bytes()
    chunk = data[start : start + length]
    raw = Path("/tmp/petkit-disasm.bin")
    elf = Path("/tmp/petkit-disasm.elf")
    raw.write_bytes(chunk)
    base = file_to_vma(start)
    subprocess.run(
        [
            OBJCOPY,
            "-I", "binary",
            "-O", "elf32-xtensa-le",
            "-B", "xtensa",
            "--set-section-flags", ".data=alloc,load,code,contents",
            "--change-section-address", f".data={base:#x}",
            str(raw), str(elf),
        ],
        check=True,
    )
    output = subprocess.check_output([OBJDUMP, "-d", str(elf)], text=True)
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
