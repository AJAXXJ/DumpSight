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
)
from tools.es_util import get_es_client
from tools.pgvector_util import get_pgvector_util
from agent.case_library.retrieve import get_retrieval


def test_client_core_analyse():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "DEBUG": False,
        }
    )

    client = app.test_client()

    response = client.post(
        "/api/client/report_crash",
        json={
            "client_id": "123",
            "pid": "54551",
            "timestamp": 1776052805,
        },
    )

    print(response.get_json())


def test_client_live_monitor():
    app = create_app()
    with app.app_context():
        client = app.test_client()

        test_payload = {"client_id": "123"}

        response = client.post(
            "/api/client/heartbeat",
            data=json.dumps(test_payload),
            content_type="application/json",
        )

        print(response.get_json())


def test_log_parse():
    app = create_app()

    with app.app_context():
        client_id = "123"
        pid = "130253"

        metrics_1s = log_1s_tool({"client_id": client_id, "pid": pid, "seconds": 20})
        metrics_5s = log_5s_tool({"client_id": client_id, "pid": pid, "seconds": 20})

        stat_1s = log_1s_statistic(metrics_1s)
        stat_5s = log_5s_statistic(metrics_5s)
        llm_prompt = build_llm_features(stat_1s, stat_5s, metrics_1s)
        print("1s日志解析:\n")
        print(stat_1s)
        print("5s日志解析:\n")
        print(stat_5s)
        print("LLM输入:\n")
        print(llm_prompt)
        print("stop")


# 导入案例
def load_cases_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    inserted_ids = []
    for case in cases:
        try:
            case_id = case_insert_service(case)
            inserted_ids.append(case_id)
            print(f"已插入案例: {case_id}")
        except Exception as e:
            print(f"插入案例失败: {case.get('case_id')}，错误: {e}")

    print(f"共插入 {len(inserted_ids)} 条案例")
    return inserted_ids


def test_hybrid_retrieval():
    app = create_app()

    # file_path = "agent/case_library/store/data/dpdk_crash_cases.json"
    with app.app_context():
        # 清空案例库
        # clear_case_library()

        # 写入案例
        # load_cases_from_json(file_path)

        # query = "DPDK 应用发生 SIGSEGV 信号导致的空指针解引用崩溃，崩溃函数为 rte_mbuf_raw_alloc，调用路径为 main 至 rte_pktmbuf_alloc 再到 rte_mbuf_raw_alloc，涉及 mempool 和 mbuf 子系统，缺失 librte_malloc 库。"

        # results = search_cases_es_pg(query=query, top_k=5)
        # print("检索结果:")
        # for r in results:
        #     print(r)

        retrieval = get_retrieval()

        state = {
            "description": "DPDK 应用发生 SIGSEGV 信号导致的空指针解引用崩溃，崩溃函数为 rte_mbuf_raw_alloc，调用路径为 main 至 rte_pktmbuf_alloc 再到 rte_mbuf_raw_alloc，涉及 mempool 和 mbuf 子系统，缺失 librte_malloc 库。"
        }

        results = retrieval.search(state)
        print("检索结果:")
        for r in results:
            print(r)


from click.testing import CliRunner
from dumpsight import monitor  # 你的命令函数

def test_monitor_basic():
    runner = CliRunner()

    result = runner.invoke(
        monitor,
        [
            "/workspace/test/dpdk_crash_oom -l 0 -n 4",
            "--file_prefix=dpdk_crash_oom"
        ]
    )

    print(result.output)

    assert result.exit_code == 0
    assert "DPDK running command executed successfully" in result.output

if __name__ == "__main__":

    # test_hybrid_retrieval()
    from config import config
    monitor_core(config)

    # test_client_core_analyse()
    # test_client_live_monitor()
    # test_log_parse()
    # pass
