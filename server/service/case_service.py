import datetime
import time
import uuid
from flask import current_app
from agent.knowledge.chunking import Chunk
from agent.knowledge.embedding import embed_chunks
from tools.vector_store_util import get_vector_store
from agent.knowledge.embedding import embed_query
from tools.vector_store_util import get_vector_store
from tools.es_util import get_es_client
from server.repository.case_repository import add_case, update_case
from flask import current_app
from server.models.client.case_info import CaseInfo
import numpy as np


def render_case_embedding_text(case):
    """
    对应原 render_embedding_input_template，
    将 case 字段拼接为用于 embedding 的文本。
    """
    parts = []
    if case.get("signal_name"):
        parts.append(f"信号名称：{case['signal_name']}")
    if case.get("crash_type"):
        parts.append(f"崩溃类型：{case['crash_type']}")
    if case.get("anomaly_flags"):
        parts.append(f"异常标志：{', '.join(case['anomaly_flags'])}")
    if case.get("description"):
        parts.append(f"描述：{case['description']}")
    if case.get("root_cause"):
        parts.append(f"根因：{case['root_cause']}")
    if case.get("repair_steps"):
        parts.append(f"修复步骤：{case['repair_steps']}")
    return "\n\n".join(parts)


def save_case_to_vs(case, bucket="dpdk_case_lib"):
    """
    单条案例直接写入向量库
    """
    # 参数校验
    missing = [f for f in ("case_id", "description") if not case.get(f)]
    if missing:
        raise ValueError(f"缺少必填字段: {missing}")

    # 构造 embedding 文本
    embedding_text = render_case_embedding_text(case)

    # 构造 Chunk
    chunk = Chunk(
        text=embedding_text,
        index=0,
        source_key=f"{case['case_id']}",
        filetype="case",
        char_start=0,
        metadata={
            "case_id": case["case_id"],
            "signal_name": case.get("signal_name"),
            "crash_type": case.get("crash_type"),
            "crash_function": case.get("crash_function"),
            "anomaly_flags": case.get("anomaly_flags", []),
            "root_cause": case.get("root_cause"),
            "description": case.get("description"),
            "repair_steps": case.get("repair_steps"),
            "created_at": int(time.time()),
        },
    )

    # embedding + 写入向量库
    valid_chunks, vectors = embed_chunks([chunk])
    if not valid_chunks:
        raise ValueError(f"案例 embedding 结果为空: case_id={case['case_id']}")

    vs = get_vector_store(bucket, current_app.config["VECTOR_DIM"])
    vs.store(case["case_id"], valid_chunks, vectors)


def search_cases(
    query,
    bucket="dpdk_case_lib",
    top_k=5,
):
    """
    案例库语义检索
    """
    if not query.strip():
        raise ValueError("查询文本不能为空")

    # query embedding
    query_vector = embed_query(query)
    # print("查询向量长度:", len(query_vector))

    # 向量检索
    vs = get_vector_store(bucket, current_app.config["VECTOR_DIM"])
    raw = vs.search(query_vector, top_k=top_k)
    # print("检索结果条数:", len(raw))

    # 展开 metadata，拼装返回结构
    results = []
    for rank, r in enumerate(raw, start=1):
        meta = r.metadata or {}

        results.append(
            {
                "case_id": meta.get("case_id"),
                "signal_name": meta.get("signal_name"),
                "crash_type": meta.get("crash_type"),
                "crash_function": meta.get("crash_function"),
                "anomaly_flags": meta.get("anomaly_flags", []),
                "root_cause": meta.get("root_cause"),
                "repair_steps": meta.get("repair_steps"),
                "description": meta.get("description"),
                "score": r.score,
                "rank": rank,
                "source": "pgvector",
            }
        )

    return results


