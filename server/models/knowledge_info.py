from sqlalchemy import JSON, Column, Integer, String, Text

from server.models.base_model import BaseModel


class KnowledgeInfo(BaseModel):

    __tablename__ = "knowledge_info"

    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    filename = Column(String(255), nullable=True)

    filetype = Column(String(255), nullable=True)

    content_type = Column(String(255), nullable=True)

    filesize = Column(String(255), nullable=True)

    size = Column(String(255), nullable=True)

    etag = Column(String(255), nullable=True)

    key = Column(String(255), nullable=True)

    bucket = Column(String(255), nullable=True)
