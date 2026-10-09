from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repository.task_repository import TaskRepository
from app.repository.user_repository import UserRepository
from sqlalchemy.exc import IntegrityError
from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.core.exception import InvalidCredentialsError, UserAlreadyExistsError
import asyncio

import logging 

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db:AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.task_repo = TaskRepository(db)
        
    # async def get_user_with_tasks(self, user_id: int):
    #     user = await self.user_repo.get_user_by_id(user_id)

    #     return user 
    
    async def create_user(self, user_email: str, user_name: str, user_password: str):
        existing_user = await self.user_repo.get_user_by_email(user_email)
        if existing_user:
            logger.warning("Attempt to create user with existing email")
            raise UserAlreadyExistsError()

        hashed_password = await asyncio.to_thread(hash_password, user_password)
        user_obj = User(name=user_name, email=user_email, hashed_password=hashed_password)
        await self.user_repo.create_user(user_obj)

        try:
            await self.db.commit()
        except IntegrityError:
            # Two simultaneous signups with the same email: the unique constraint wins.
            await self.db.rollback()
            raise UserAlreadyExistsError()

        await self.db.refresh(user_obj)
        logger.info("User registered", extra={"context": {"user_id": user_obj.id}})
        return user_obj

    async def login(self, user_email: str, user_password: str):
        user = await self.user_repo.get_user_by_email(user_email)

        # Always run bcrypt, even for unknown emails, so timing doesn't reveal which emails exist.
        hashed = user.hashed_password if user else DUMMY_HASH
        password_matches = await asyncio.to_thread(verify_password, user_password, hashed)

        if user is None or not password_matches:
            logger.warning("Invalid login attempt")
            raise InvalidCredentialsError()

        access_token = create_access_token(data={"sub": str(user.id)})
        logger.info("User logged in", extra={"context": {"user_id": user.id}})
        return access_token
#         """
        
#         why sequential instead of doing concurrent 
#         user, tasks = await asyncio.gather(
#         self.user_repo.get_user_by_id(user_id),
#         self.task_repo.get_tasks_by_user(user_id)
#     )
#         classic tradeoff
# Concurrent approach

# Pros:

# Lower latency
# Faster responses

# Cons:

# May waste resources

# Best when:

# both queries are usually needed
# invalid requests are rare
# Sequential approach

# Pros:

# Efficient DB usage
# No wasted queries

# Cons:

# Higher latency

# Best when:

# second query depends on first
# invalid requests happen often"""
        