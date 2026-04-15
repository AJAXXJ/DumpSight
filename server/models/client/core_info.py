from sqlalchemy import JSON, Column, Integer, String, Text

from server.models.base_model import BaseModel


class CoreInfo(BaseModel):

    __tablename__ = "core_info"
    
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    client_info_id = Column(Integer, nullable=True)

    report = Column(Text, nullable=True)

    process_time = Column(Integer, nullable=True)

    analyse_time = Column(Integer, nullable=True)

    total_time = Column(Integer, nullable=True)