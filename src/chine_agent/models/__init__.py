"""ORM 模型。新增模型后在这里导入,Alembic 才能发现它（第 7 步）。"""

from chine_agent.models.base import Base

__all__ = ["Base"]
