from sqlalchemy import BigInteger, Column, String, Text, TIMESTAMP, Enum
from server.models.base_model import BaseModel



class AlertMailLog(BaseModel):
    __tablename__ = "alert_mail_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sent_at = Column(TIMESTAMP)
    sender = Column(String(255))
    receivers = Column(Text)
    subject = Column(String(500))
    alert_level = Column(Enum("P1", "P2", "P3"))
    status = Column(Enum("success", "failed"))
    error_message = Column(Text)
