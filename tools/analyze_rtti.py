"""Static RTTI / call-site analysis for the game's DLLs, with no process attached.

Enumerates MSVC RTTI (type descriptors -> complete object locators -> vtables) in a
PE image and can disassemble the code that references a class's vtable, so item and
inventory entry points can be located while the game is closed.

    python tools/analyze_rtti.py names [pattern]
    python tools/analyze_rtti.py vtable <ClassName>
    python tools/analyze_rtti.py refs <ClassName> [--limit N]
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_OP_MEM, CS_MODE_64, Cs

GAME = Path(r"D:\App\Steam\steamapps\common\Dying Light The Beast")
BIN = GAME / "ph_ft" / "work" / "bin" / "x64"
DLL_NAME = "gamedll_ph_x64_rwdi.dll"

SECTION_READABLE = 0x40000000
RTTI_NAME = re.compile(rb"\.\?A[VU][^\x00]{2,220}@@\x00")


class Image:
    def __init__(self, path: Path):
        self.pe = pefile.PE(str(path))
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.sections = [(s.Name.rstrip(b"\x00").decode("ascii", "replace"), s.VirtualAddress,
                          s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics)
                         for s in self.pe.sections]
        self.data = path.read_bytes()

    def section_of(self, rva: int):
        for entry in self.sections:
            _, va, vsize, raw, rsize, _ = entry
            if va <= rva < va + max(vsize, rsize):
                return entry
        return None

    def read(self, rva: int, size: int) -> bytes:
        entry = self.section_of(rva)
        if entry is None:
            return b""
        _, va, _, raw, _, _ = entry
        return self.data[raw + (rva - va):raw + (rva - va) + size]

    def offset_to_rva(self, offset: int):
        for _, va, _, raw, rsize, _ in self.sections:
            if raw <= offset < raw + rsize:
                return va + (offset - raw)
        return None


def type_descriptors(image: Image) -> dict[int, str]:
    """RVA of each TypeDescriptor -> mangled class name. The name follows two pointers."""
    found = {}
    for match in RTTI_NAME.finditer(image.data):
        rva = image.offset_to_rva(match.start())
        if rva is None or rva < 0x10:
            continue
        found[rva - 0x10] = match.group(0)[:-1].decode("ascii", "replace")
    return found


def locators(image: Image, descriptors: dict[int, str]) -> dict[int, str]:
    """RVA of each RTTICompleteObjectLocator -> class name."""
    found = {}
    for _, va, _, raw, rsize, chars in image.sections:
        if not chars & SECTION_READABLE:
            continue
        for offset in range(raw, raw + rsize - 20, 4):
            if image.data[offset:offset + 4] != b"\x00\x00\x00\x00":
                continue
            signature, _, _, descriptor, _ = struct.unpack_from("<IIIII", image.data, offset)
            if signature or descriptor not in descriptors:
                continue
            found[va + (offset - raw)] = descriptors[descriptor]
    return found


def vtables(image: Image, cols: dict[int, str]) -> dict[int, list[str]]:
    """RVA of each vtable -> the class names its locator belongs to."""
    found: dict[int, list[str]] = {}
    for _, va, _, raw, rsize, chars in image.sections:
        if not chars & SECTION_READABLE:
            continue
        for offset in range(raw, raw + rsize - 8, 8):
            value = struct.unpack_from("<Q", image.data, offset)[0]
            if value < image.base:
                continue
            name = cols.get(value - image.base)
            if name:
                found.setdefault(va + (offset - raw) + 8, []).append(name)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["names", "vtable", "refs"])
    parser.add_argument("target", nargs="?", default="")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--dll", default=DLL_NAME)
    args = parser.parse_args()

    image = Image(BIN / args.dll)
    descriptors = type_descriptors(image)
    cols = locators(image, descriptors)
    tables = vtables(image, cols)
    print(f"{args.dll}: descriptors {len(descriptors)}, locators {len(cols)}, vtables {len(tables)}", file=sys.stderr)

    if args.action == "names":
        pattern = re.compile(args.target, re.I) if args.target else None
        names = sorted({name for name in descriptors.values() if not pattern or pattern.search(name)})
        for name in names[:args.limit]:
            print(name)
        print(f"-- {len(names)} matches", file=sys.stderr)
        return 0

    if args.action == "vtable":
        hits = [(rva, cls) for rva, classes in tables.items() for cls in classes
                if args.target.lower() in cls.lower()]
        for rva, cls in sorted(hits)[:args.limit]:
            print(f"0x{rva:X}\t{cls}")
        print(f"-- {len(hits)} vtables", file=sys.stderr)
        return 0

    wanted = {rva for rva, classes in tables.items()
              if any(args.target.lower() in cls.lower() for cls in classes)}
    if not wanted:
        print("no vtable matched", file=sys.stderr)
        return 1
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    text = next(entry for entry in image.sections if entry[0] == ".text")
    _, va, _, raw, rsize, _ = text
    hits = []
    for instruction in md.disasm(image.data[raw:raw + rsize], image.base + va):
        if instruction.mnemonic != "lea" or len(instruction.operands) != 2:
            continue
        operand = instruction.operands[1]
        if operand.type != CS_OP_MEM:
            continue
        resolved = (instruction.address + instruction.size + operand.mem.disp) - image.base
        if resolved in wanted:
            hits.append((instruction.address - image.base, resolved))
    for site, resolved in hits[:args.limit]:
        print(f"0x{site:X}\t-> vtable 0x{resolved:X}")
    print(f"-- {len(hits)} references", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
