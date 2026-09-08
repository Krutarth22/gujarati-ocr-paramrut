"""Bound admission across API processes; expired leases recover after worker loss."""
import os
import time
from redis import Redis

QUEUE_WAIT_SECONDS = 600
TASK_TIME_LIMIT = 1800
LEASE_SECONDS = QUEUE_WAIT_SECONDS + TASK_TIME_LIMIT + 300
MAX_ACTIVE_JOBS = int(os.getenv('MAX_ACTIVE_JOBS', '8'))
redis_client = Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
                               socket_connect_timeout=5, socket_timeout=5)
KEY = 'gujarati-ocr:active-jobs'


def reserve_job(task_id):
    return bool(redis_client.eval('''
        redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
        if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
        redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
        redis.call('EXPIRE', KEYS[1], ARGV[5])
        return 1
    ''', 1, KEY, time.time(), time.time() + LEASE_SECONDS,
        MAX_ACTIVE_JOBS, task_id, LEASE_SECONDS))


def release_job(task_id):
    redis_client.zrem(KEY, task_id)
