"""OpenXML 结构验证 — ZIP 完整性 + .rels 引用 + Content_Types"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from typing import BinaryIO

from .result import ErrorCode, ValidationError

# xlsx 必需文件
_REQUIRED_FILES = [
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
]

# OOXML 命名空间
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def parse_rels(xml_content: bytes) -> dict[str, str]:
    """解析 .rels 文件，返回 {rId: target} 映射"""
    rels: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_content)
        for rel in root.findall(f"{{{_REL_NS}}}Relationship"):
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if rid and target:
                rels[rid] = target
    except ET.ParseError:
        pass
    return rels


def parse_content_types(xml_content: bytes) -> tuple[set[str], set[str]]:
    """
    解析 [Content_Types].xml，返回:
    - 已声明的 PartName 集合（不含前导 /）
    - 已声明的 Extension 集合（含前导 .）
    """
    parts: set[str] = set()
    extensions: set[str] = set()
    try:
        root = ET.fromstring(xml_content)
        for override in root.findall(f"{{{_CT_NS}}}Override"):
            part_name = override.get("PartName", "")
            # PartName 以 / 开头，去掉前导 /
            if part_name.startswith("/"):
                part_name = part_name[1:]
            if part_name:
                parts.add(part_name)
        for default_elem in root.findall(f"{{{_CT_NS}}}Default"):
            ext = default_elem.get("Extension", "")
            if ext:
                extensions.add("." + ext)
    except ET.ParseError:
        pass
    return parts, extensions


def check_structure(file_path: str) -> list[ValidationError]:
    """
    验证 xlsx 的 ZIP 结构完整性:
    1. 有效的 ZIP 文件
    2. [Content_Types].xml 存在且合法
    3. _rels/.rels 存在
    4. xl/workbook.xml 存在
    5. 所有 .rels 引用的文件都存在
    """
    errors: list[ValidationError] = []

    try:
        zf = zipfile.ZipFile(file_path, "r")
    except zipfile.BadZipFile:
        errors.append(ValidationError(
            severity="error",
            category="structure",
            sheet="",
            cell="",
            code=ErrorCode.STRUCTURE_INVALID_ZIP,
            message="文件不是有效的 ZIP/XLSX 格式",
        ))
        return errors

    try:
        names = set(zf.namelist())

        # 检查必需文件
        for req in _REQUIRED_FILES:
            if req not in names:
                errors.append(ValidationError(
                    severity="error",
                    category="structure",
                    sheet="",
                    cell="",
                    code=ErrorCode.STRUCTURE_MISSING_FILE,
                    message=f"缺少必需文件: {req}",
                    detail={"missing_file": req},
                ))

        # 如果关键文件缺失，后续检查无意义
        if errors:
            return errors

        # 检查 _rels/.rels 引用
        if "_rels/.rels" in names:
            rels = parse_rels(zf.read("_rels/.rels"))
            for rid, target in rels.items():
                # .rels 中的 target 可能以 / 开头或直接是相对路径
                normalized = target.lstrip("/")
                if normalized and normalized not in names:
                    errors.append(ValidationError(
                        severity="error",
                        category="structure",
                        sheet="",
                        cell="",
                        code=ErrorCode.STRUCTURE_BROKEN_RELS,
                        message=f".rels 引用不存在的文件: {target}（{rid}）",
                        detail={
                            "relationship_id": rid,
                            "target": target,
                        },
                    ))

        # 检查 xl/_rels/workbook.xml.rels 引用
        wb_rels_path = "xl/_rels/workbook.xml.rels"
        if wb_rels_path in names:
            rels = parse_rels(zf.read(wb_rels_path))
            for rid, target in rels.items():
                # 去掉前导 / 并拼接为 xl/ 下的相对路径
                clean = target.lstrip("/")
                if clean.startswith("xl/"):
                    full_target = clean
                else:
                    full_target = f"xl/{clean}"
                if full_target not in names and clean not in names:
                    errors.append(ValidationError(
                        severity="error",
                        category="structure",
                        sheet="",
                        cell="",
                        code=ErrorCode.STRUCTURE_BROKEN_RELS,
                        message=f"workbook.xml.rels 引用不存在的文件: {target}（{rid}）",
                        detail={
                            "relationship_id": rid,
                            "target": target,
                        },
                    ))

        # 检查 [Content_Types].xml 声明
        if "[Content_Types].xml" in names:
            declared_parts, declared_extensions = parse_content_types(
                zf.read("[Content_Types].xml")
            )
            # 检查所有文件是否被 Content_Types 覆盖
            for name in names:
                if name == "[Content_Types].xml":
                    continue
                # 检查 Override 或 Default
                is_covered = name in declared_parts
                if not is_covered:
                    # 检查扩展名是否在 Default 中
                    _, ext = _split_extension(name)
                    if ext and ext.lower() in {e.lower() for e in declared_extensions}:
                        is_covered = True
                # .rels 文件通常有默认声明，不强制检查
                if not is_covered and not name.endswith(".rels"):
                    errors.append(ValidationError(
                        severity="warning",
                        category="structure",
                        sheet="",
                        cell="",
                        code=ErrorCode.STRUCTURE_MISSING_CONTENT_TYPE,
                        message=f"文件 {name} 未在 [Content_Types].xml 中声明",
                        detail={"file": name},
                    ))

    finally:
        zf.close()

    return errors


def _split_extension(filename: str) -> tuple[str, str]:
    """分割文件名和扩展名"""
    if "." in filename:
        idx = filename.rfind(".")
        return filename[:idx], filename[idx:]
    return filename, ""
