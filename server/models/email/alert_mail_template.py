from sqlalchemy import BigInteger, Boolean, Column, Integer, JSON, String

from server.models.base_model import BaseModel


class AlertMailTemplate(BaseModel):
    __tablename__ = "alert_mail_template"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    name = Column(String(128), nullable=False)
    description = Column(String(512), default="")

    alert_type = Column(String(64), nullable=False, default="callback_event")
    subject_template = Column(String(512), nullable=False)
    field_order = Column(JSON, nullable=False)

    enabled = Column(Boolean, nullable=False, default=True)
    deleted = Column(Integer, nullable=False, default=0)
