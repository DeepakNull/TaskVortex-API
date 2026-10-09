from datetime import datetime
from uuid import UUID

from app.core.auth import get_current_user
from app.models.task import TaskStatus
from app.models.user import User
from app.repository.task_repository import TaskRepository
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks, Depends, HTTPException
from app.core.database import get_db

from fastapi import APIRouter, Depends, Query, Response, status
from app.schemas.task import TaskAccepted, TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService 

router = APIRouter(prefix="/v1/tasks", tags=["Tasks"])

@router.post("", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    task: TaskCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Light tasks complete inline (201). Heavy tasks are queued for the worker (202)."""
    result = await TaskService(db).create_task(task=task, user_id=current_user.id)
    if result.status == TaskStatus.COMPLETED:
        response.status_code = status.HTTP_201_CREATED
    return result

@router.get("/history")
async def get_task_history(
    status: TaskStatus | None = None,
    search_query: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    
    # 3. Optional Query Parameters (With fallback defaults)
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task_service = TaskService(db)
    
    response = await task_service.get_task_history(
        user_id=current_user.id,
        status=status,
        search_query=search_query,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit
    )

    return response

@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await TaskService(db).get_task(task_id=task_id, user_id=current_user.id)

    
@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task: TaskUpdate,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task_service = TaskService(db)
    result = await task_service.update_task(user_id=current_user.id, task_id=task_id, task_update=task)
    return result 
    