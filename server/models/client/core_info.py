from sqlalchemy import Column, Integer, String, Text

from server.models.base_model import BaseModel


class CoreInfo(BaseModel):

    __tablename__ = "core_info"
    
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    client_id = Column(String(255), nullable=True, unique=True)

    pid = Column(String(255), nullable=True)

    timestamp = Column(String(255), nullable=True)

    prompt = Column(Text, nullable=True)

    output = Column(Text, nullable=True)

    preprocess_time = Column(Integer)

    analyse_time = Column(Integer)
