from sqlalchemy import JSON, Column, Integer, String

from server.models.base_model import BaseModel


class ClientInfo(BaseModel):

    __tablename__ = "client_info"
    
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    client_id = Column(String(255), nullable=True, unique=True)

    dpdk_context = Column(JSON)
