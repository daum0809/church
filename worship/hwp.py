"""한글 문서(.hwp / .hwpx)에서 글자만 꺼냅니다. 한 문단(표 칸 포함)이 한 줄."""

import re
import struct
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree


class HwpError(Exception):
    pass


def extract_text(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".hwpx" or zipfile.is_zipfile(path):
        return _hwpx_text(path)
    if ext == ".hwp":
        return _hwp_text(path)
    if ext in (".txt", ".text"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise HwpError(f"{path.name}: .hwp 또는 .hwpx 파일이 아닙니다.")


# ------------------------------------------------------------------ HWPX (zip + XML)

def _hwpx_text(path):
    lines = []
    with zipfile.ZipFile(path) as z:
        sections = sorted((n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
                          key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
        if not sections:
            raise HwpError(f"{path.name}: 본문(section)을 찾지 못했습니다.")
        for name in sections:
            root = ElementTree.fromstring(z.read(name))
            for para in root.iter():
                if _local(para.tag) != "p":
                    continue
                parts = []
                for run in para:  # 바로 아래 run 만 (표 안 문단은 따로 처리됨)
                    if _local(run.tag) != "run":
                        continue
                    for el in run:
                        tag = _local(el.tag)
                        if tag == "t":
                            parts.append(_t_text(el))
                        elif tag == "tab":
                            parts.append("\t")
                        elif tag in ("lineBreak",):
                            parts.append("\n")
                lines.append("".join(parts))
    return "\n".join(lines)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _t_text(el):
    out = [el.text or ""]
    for child in el:
        if _local(child.tag) == "tab":
            out.append("\t")
        elif _local(child.tag) == "lineBreak":
            out.append("\n")
        out.append(child.tail or "")
    return "".join(out)


# ------------------------------------------------------------------ HWP 5.0 (OLE 바이너리)

PARA_TEXT = 67  # HWPTAG_BEGIN(16) + 51
# 8글자(16바이트)를 차지하는 제어 문자
_WIDE_CONTROLS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def _hwp_text(path):
    try:
        import olefile
    except ImportError as e:
        raise HwpError("olefile 패키지가 필요합니다: pip install -r requirements.txt") from e
    if not olefile.isOleFile(str(path)):
        raise HwpError(f"{path.name}: 한글(HWP 5.0) 문서가 아닙니다.")
    with olefile.OleFileIO(str(path)) as ole:
        header = ole.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", header, 36)[0]
        compressed, encrypted, distribute = flags & 1, flags & 2, flags & 4
        if encrypted:
            raise HwpError(f"{path.name}: 암호가 걸린 문서입니다. 암호를 풀고 저장해 주세요.")
        if distribute:
            raise HwpError(f"{path.name}: 배포용 문서입니다. 일반 문서로 저장해 주세요.")
        sections = sorted((e for e in ole.listdir() if e[0] == "BodyText" and e[1].startswith("Section")),
                          key=lambda e: int(e[1][7:]))
        lines = []
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                data = zlib.decompress(data, -15)
            lines.extend(para_texts(data))
    return "\n".join(lines)


def para_texts(data):
    """섹션 레코드에서 문단 글자(PARA_TEXT)만 꺼냅니다."""
    out, pos = [], 0
    while pos + 4 <= len(data):
        head = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        tag, size = head & 0x3FF, (head >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if tag == PARA_TEXT:
            out.append(_decode(data[pos:pos + size]))
        pos += size
    return out


def _decode(raw):
    chars, i, n = [], 0, len(raw) // 2
    while i < n:
        code = struct.unpack_from("<H", raw, i * 2)[0]
        if code < 32:
            if code == 9:
                chars.append("\t")
            elif code == 10:
                chars.append("\n")
            i += 8 if code in _WIDE_CONTROLS else 1
            continue
        chars.append(chr(code))
        i += 1
    return "".join(chars).rstrip("\r")
