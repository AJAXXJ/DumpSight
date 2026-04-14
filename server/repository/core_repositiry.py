from server.models.client.core_info import CoreInfo


def add_core_info(
    client_info_id,
    crash_md_report,
    crash_json_report,
    process_time,
    analyse_time,
    total_time,
):
    client_info = CoreInfo.create(
        client_info_id=client_info_id,
        crash_md_report=crash_md_report,
        crash_json_report=crash_json_report,
        process_time=process_time,
        analyse_time=analyse_time,
        total_time=total_time,
    )
    return client_info['id']
