from server.models.client.client_info import ClientInfo

def add_client_info(client_id, dpdk_context):
    client_info = ClientInfo.create(
        client_id=client_id,
        dpdk_context=dpdk_context
    )
    return client_info.id
    

def get_client_info(client_id):
    client_info = ClientInfo.get(client_id=client_id)
    return client_info.to_dict() if client_info else None


def page_client_info(page_num,page_size):
    return ClientInfo.page(page_num, page_size)
