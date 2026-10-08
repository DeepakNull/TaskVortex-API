from datetime import datetime
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifier import generate_uuid
from app.models.task import Task, TaskStatus
from app.repository.metrics_cache_repository import MetricsCacheRepository
from app.repository.task_repository import TaskRepository
from fastapi import BackgroundTasks, HTTPException
from uuid import UUID, uuid4
import asyncio
import json
from app.core.redis import redis_client

from app.core.database import AsyncSessionLocal

from app.schemas.task import TaskCreate, TaskUpdate
from app.core.logging import trace_id_var

from app.services.message_publisher import publish_message


import logging 

logger = logging.getLogger(__name__)

class TaskService:
    def __init__(self, db:AsyncSession):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.metrics_cache_repo = MetricsCacheRepository() 
        
    async def create_task(
        self, 
        task:TaskCreate, 
        user_id: UUID, 
        background_tasks: BackgroundTasks
        ) -> Task | dict:        
        
        if task.complexity == "light":
            
            task_obj = Task(
                title = task.title,
                description = task.description,
                priority = task.priority,
                task_type = task.task_type,
                payload = task.payload,
                status = TaskStatus.COMPLETED,
                user_id = user_id,
            )
            await self.task_repo.save(task_obj)
            await self.db.commit()
            await self.db.refresh(task_obj)
            
            logger.info(
            "Light task created",
            extra={
                "context": {
                    "task_id": task_obj.id,
                    "user_id": user_id,
                }
            }
        )
            
            #invalidate cache
            keys_to_delete = []
            async for key in redis_client.scan_iter(match=f"task_history:{user_id}:*"):
                keys_to_delete.append(key)
                
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
                
            logger.info(
                "Task history cache invalidated",
                extra={
                    "context": {
                        "user_id": user_id,
                        "deleted_keys": len(keys_to_delete),
                    }
                }
            )
            # keys = await redis_client.keys(f"task_history:{user_id}:*")
            # if keys:
            #     await redis_client.delete(*keys)
            return task_obj
        
        else:
            # token = uuid4()
            task_obj = Task(
                id=generate_uuid(),
                title = task.title,
                description = task.description,
                task_type = task.task_type,
                priority = task.priority,
                payload = task.payload,
                status = TaskStatus.QUEUED,
                user_id = user_id,
            )
            await self.task_repo.save(task_obj)
            
            await self.db.commit()
            await self.db.refresh(task_obj)
            
            await self.metrics_cache_repo.incr_ingested()
            
            logger.info(
                "Heavy task queued",
                extra={
                    "context": {
                        "task_id": task_obj.id,
                        "user_id": user_id,
                    }
                }
            )
            
            # #invalidate cache
            keys_to_delete = []
            async for key in redis_client.scan_iter(match=f"task_history:{user_id}:*"):
                keys_to_delete.append(key)
                
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
                
            await publish_message(
                            {
                                "task_id": str(task_obj.id),
                                "user_id": str(user_id),
                            }
                        )
                
            return {
                "task_id": task_obj.id,
                "status": task_obj.status,
                "message": "Task accepted for processing",
            }
    
            
    async def get_task_history(
        self, 
        user_id: UUID,
        status: TaskStatus | None,
        search_query: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        page: int = 1,
        limit: int = 10,) -> dict:
        if search_query:
            search_query = search_query.strip() 
            
        cache_key = (
            f"task_history:"
            f"{user_id}:"
            f"{status or 'all'}:"
            f"{search_query or 'none'}:"
            f"{start_date or 'none'}:"
            f"{end_date or 'none'}:"
            f"{page}:"
            f"{limit}"
        )
        cached_data = await redis_client.get(cache_key)

        if cached_data:
            print(trace_id_var.get())
            # print("Cache Hit")
            logger.info("Cache Hit",
                    extra={
                        "context": {
                            "user_id": user_id,
                            "cache_key": cache_key,
                        }
                    })
            
            return json.loads(cached_data)
        
        print(trace_id_var.get())

        # print("Cache Miss")
        logger.info("Cache miss",
                    extra={
                        "context": {
                            "user_id": user_id,
                            "cache_key": cache_key,
                        }
                    })
        
        
        tasks, total_count = await self.task_repo.get_paginated_tasks_for_user(
            user_id=user_id, 
            status=status, 
            search_query=search_query, 
            start_date=start_date, 
            end_date=end_date, 
            page=page, 
            limit=limit)
        tasks_data = []

        for task in tasks:
            tasks_data.append({
                "id": str(task.id),
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority,
                "payload": task.payload,
                "created_at": task.created_at.isoformat(),
            })
        response =  {
            "tasks": tasks_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": (total_count + limit - 1) // limit
            }
        }
        
        await redis_client.set(cache_key, json.dumps(response), ex=300)
        return response 
    
    async def update_task(self, task_id: UUID, user_id: UUID, task_update: TaskUpdate):
        task = await self.task_repo.get_task_for_update(task_id, user_id)
        
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        
        update_data = task_update.model_dump(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided for update")
        
        for key, value in update_data.items():
            setattr(task, key, value)
        
        await self.db.commit()
        await self.db.refresh(task)  #commit writes and refresh reads back
        
        logger.info(
            "Task updated",
            extra={
                "context": {
                    "task_id": task.id,
                    "user_id": user_id,
                    "updated_fields": list(update_data.keys())
                }
            }
        )
        
        keys_to_delete = []
        async for key in redis_client.scan_iter(match=f"task_history:{user_id}:*"):
            keys_to_delete.append(key)
            
        if keys_to_delete:
            await redis_client.delete(*keys_to_delete)
            
        logger.info(
                "Task history cache invalidated",
                extra={
                    "context": {
                        "user_id": user_id,
                        "deleted_keys": len(keys_to_delete),
                    }
                }
            )
            
        return task
