import logging

from agent.tools.fetch_data_tool import *

logger = logging.getLogger(__name__)

class Tool:
    def __init__(self, func, name):
        self.func = func
        self.name = name
        logger.info("Tool registered: %s", self.name)

    def invoke(self, inputs):
        # logger.info("Invoking tool: %s with inputs: %s", self.name, inputs)
        result = self.func(inputs)
        # logger.info("Tool %s output: %s", self.name, result)
        return result
    

_tools = {
    "client_info": Tool(client_info_tool, "client_info"),
    "dpdk_info": Tool(dpdk_info_tool, "dpdk_info"),
    "core_info": Tool(core_info_tool, "core_info"),
    "log_1s": Tool(log_1s_tool, "log_1s"),
    "log_5s": Tool(log_5s_tool, "log_5s"),
}


def get_tools():
    logger.info("All tools registered: %s", list(_tools.keys()))
    return _tools