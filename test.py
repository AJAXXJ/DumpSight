from flask import json
from agent.tools.fetch_data_tool import log_1s_tool, log_5s_tool
from agent.tools.telemetry_feature_tool import build_llm_features, log_1s_statistic, log_5s_statistic
from monitor.coredump_extractor.analyzer import extract_ldd_paths
from monitor.coredump_extractor.main import run_core_extractor
from server.app import create_app


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
        llm_prompt  = build_llm_features(stat_1s, stat_5s, metrics_1s)
        print("1s日志解析:\n")
        print(stat_1s)
        print("5s日志解析:\n")
        print(stat_5s)
        print("LLM输入:\n")
        print(llm_prompt)
        print("stop")


if __name__ == "__main__":
    # test_client_core_analyse()
    # test_client_live_monitor()
    # test_log_parse()
    pass
