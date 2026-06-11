from flask import json
from agent.case_library.retrieve import get_retrieval
from agent.client.llm_client import completion_stream
from agent.tools.fetch_data_tool import log_1s_tool, log_5s_tool
from agent.tools.telemetry_feature_tool import (
    build_llm_features,
    log_1s_statistic,
    log_5s_statistic,
)

from monitor.coredump_extractor.analyzer import extract_ldd_paths
from monitor.coredump_extractor.main import run_core_extractor
from monitor.events import monitor_core
from server.models.client.case_info import CaseInfo
from server.app import create_app
from tools.logger import logger
from server.service.case_service import (
    es_search,
    search_cases,
    search_cases_es_pg,
    save_case_to_vs,
    case_insert_service,
    clear_case_library,
    recall_search_cases_es_pg,
)
from tools.es_util import get_es_client
from tools.pgvector_util import get_pgvector_util
from agent.case_library.retrieve import get_retrieval
from tools.vector_store_util import get_vector_store
import itertools

# def test_client_core_analyse():
#     app = create_app()
#     app.config.update(
#         {
#             "TESTING": True,
#             "DEBUG": False,
#         }
#     )

#     client = app.test_client()

#     response = client.post(
#         "/api/client/report_crash",
#         json={
#             "client_id": "123",
#             "pid": "54551",
#             "timestamp": 1776052805,
#         },
#     )

#     print(response.get_json())


# def test_client_live_monitor():
#     app = create_app()
#     with app.app_context():
#         client = app.test_client()

#         test_payload = {"client_id": "123"}

#         response = client.post(
#             "/api/client/heartbeat",
#             data=json.dumps(test_payload),
#             content_type="application/json",
#         )

#         print(response.get_json())


# def test_log_parse():
#     app = create_app()

#     with app.app_context():
#         client_id = "123"
#         pid = "130253"

#         metrics_1s = log_1s_tool({"client_id": client_id, "pid": pid, "seconds": 20})
#         metrics_5s = log_5s_tool({"client_id": client_id, "pid": pid, "seconds": 20})

#         stat_1s = log_1s_statistic(metrics_1s)
#         stat_5s = log_5s_statistic(metrics_5s)
#         llm_prompt = build_llm_features(stat_1s, stat_5s, metrics_1s)
#         print("1s日志解析:\n")
#         print(stat_1s)
#         print("5s日志解析:\n")
#         print(stat_5s)
#         print("LLM输入:\n")
#         print(llm_prompt)
#         print("stop")


# # 导入案例
# def load_cases_from_json(file_path):
#     with open(file_path, "r", encoding="utf-8") as f:
#         cases = json.load(f)

#     inserted_ids = []
#     for case in cases:
#         try:
#             case_id = case_insert_service(case)
#             inserted_ids.append(case_id)
#             print(f"已插入案例: {case_id}")
#         except Exception as e:
#             print(f"插入案例失败: {case.get('case_id')}，错误: {e}")

#     print(f"共插入 {len(inserted_ids)} 条案例")
#     return inserted_ids


def test_hybrid_retrieval():
    app = create_app()

    file_path = "agent/case_library/store/data/dpdk_crash_cases.json"
    # file_path = "agent/case_library/store/data/library.json"
    with app.app_context():
        # # 清空案例库
        # clear_case_library()

        # # 写入案例
        # load_cases_from_json(file_path)

        group_truth_ids = [
            "0539e673-f977-4c8a-b6ea-93463999b68c",
            "89936eca-eed3-4621-8c84-29e2f8279798",
            "8d0d87e3-0b35-4597-be9d-b480b9fe2bb2",
            "338fb12e-18f5-41aa-a179-6ced71b45b3d",
            "20aaa065-5b6a-44fe-a3b9-41e9c6f9770f",
        ]

        query = "DPDK 应用发生 SIGSEGV 信号导致的空指针解引用崩溃，崩溃函数为 rte_mbuf_raw_alloc，调用路径为 main 至 rte_pktmbuf_alloc 再到 rte_mbuf_raw_alloc，涉及 mempool 和 mbuf 子系统，缺失 librte_malloc 库。"
        # 可调参数列表
        rrf_k_list = [30, 60, 100]
        alpha_list = [0, 0.5, 1]
        beta_list = [0, 0.5, 1]
        top_k = [1, 3, 5, 7, 10]

        results = []

        for rrf_k, alpha, beta, top_k in itertools.product(
            rrf_k_list, alpha_list, beta_list, top_k
        ):
            es_ids, pg_ids, fused_ids = recall_search_cases_es_pg(
                query=query,
                group_truth_ids=group_truth_ids,
                top_k=top_k,
                top_k_es=top_k * 2,
                top_k_pg=top_k * 2,
                rrf_k=rrf_k,
                alpha=alpha,
                beta=beta,
            )

            # 计算召回率
            es_recall = len(set(es_ids) & set(group_truth_ids)) / len(group_truth_ids)
            pg_recall = len(set(pg_ids) & set(group_truth_ids)) / len(group_truth_ids)
            fused_recall = len(set(fused_ids) & set(group_truth_ids)) / len(
                group_truth_ids
            )

            # 记录融合检索优于单路的组合
            if fused_recall >= max(es_recall, pg_recall):
                results.append(
                    {
                        "top_k": top_k,
                        "top_k_es": top_k,
                        "top_k_pg": top_k,
                        # "rrf_k": rrf_k,
                        # "alpha": alpha,
                        # "beta": beta,
                        "es_recall": es_recall,
                        "pg_recall": pg_recall,
                        "fused_recall": fused_recall,
                        # "fused_ids": fused_ids,
                    }
                )

        # 按融合召回率排序
        results.sort(key=lambda x: x["fused_recall"], reverse=True)

        print(f"共找到 {len(results)} 种融合检索优于单路检索的参数组合")
        for r in results:
            print(r)


# from click.testing import CliRunner
# from dumpsight import monitor  # 你的命令函数

# def test_monitor_basic():
#     runner = CliRunner()

#     result = runner.invoke(
#         monitor,
#         [
#             "/workspace/test/dpdk_crash_oom -l 0 -n 4",
#             "--file_prefix=dpdk_crash_oom"
#         ]
#     )

#     print(result.output)

#     assert result.exit_code == 0
#     assert "DPDK running command executed successfully" in result.output

from monitor.coredump_extractor.main import run_core_extractor

if __name__ == "__main__":

    test_hybrid_retrieval()
    # from config import config
    # monitor_core(config)

    # test_client_core_analyse()
    # test_client_live_monitor()
    # test_log_parse()
    # pass
    pass
