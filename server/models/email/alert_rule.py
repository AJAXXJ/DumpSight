from sqlalchemy import BigInteger, Column, String, Text

from server.models.base_model import BaseModel


class AlertRule(BaseModel):

    __tablename__ = "alert_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    name = Column(String(128), nullable=False)

    alert_type = Column(String(32), nullable=False)

    severity = Column(String(32), nullable=False)

    template_id = Column(BigInteger, nullable=True)

    template_name = Column(String(128), nullable=True)

    enabled = Column(BigInteger, nullable=True)

    remark = Column(Text, nullable=True)

    deleted = Column(BigInteger, nullable=True)
