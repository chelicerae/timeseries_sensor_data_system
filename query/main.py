from fastapi import FastAPI, HTTPException, Depends, Query
from typing import Any, Tuple
from datetime import datetime
import os
import asyncpg
import asyncio

app = FastAPI()

DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "sensors")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

# Global async connection pool
db_pool: asyncpg.pool.Pool | None = None


async def create_db_pool(max_retries=5, delay=3):
    for attempt in range(1, max_retries + 1):
        try:
            pool = await asyncpg.create_pool(
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                host=DB_HOST,
                min_size=1,
                max_size=5,
            )
            print("Database pool created")
            return pool
        except Exception as e:
            print(f"Attempt {attempt}: DB not ready yet ({e})")
            if attempt < max_retries:
                await asyncio.sleep(delay)
            else:
                raise


@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await create_db_pool()


@app.on_event("shutdown")
async def shutdown_event():
    global db_pool
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed")


async def run_query(query: str, params: Tuple = ()) -> Any:
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetch(query, *params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_range")
async def get_data(
    sensor_id: str,
    start: datetime,
    end: datetime,
) -> dict:
    query = """
        SELECT * 
        FROM sensor_data
        WHERE sensor_id = $1
          AND timestamp >= $2
          AND timestamp <= $3
        ORDER BY timestamp
    """
    rows = await run_query(query, (sensor_id, start, end))
    return {"data": [dict(row) for row in rows]}


@app.get("/min")
async def get_min_value(
    sensor_id: str,
    start: datetime,
    end: datetime,
) -> dict:
    query = """
        SELECT MIN(value) AS min_value
        FROM sensor_data
        WHERE sensor_id = $1
          AND timestamp >= $2
          AND timestamp <= $3
    """
    result = await run_query(query, (sensor_id, start, end))
    return {"min_value": result[0]["min_value"] if result else None}


@app.get("/hourly")
async def get_hourly_data(sensor_id: str) -> list[dict]:
    query = """
    SELECT bucket AS timestamp,
           avg_value AS avg,
           min_value AS min,
           max_value AS max,
           samples
    FROM measurement_hourly
    WHERE sensor_id = $1
    ORDER BY bucket;
    """
    result = await run_query(query, (sensor_id,))
    return [
        {
            "timestamp": r["timestamp"],
            "avg": r["avg"],
            "min": r["min"],
            "max": r["max"],
            "samples": r["samples"],
        }
        for r in result
    ]


@app.get("/")
async def root() -> dict:
    return {"message": "Async Query API is running"}
