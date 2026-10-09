import aio_pika 
from app.core.config import settings

connection: aio_pika.RobustConnection | None = None 
channel: aio_pika.abc.AbstractChannel | None = None 

DLX_NAME = "task_dlx"
DLQ_NAME = "task_queue.dlq"

async def declare_topology(channel: aio_pika.abc.AbstractChannel):
    # Declare the main queue and it's dead-letter queue. Safe to call from api and worker. 
    dlx = await channel.declare_exchange(DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx, routing_key="task_queue")
    
    return await channel.declare_queue(
        "task_queue",
        durable=True, 
        arguments = {
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": "task_queue"
        }
    )

async def connect_rabbitmq():
    global connection, channel 
    RABBITMQ_URL : str = settings.RABBITMQ_URL
    connection = await aio_pika.connect_robust(
        RABBITMQ_URL
    )
    
    channel = await connection.channel()
    
    await declare_topology(channel)
    
async def close_rabbitmq():
    if connection:
        await connection.close() 