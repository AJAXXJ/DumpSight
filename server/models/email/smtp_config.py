from sqlalchemy import BigInteger, Column, Integer, String
from server.models.base_model import BaseModel


class SmtpConfig(BaseModel):
    __tablename__ = "smtp_config"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host = Column(String(255))
    port = Column(Integer)
    use_ssl = Column(Integer)
    sender = Column(String(255))
    username = Column(String(255))
    password = Column(String(255))
    enabled = Column(Integer)
