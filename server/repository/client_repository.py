from server.models.client.client_info import ClientInfo


def add_client_info(client_id, environment):

    client_info = ClientInfo.create(client_id=client_id, environment=environment)

    return client_info['id']


def update_client_heartbeat(client_id):
    ClientInfo.update(filters={"client_id": client_id}, updates={})


def get_client_info(client_id):
    client_info = ClientInfo.get(client_id=client_id)
    return client_info if client_info else None


def page_client_info(page_num, page_size):
    return ClientInfo.page(page_num, page_size)