def es_search(query, index_name="dumpsight_cases", top_k=5):
    """
    ES 关键词检索
    """

    es = get_es_client()

    es_query = {
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "crash_function^5",
                            "description^3",
                            "log_feature^2",
                            "root_cause",
                        ],
                        "operator": "or",
                        "fuzziness": "AUTO",  # 允许拼写错误
                    }
                }
            }
        },
        "size": top_k,
    }

    resp = es.search(index_name, es_query)
    hits = resp["hits"]["hits"]

    # 获取最大 _score，用于归一化
    max_score = max(hit["_score"] for hit in hits) if hits else 1.0

    results = []
    for rank, hit in enumerate(hits, start=1):
        source = hit["_source"]
        raw_score = hit["_score"]

        results.append(
            {
                "case_id": source.get("case_id"),
                "signal_name": source.get("signal_name"),
                "crash_type": source.get("crash_type"),
                "crash_function": source.get("crash_function"),
                "anomaly_flags": source.get("anomaly_flags", []),
                "root_cause": source.get("root_cause"),
                "repair_steps": source.get("repair_steps"),
                "description": source.get("description"),
                "score": raw_score / max_score if max_score else 0,
                "rank": rank,
                "source": "es",
            }
        )

    return results


def deduplicate_by_content(results):
    """按 root_cause 去重，保留分数最高的"""
    seen = {}
    for r in results:
        content = r.get("root_cause", "").strip()
        if not content:
            continue
        score = r.get("score", 0)
        if content not in seen or score > seen[content]["score"]:
            seen[content] = r
    return list(seen.values())


def rrf_fusion(result_lists, k=60, alpha=0.7, beta=0.3):
    """
    Reciprocal Rank Fusion

    result_lists: [es_results, pg_results]
    k: 常用 60
    alpha: 原始 score 权重
    beta: RRF 排名权重

    返回：融合排序后的结果
    """

    merged = {}

    for results in result_lists:
        for r in results:
            cid = r.get("case_id")
            rank = r.get("rank")

            if not cid or not rank:
                continue

            rrf_score = 1.0 / (k + rank)
            # 原始score都已归一化
            score = alpha * r.get("score", 0) + beta * rrf_score

            if cid not in merged:
                merged[cid] = r.copy()
                merged[cid]["fused_score"] = score
            else:
                merged[cid]["fused_score"] += score

    # 排序
    final = list(merged.values())
    # final.sort(key=lambda x: x["score"], reverse=True)
    final.sort(key=lambda x: x["fused_score"], reverse=True)

    return final


def search_cases_es_pg(
    query, bucket="dpdk_case_lib", index_name="dumpsight_cases", top_k=5
):
    """
    ES + PGVector + RRF 融合检索
    """

    if not query.strip():
        raise ValueError("查询文本不能为空")

    # 双路检索
    es_results = es_search(query, index_name=index_name, top_k=top_k)

    pg_results = search_cases(query, bucket=bucket, top_k=top_k)

    # RRF 融合
    # fused = rrf_fusion([es_results, pg_results])
    fused = rrf_fusion([es_results, pg_results], k=60, alpha=0, beta=1)

    # 截断
    return fused[:top_k]


def case_insert_service(case: dict):
    """
    新增 case: DB + ES + pgvector
    """
    # mysql
    if not case.get("case_id"):
        case["case_id"] = str(uuid.uuid4())

    add_case(**case)

    if not case.get("case_id"):
        raise ValueError("case_id 必填")

    es_doc = {
        "case_id": case.get("case_id"),
        "signal_name": case.get("signal_name"),
        "crash_type": case.get("crash_type"),
        "crash_function": case.get("crash_function"),
        "description": case.get("description"),
        "root_cause": case.get("root_cause"),
        "log_feature": case.get("log_feature"),
        "anomaly_flags": case.get("anomaly_flags", []),
        "repair_steps": case.get("repair_steps"),
    }

    # 写 ES
    es = get_es_client()
    es.index_doc(
        index_name="dumpsight_cases",
        doc_id=case["case_id"],
        document=es_doc,
    )

    # 写向量库
    save_case_to_vs(case)

    return case["case_id"]


