from server.models.knowledge_info import KnowledgeInfo


def add_fileinfo(**kwargs):
    fileinfo = KnowledgeInfo.create(**kwargs)
    return fileinfo["id"]


def get_fileinfo_by_etag(etag):
    return KnowledgeInfo.get(etag=etag)


def get_fileinfo_by_id(file_id):
    return KnowledgeInfo.get(id=file_id)


def delete_fileinfo_by_id(file_id):
    return KnowledgeInfo.delete(id=file_id)


def get_fileinfo_page(page_index, page_size):
    return KnowledgeInfo.page(int(page_index), int(page_size))
