import aio_pika 
from app.core.config import settings

connection: aio_pika.RobustConnection | None = None 
channel: aio_pika.abc.AbstractChannel | None = None 

async def connect_rabbitmq():
    global connection, channel 
    RABBITMQ_URL : str = settings.RABBITMQ_URL
    connection = await aio_pika.connect_robust(
        RABBITMQ_URL
    )
    
    channel = await connection.channel()
    
    await channel.declare_queue(
        "task_queue",
        durable=True,
    )
    
async def close_rabbitmq():
    if connection:
        await connection.close() 