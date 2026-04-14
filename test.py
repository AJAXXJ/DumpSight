from flask import json
from agent.tools.fetch_data_tool import log_1s_tool
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


def test_core_parese():
    core_path = (
        "/home/test/core.dpdk_crash.456196.456196.11.1775139629.!home!test!dpdk_crash"
    )
    exe_path = "/home/test/dpdk_crash"
    log_path = "/home/test/dpdk_17751396297981.log"
    output_dir = "/home/test"
    core_extractor_result = run_core_extractor(
        [core_path, exe_path, log_path], output_dir
    )


if __name__ == "__main__":
    test_client_core_analyse()
    # test_client_live_monitor()
    # test_core_parese()
