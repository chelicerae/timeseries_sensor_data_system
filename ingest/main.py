from fastapi import FastAPI, Request
import redis
import os


app = FastAPI(title="Sensor Ingest Service")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_QUEUE = "sensor_data_queue"
STREAM_NAME = "sensor_stream"

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@app.post("/ingest")
async def ingest(request: Request) -> dict:
    data = await request.json()

    msg_ids = []
    for record in data:
        msg_id = r.xadd(STREAM_NAME, record)
        msg_ids.append(msg_id)

    return {"status": "ok", "msg_ids": msg_ids, "ingested": len(data)}
