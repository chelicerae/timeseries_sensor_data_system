import redis
import time
import psycopg2
import os
import sys


# Line that forces prints to appear in docker logs.
sys.stdout.reconfigure(line_buffering=True)

DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "sensors")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

for _ in range(10):
    try:
        conn = psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        print("Connected to database.")
        break
    except psycopg2.OperationalError:
        print("Database not ready, retrying in 2s...")
        time.sleep(2)
else:
    raise RuntimeError("Database connection failed after multiple attempts.")

conn.autocommit = True
cur = conn.cursor()

STREAM_NAME = "sensor_stream"
GROUP_NAME = "workers"
CONSUMER_NAME = "worker-1"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
print(f"Created consumer group '{GROUP_NAME}' on stream '{STREAM_NAME}'")


def process_message(data: dict) -> None:
    print(
        f"Processing record: {data['sensor_id']}, {data['value']}, {data['timestamp']}"
    )

    sensor_id = data["sensor_id"]
    value = float(data["value"])
    timestamp = data["timestamp"]

    cur.execute(
        """
        INSERT INTO sensor_data (sensor_id, timestamp, value)
        VALUES (%s, %s, %s)
        """,
        (sensor_id, timestamp, value),
    )
    print("Record is processed.")


while True:
    messages = r.xreadgroup(
        GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=1, block=5000
    )

    if messages:
        for stream, entries in messages:
            for msg_id, data in entries:
                try:
                    process_message(data)
                    r.xack(STREAM_NAME, GROUP_NAME, msg_id)
                except Exception as e:
                    print(f"Error processing {msg_id}: {e}")
    else:
        print("No new messages, waiting...")
        time.sleep(1)
