from sqlalchemy import BigInteger, Column, String

from server.models.base_model import BaseModel


class AlertRuleRecipient(BaseModel):

    __tablename__ = "alert_rule_recipient"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    rule_id = Column(BigInteger, nullable=False)

    email = Column(String(255), nullable=False)
