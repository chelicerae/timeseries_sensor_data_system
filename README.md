## Architecture overview

This is my solution for lightweight scalable time series ingestion and reading pipeline.  

I used the following technologies:
- I used Redis as lightweight Kafka-esque analogue as scalable solution. Redis is populated by API endpoint with batches of data.
- As target database for timeseries storage I used TimescaleDB. Timescale DB is populated by records from Redis.
- I used FastAPI as a python library for backend API logic. 

This project consists of three modules:
- Ingest module.
- Query module.
- Worker Module.

We will go through each of them in more detail. Examples of requests and their format will be provided afterwards.

### `./ingest`

Ingest module contains single API endpint: `/ingest`. 

It receives batches (lists of JSON objects) of data and pushes it to Redis. In this way even if we receive lot's of batches from sensors (processes that supposedly push data to out system) this messages will be stored in Redis and our DB will not be overflown with insert jobs.

### `./worker`

Worker module gets records from Redis and pushes them to TimescaleDB via `INSERT` queries. 

### `./query`

Query module reads data from timescale DB.

It contains following endpoints:
- `/get_range` - returns records from time series in given range.
- `/min` - as an example of aggregation query, this endpoint returns MIN aggregation function on given time range.
- `/hourly` - as an example of downsampling data query, this endpoint returns aggregation function from given downsample windows from TimescaleDB `timescaledb.continuous` materialized view. 


### `./timescaledb_init`

This folder contains `init.sql` that contains all the DDL statements required for our time-series DB to function. It creates main table, `sensor_data`, that contains all datapoints pushed by sensors and creates materialized view, `measurement_hourly`, that contains hourly aggregations as an example of TimescaleDB downsampling functionality.


## How to launch: demo instructions

This projects runs in docker, so to lunch it is usually needed to run two commands:
1) `docker compose down -v`
2) `docker compose up --build`

First command is needed to clear the environment of all entities and processes that could have survived last docker run.

After docker image is launched and ready you should see something like this in logs:

```
query        | INFO:     Application startup complete.
query        | INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
worker       | Connected to database.                                                                                   
worker       | Created consumer group 'workers' on stream 'sensor_stream'
```

Now we need to push some data to Redis and TimescaleDB. To do this we must trigger our ingest process. I use postman for that, but `curl` is also a viable option. I use this request:
```
POST
http://localhost:8000/ingest
Content-Type: application/json
Body:
[
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T21:00:00Z", "value": 25.3},
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T21:01:00Z", "value": 26.7},
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T21:05:00Z", "value": 30.7},
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T22:00:00Z", "value": 10.0},
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T22:06:00Z", "value": 12.0},
    {"sensor_id": "sensor-1", "timestamp": "2025-10-22T22:06:00Z", "value": 114.0}
]
```

After we launch this request we must see the following result:
```
worker       | Processing record: sensor-1, 25.3, 2025-10-22T21:00:00Z
ingest_api   | INFO:     172.18.0.1:45824 - "POST /ingest HTTP/1.1" 200 OK
worker       | Record is processed.
worker       | Processing record: sensor-1, 26.7, 2025-10-22T21:01:00Z
worker       | Record is processed.                                                                                     
worker       | Processing record: sensor-1, 30.7, 2025-10-22T21:05:00Z                                                  
worker       | Record is processed.                                                                                     
worker       | Processing record: sensor-1, 10.0, 2025-10-22T22:00:00Z                                                  
worker       | Record is processed.                                                                                     
worker       | Processing record: sensor-1, 12.0, 2025-10-22T22:06:00Z                                                  
worker       | Record is processed.                                                                                     
worker       | Processing record: sensor-1, 114.0, 2025-10-22T22:06:00Z                                                 
worker       | Record is processed.         
```

If we have this result in logs, that means that our data went from Redis to TimescaleDB and we can move on to reading data. 

To get records in given time period let's run this request:
```
GET
http://localhost:8001/get_range?sensor_id=sensor-1&start=2025-10-22T21:00:00Z&end=2025-10-22T21:00:01Z
```

This should give us the following result:
```JSON
{
    "data": [
        {
            "id": 1,
            "timestamp": "2025-10-22T21:00:00Z",
            "sensor_id": "sensor-1",
            "value": 25.3
        }
    ]
}
```

Next let's try getting a minimum value from given time range. Let's make this request:
```
GET
http://localhost:8001/min?sensor_id=sensor-1&start=2025-10-22T21:00:00Z&end=2026-10-22T21:00:01Z
```

We must get the following result:
```
{
    "min_value": 10.0
}
```

And lastly let's see how our automatic TimescaleDB downsampling functionality works. This can be a bit tricky. Currently the frequence of updates or downsampling materialized view is set to one minute as per DDL:
```SQL
SELECT add_continuous_aggregate_policy('measurement_hourly',
    start_offset => INTERVAL '7 days',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');
```

That means that in our demo when we make the following request it can return us an empty list.
```
GET
http://localhost:8001/hourly?sensor_id=sensor-1
```

Response:
```JSON
[]
```

That means that `measurement_hourly` materialized view was not updated yet. So if we don't want to wait for 1 minute for it to update we can update it manually. To do it we need to execute the following commands:
 - `docker compose exec timescaledb psql -U postgres -d sensors` to enter TimescaleDB cli.
 - `CALL refresh_continuous_aggregate('measurement_hourly', NULL, NULL);` to manually update out materialized view.

Now we need to get the following response:
 ```JSON
 [
    {
        "timestamp": "2025-10-22T21:00:00Z",
        "avg": 27.566666666666666,
        "min": 25.3,
        "max": 30.7,
        "samples": 3
    },
    {
        "timestamp": "2025-10-22T22:00:00Z",
        "avg": 45.333333333333336,
        "min": 10.0,
        "max": 114.0,
        "samples": 3
    }
]
 ```

 That's it! That's the demo. There some thing that could have also been done here, but this features where out of time budget. They include:
 - Some env vars could be put into separate config to have more DRY solution.
 - In place of `./requirements.txt` I could have user `poetry` for more dependency control. 
 - Probably I could have created better development feedback loop.
 - On large scale I could have created a separate DB duplicate solely for reading data. This way reading and writing jobs would be separated and there would be less pressure on DBs.
 - I could have written more try/except clauses for more safety and readability of logs.

### Useful commands

For debugging Redis:
- `docker exec -it redis redis-cli`
- `XRANGE sensor_stream - +`

For debugging TimescaleDB:
- `docker exec -it timescaledb psql -U postgres -d sensors`
- `CALL refresh_continuous_aggregate('measurement_hourly', NULL, NULL);`

For reading logs:
- `docker compose logs -f worker`
