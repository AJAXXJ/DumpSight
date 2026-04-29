from server.models.client.core_info import CoreInfo


def add_core_info(
    client_id=None,
    pid=None,
    timestamp=None,
    report=None,
    process_time=None,
    analyse_time=None,
    total_time=None,
    state=None
):
    client_info = CoreInfo.create(
        client_id=client_id,
        pid=pid,
        timestamp=timestamp,
        report=report,
        process_time=process_time,
        analyse_time=analyse_time,
        total_time=total_time,
        state=state
    )
    return client_info["id"]

def get_core_list():
    return CoreInfo.all()

def get_core_page(page_index, page_size):
    return CoreInfo.page(int(page_index), int(page_size))


def get_core_info(client_id, pid, timestamp):
    return CoreInfo.get(client_id=client_id, pid=pid, timestamp=timestamp)