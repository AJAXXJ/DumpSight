from sqlalchemy import JSON, Boolean, Column, Integer, String

from server.models.base_model import BaseModel


class CrashCaseMeta(BaseModel):

    __tablename__ = "crash_case_meta"
    
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    case_id = Column(String(255), nullable=True)

    signal_name = Column(String(255), nullable=True)

    crash_type = Column(String(255), nullable=True)

    crash_function = Column(String(255), nullable=True)

    dpdk_lib_missing = Column(Boolean, nullable=True)

    dpdk_subsystems = Column(JSON, nullable=True)
    
    missing_libs = Column(JSON, nullable=True)

    root_cause = Column(String(255), nullable=True)

    repair_steps = Column(JSON,  nullable=True)



