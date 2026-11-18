"""用户相关的业务逻辑。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chine_agent.core.exceptions import ConflictError
from chine_agent.core.security import hash_password
from chine_agent.models import User
from chine_agent.repositories.user_repository import UserRepository
from chine_agent.schemas.user import UserCreate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def create_user(self, data: UserCreate) -> User:
        if await self.users.get_by_username(data.username) is not None:
            raise ConflictError("用户名已存在")

        user = User(username=data.username, password_hash=hash_password(data.password))
        try:
            await self.users.add(user)
            await self.session.commit()
        except IntegrityError as e:
            # 两个请求同时创建同一用户名时，上面的检查可能都通过，由数据库唯一约束兜底
            await self.session.rollback()
            raise ConflictError("用户名已存在") from e
        return user
