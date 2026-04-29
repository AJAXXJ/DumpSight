# 统一导出 service 只需从这里引入
from agent.client.tools.client_info import ClientInfoTool
from agent.client.tools.client_list import ClientListTool
from agent.client.tools.dpdk_info import DpdkInfoTool
from agent.client.tools.dpdk_list import DpdkListTool
from agent.client.tools.log_info import LogInfoTool
from agent.client.tools.report_info import ReportInfoTool
from agent.client.tools.report_list import ReportListTool


ALL_TOOLS = [
    ClientInfoTool(),
    DpdkInfoTool(),
    LogInfoTool(),
    ClientListTool(),
    DpdkListTool(),
    ReportListTool(),
    ReportInfoTool(),
]
