from sqlalchemy import JSON, Boolean, Column, Integer, String

from server.models.base_model import BaseModel


class CaseInfo(BaseModel):

    __tablename__ = "case_info"

    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    case_id = Column(String(255), nullable=True)

    signal_name = Column(String(255), nullable=True)

    crash_type = Column(String(255), nullable=True)

    crash_function = Column(String(255), nullable=True)

    main_path = Column(String(255), nullable=True)

    dpdk_subsystems = Column(JSON, nullable=True)

    missing_libs = Column(JSON, nullable=True)

    root_cause = Column(String(255), nullable=True)

    repair_steps = Column(JSON, nullable=True)

    description = Column(String(255), nullable=True)

    log_feature = Column(JSON, nullable=True)

    reference_feature = Column(JSON, nullable=True)

    anomaly_flags = Column(JSON, nullable=True)
