import datetime
import os
from urllib.parse import quote, unquote
import uuid
from flask import current_app
from agent.knowledge.chunking import download_and_chunk
from agent.knowledge.embedding import embed_chunks, embed_query
from server.repository.knowledge_repository import (
    add_fileinfo,
    delete_fileinfo_by_id,
    get_fileinfo_by_etag,
    get_fileinfo_by_id,
    get_fileinfo_page,
)
from server.tools.exception_handler import BusinessException
from tools.minio_util import get_minio_util
from tools.vector_store_util import get_vector_store


def knowledge_upload_service(filename):
    """
    前端获取上传 minio 签名
    存储结构：knowledge/{date}/{uuid}_{filename}
    """
    # 日期目录
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # 文件后缀
    ext = os.path.splitext(filename)[1]
    base_name = os.path.splitext(filename)[0]

    # 唯一 ID
    uid = uuid.uuid4().hex[:8]

    # 组合安全文件名
    safe_filename = f"{uid}_{base_name}{ext}"

    # object path
    object_name = f"knowledge/{date_str}/{safe_filename}"

    # 生成 MinIO 预签名 URL
    url = get_minio_util().get_upload_url(object_name)
    return {"url": url, "object_name": object_name}


def knowledge_handle_minio_event_service(minio_event_info):
    """
    处理 minio 事件回调函数
    """
    event_name = minio_event_info.get("EventName", "")  # 事件类型

    for record in minio_event_info.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]  # 桶名称
        raw_key = record["s3"]["object"]["key"]
        object_key = unquote(raw_key)
        size = record["s3"]["object"]["size"]  # 文件大小
        content_type = record["s3"]["object"]["contentType"]  # 文件类型
        etag = record["s3"]["object"]["eTag"]  # 文件md5用于去重

        filename_with_prefix = os.path.basename(object_key)
        name, ext = os.path.splitext(filename_with_prefix)
        file_ext = ext.lstrip(".")
        name = name.split("_", 1)[1] if "_" in name else name
        filename = name

        size_mb = f"{round(size / 1024 / 1024, 2)} MB"

        file_info = {
            "filename": filename,
            "bucket": bucket,
            "key": object_key,
            "size": size,
            "filesize": size_mb,
            "filetype": file_ext,
            "content_type": content_type,
            "etag": etag,
        }

        if event_name == "s3:ObjectCreated:Put":
            # 触发 RAG 入库流程
            handle_file_upload(file_info)


def handle_file_upload(file_info):
    """
    处理文件上传
    """
    if get_fileinfo_by_etag(file_info["etag"]):
        # 已经存在相同的文件不触发入库流程
        return

    # 触发数据库保存
    add_fileinfo(**file_info)

    # 触发向量库保存
    vs = get_vector_store(file_info["bucket"], current_app.config["VECTOR_DIM"])

    # 下载文件并切片，携带元数据用于 RAG 溯源
    chunks = download_and_chunk(
        file_info["key"], file_info["filetype"], with_metadata=True
    )

    # 向量化，返回对齐后的 (valid_chunks, vectors)
    valid_chunks, vectors = embed_chunks(chunks)

    # 存储，使用对齐后的 valid_chunks
    vs.store(file_info["etag"], valid_chunks, vectors)


def knowledge_delete_service(file_id):
    """
    知识库文件删除
    """
    file_info = get_fileinfo_by_id(file_id)
    if not file_info:
        raise BusinessException("知识库尚未存在该文件")

    # 向量库删除
    get_vector_store(file_info["bucket"], current_app.config["VECTOR_DIM"]).delete(
        file_info["etag"]
    )

    # minio删除
    get_minio_util().delete_file(file_info["key"])

    # 数据库删除
    delete_fileinfo_by_id(file_id)


def knowledge_page_service(page_index, page_size):
    """
    分页获取知识库文件
    """
    fileinfo_page = get_fileinfo_page(page_index, page_size)
    raw_fileinfo_list = fileinfo_page["items"]

    fileinfo_list = []
    for fileinfo in raw_fileinfo_list:

        url = (
            f"{get_minio_util().endpoint}/{fileinfo['bucket']}/{quote(fileinfo['key'])}"
        )

        fileinfo_list.append(
            {
                **fileinfo,
                "url": url,
                "create_time": datetime.datetime.fromisoformat(
                    fileinfo["create_time"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return {
        "total": fileinfo_page["total"],
        "page": fileinfo_page["page"],
        "page_size": fileinfo_page["page_size"],
        "items": fileinfo_list,
    }


def knowledge_search_service(query, bucket="dpdk_knowledge", top_k=5):
    """
    知识库语义检索
    """
    if not query or not query.strip():
        raise BusinessException("查询文本不能为空")

    # query embedding
    query_vector = embed_query(query)

    # 向量检索
    vs = get_vector_store(bucket, current_app.config["VECTOR_DIM"])
    results = vs.search(query_vector, top_k=top_k)

    return [
        {
            "id": r.id,
            "content": r.content,
            "score": round(r.score, 4),
            "filetype": r.metadata.get("filetype"),
            "key": r.metadata.get("source_key"),
        }
        for r in results
    ]
