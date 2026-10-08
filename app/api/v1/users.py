from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import UserLogin
from app.services.user_service import UserService
from app.repository.user_repository import UserRepository
from app.schemas.user import UserSignup
from app.core.exception import InvalidCredentialsError, UserAlreadyExistsError

router = APIRouter(prefix="/v1/users", tags=["Users"])

# @router.get("/{user_id}")
# async def get_user_with_tasks(
#     user_id: UUID,
#     db: AsyncSession = Depends(get_db)
# ):
#     service = UserService(db)
#     result = await service.get_user_with_tasks(user_id)
    
#     if result is None:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     return result 

# @router.post("/create-test-user")
# async def create_test_user(
#     db: AsyncSession = Depends(get_db)
# ):
#     user_repo = UserRepository(db)

#     user = await user_repo.create_user(
#         name="Renu",
#         email="renu@gmail.com"
#     )

#     return {
#         "id": user.id,
#         "name": user.name,
#         "email": user.email
#     }
    
@router.post("/signup", status_code=201)
async def register(
    user: UserSignup,
    db: AsyncSession = Depends(get_db)
):
    try:
        service = UserService(db)
        created_user = await service.create_user(user_email=user.email, user_name=user.name, user_password=user.password)
        return {
            "message": "User created successfully",
            "user": {
                "id": created_user.id,
                "name": created_user.name,
                "email": created_user.email
            }
        }
    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=400,
            detail="User already exists"
        )
        
@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = UserService(db)
        
        jwt_token = await service.login(user_email=form_data.username, user_password=form_data.password)
        
        return {
            "access_token": jwt_token,
            "token_type": "bearer"
        }
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail="Invalid Credentials"
        )