def case_get_service(case_id):
    return CaseInfo.get(id=case_id)


def case_update_service(case_id: str, updates: dict):
    """
    更新 case
    """
    # mysql
    updated = update_case(case_id, updates)
    if not updated:
        raise ValueError("case 不存在")

    # es
    es = get_es_client()
    es_doc = {
        "case_id": case_id,
        "signal_name": updates.get("signal_name"),
        "crash_type": updates.get("crash_type"),
        "crash_function": updates.get("crash_function"),
        "description": updates.get("description"),
        "root_cause": updates.get("root_cause"),
        "log_feature": updates.get("log_feature"),
        "anomaly_flags": updates.get("anomaly_flags", []),
    }

    es.update_doc(index_name="dumpsight_cases", doc_id=case_id, document=es_doc)

    # pg
    vs = get_vector_store("dpdk_case_lib", current_app.config["VECTOR_DIM"])
    vs.delete(case_id)

    save_case_to_vs({**updated, **updates})

    return True


def case_delete_service(id: str):
    """
    删除 case
    """
    # 根据案例id查询case
    case = CaseInfo.get(id=id)
    if not case:
        raise ValueError("case 不存在")

    case_id = case["case_id"]

    # MySQL
    deleted = CaseInfo.delete(id=id)
    if not deleted:
        raise ValueError("case 不存在")

    #  ES
    es = get_es_client()
    try:
        es.client.delete(index="dumpsight_cases", id=case_id)
    except Exception:
        pass

    # PGVector
    vs = get_vector_store("dpdk_case_lib", current_app.config["VECTOR_DIM"])
    vs.delete(case_id)

    return True


def case_page_service(page_index=1, page_size=10):
    case_page = CaseInfo.page(page_index, page_size)
    raw_case_list = case_page["items"]

    case_list = []
    for case in raw_case_list:

        case_list.append(
            {
                "id": case["id"],
                "case_id": case["case_id"],
                "crash_type": case["crash_type"],
                "signal_name": case["signal_name"],
                "root_cause": case["root_cause"],
                "create_time": datetime.datetime.fromisoformat(
                    case["create_time"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return {
        "total": case_page["total"],
        "page": case_page["page"],
        "page_size": case_page["page_size"],
        "items": case_list,
    }


def clear_case_library():
    vs = get_vector_store("dpdk_case_lib", current_app.config["VECTOR_DIM"])
    es = get_es_client()

    # 获取所有 case
    all_cases = CaseInfo.all()
    for case in all_cases:
        case_id = case["case_id"]
        # 删除 MySQL
        CaseInfo.delete(id=case["id"])
        # 删除 ES
        try:
            es.client.delete(index="dumpsight_cases", id=case_id)
        except Exception:
            pass
        # 删除 PGVector
        vs.delete(case_id)

    print(f"已清空 {len(all_cases)} 条案例库")


def recall_search_cases_es_pg(
    query,
    group_truth_ids,
    bucket="dpdk_case_lib",
    index_name="dumpsight_cases",
    top_k=5,
    top_k_es=5,
    top_k_pg=5,
    rrf_k=60,
    alpha=0,
    beta=1,
):
    """
    ES + PGVector + RRF 融合检索
    """

    if not query.strip():
        raise ValueError("查询文本不能为空")

    # 双路检索
    es_results = es_search(query, index_name=index_name, top_k=top_k_es)

    pg_results = search_cases(query, bucket=bucket, top_k=top_k_pg)

    es_ids = [r["case_id"] for r in es_results]
    pg_ids = [r["case_id"] for r in pg_results]

    # RRF 融合
    # fused = rrf_fusion([es_results, pg_results])
    fused = rrf_fusion([es_results, pg_results], k=rrf_k, alpha=alpha, beta=beta)

    fused_ids = [r["case_id"] for r in fused]

    return es_ids, pg_ids, fused_ids[:top_k]


