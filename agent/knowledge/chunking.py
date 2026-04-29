import io
import asyncio
import logging
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import pdfplumber
import pytesseract
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from tools.minio_util import get_minio_util

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """文件解析失败"""


class UnsupportedFileTypeError(ParserError):
    """不支持的文件类型"""


@dataclass
class Chunk:
    text: str
    index: int  # 第几块
    source_key: str  # MinIO key
    filetype: str
    char_start: int  # 原文字符起始位置
    metadata: dict = field(default_factory=dict)  # 扩展字段（页码等）


_SPLITTERS = {
    "default": RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
        add_start_index=True,
    ),
    "code": RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\nclass ", "\ndef ", "\n\n", "\n", " ", ""],
        add_start_index=True,
    ),
    "table": RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n", ",", ""],
        add_start_index=True,
    ),
    "html": RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n## ", "\n\n", "\n", "。", ".", " "],
        add_start_index=True,
    ),
}

_FILETYPE_SPLITTER_MAP = {
    "py": "code",
    "js": "code",
    "ts": "code",
    "java": "code",
    "go": "code",
    "cpp": "code",
    "csv": "table",
    "html": "html",
    "htm": "html",
}


_PARSER_REGISTRY: dict = {}


def register_parser(*extensions):
    """
    注册文件类型解析器的装饰器。
    用法：
        @register_parser("txt", "md")
        def parse_plain(raw: bytes) -> str: ...
    """

    def decorator(fn):
        for ext in extensions:
            _PARSER_REGISTRY[ext.lower()] = fn
        return fn

    return decorator


def get_parser(ext: str):
    """按扩展名取解析器，找不到则抛出 UnsupportedFileTypeError。"""
    parser = _PARSER_REGISTRY.get(ext.lower())
    if parser is None:
        raise UnsupportedFileTypeError(
            f"不支持的文件类型: .{ext}，" f"已支持: {sorted(_PARSER_REGISTRY.keys())}"
        )
    return parser


@register_parser("txt", "md", "log")
def _parse_plain(raw: bytes) -> str:
    """普通文本解析器"""
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        raise ParserError(f"纯文本解析失败: {e}") from e


@register_parser("csv")
def _parse_csv(raw: bytes) -> str:
    """CSV 解析器（保留换行结构供 table 分块器处理）"""
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        raise ParserError(f"CSV 解析失败: {e}") from e


@register_parser("docx")
def _parse_docx(raw: bytes) -> str:
    """docx 解析器"""
    try:
        doc = Document(io.BytesIO(raw))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise ParserError(f"DOCX 解析失败: {e}") from e


@register_parser("pdf")
def _parse_pdf(raw: bytes) -> str:
    """
    PDF 解析器：
    - 优先使用 pdfplumber 提取文字层
    - 若某页无文字（扫描件），降级到 pytesseract OCR
    """
    parts = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text and text.strip():
                    parts.append(text)
                else:
                    logger.warning(f"第 {page_num} 页无文字层，尝试 OCR")
                    try:
                        img = page.to_image(resolution=200).original
                        ocr_text = pytesseract.image_to_string(img, lang="chi_sim+eng")
                        if ocr_text.strip():
                            parts.append(ocr_text)
                            logger.info(f"第 {page_num} 页 OCR 成功")
                        else:
                            logger.warning(f"第 {page_num} 页 OCR 未识别到文字")
                    except Exception as ocr_err:
                        logger.error(f"第 {page_num} 页 OCR 失败: {ocr_err}")
    except Exception as e:
        raise ParserError(f"PDF 解析失败: {e}") from e

    if not parts:
        raise ParserError("PDF 未提取到任何文本（文件可能损坏或为纯图片）")

    return "\n\n".join(parts)


@register_parser("html", "htm")
def _parse_html(raw: bytes) -> str:
    """
    HTML 解析器：
    - 去除 script/style
    - 提取正文文本
    - 保留基本换行结构
    """
    try:
        html = raw.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")

        # 去掉无用标签
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # 获取文本（用换行分隔，方便后续 chunk）
        text = soup.get_text(separator="\n")

        # 清理空行
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        return "\n\n".join(lines)

    except Exception as e:
        raise ParserError(f"HTML 解析失败: {e}") from e


def split_by_paragraph(
    text: str,
    filetype: str = "default",
) -> list[str]:
    """
    使用 RecursiveCharacterTextSplitter 对文本分块。
    按 filetype 选择对应分块策略，返回纯字符串列表。
    """
    splitter_key = _FILETYPE_SPLITTER_MAP.get(filetype.lower(), "default")
    splitter = _SPLITTERS[splitter_key]
    chunks = splitter.split_text(text)
    return [c.strip() for c in chunks if c.strip()]


def split_with_metadata(
    text: str,
    source_key: str,
    filetype: str,
) -> list[Chunk]:
    """
    分块并附加元数据，用于 RAG 溯源。
    返回 list[Chunk]，每个 Chunk 携带位置、来源等信息。
    """
    splitter_key = _FILETYPE_SPLITTER_MAP.get(filetype.lower(), "default")
    splitter = _SPLITTERS[splitter_key]
    documents = splitter.create_documents([text])

    chunks = []
    for i, doc in enumerate(documents):
        content = doc.page_content.strip()
        if not content:
            continue
        chunks.append(
            Chunk(
                text=content,
                index=i,
                source_key=source_key,
                filetype=filetype,
                char_start=doc.metadata.get("start_index", 0),
                metadata=doc.metadata,
            )
        )
    return chunks


def download_and_chunk(
    key: str,
    filetype: str,
    with_metadata: bool = False,
) -> list[str] | list[Chunk]:
    """
    从 MinIO 下载文件，按 filetype 选解析器提取文本，再分块。

    Args:
        key:           MinIO 对象 key
        filetype:      文件扩展名，如 "pdf"、"docx"
        with_metadata: True 时返回 list[Chunk]，False 时返回 list[str]
    """
    raw = get_minio_util().get_file_bytes(key)
    parser = get_parser(filetype)
    text = parser(raw)

    if with_metadata:
        return split_with_metadata(text, source_key=key, filetype=filetype)
    return split_by_paragraph(text, filetype=filetype)


_executor = ThreadPoolExecutor(max_workers=4)


async def download_and_chunk_async(
    key: str,
    filetype: str,
    with_metadata: bool = False,
) -> list[str] | list[Chunk]:
    """
    download_and_chunk 的异步版本，适合 FastAPI 等异步框架。
    IO/CPU 密集操作均在线程池中执行，不阻塞事件循环。
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        download_and_chunk,
        key,
        filetype,
        with_metadata,
    )


async def batch_chunk(
    files: list[dict],
    with_metadata: bool = False,
) -> dict[str, list[str] | list[Chunk] | None]:
    """
    批量并发处理多个文件。

    Args:
        files: [{"key": "...", "filetype": "pdf"}, ...]
        with_metadata: 是否携带元数据

    Returns:
        {key: chunks}，失败的 key 对应值为 None
    """
    tasks = [
        download_and_chunk_async(f["key"], f["filetype"], with_metadata) for f in files
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = {}
    for f, result in zip(files, results):
        if isinstance(result, Exception):
            logger.error(f"处理文件 {f['key']} 失败: {result}")
            output[f["key"]] = None
        else:
            output[f["key"]] = result

    return output
