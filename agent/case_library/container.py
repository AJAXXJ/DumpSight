from dataclasses import dataclass, field
from typing import Optional
from tools.logger import logger
from agent.config import config
from agent.case_library.retriever import Retriever


@dataclass
class Container:
    """
    轻量依赖容器，按需懒加载各组件。
    组件初始化失败时记录错误并标记不健康，不影响其他组件启动。
    """

    _retriever: Optional[Retriever] = field(default=None, repr=False)
    _healthy: dict = field(default_factory=dict, repr=False)


    @property
    def retriever(self) -> Retriever:
        """
        获取 Retriever 单例，首次访问时初始化。

        :raises RuntimeError: 初始化失败时抛出
        """
        if self._retriever is None:
            self._retriever = self._init("retriever", lambda: Retriever(vars(config)))
        return self._retriever

    def _init(self, name: str, factory):
        """
        执行组件初始化，捕获异常并更新健康状态。

        :param name: 组件名称（用于日志和健康标记）
        :param factory: 无参工厂函数，返回组件实例
        :raises RuntimeError: 初始化失败时抛出
        """
        try:
            instance = factory()
            self._healthy[name] = True
            logger.info(f"[Container] {name} 初始化成功")
            return instance
        except Exception as e:
            self._healthy[name] = False
            logger.error(f"[Container] {name} 初始化失败: {e}")
            raise RuntimeError(f"{name} 初始化失败: {e}") from e

    def health(self) -> dict:
        """
        返回各组件健康状态快照。

        :return: {"retriever": True/False, "generator": True/False, ...}
        """
        return dict(self._healthy)


container = Container()
