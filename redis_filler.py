import redis
import time
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
r.flushdb()
while True:
    r.set('heartbeat', 'alive')
    time.sleep(2)
    r.rpush('processor:CPU1', 'CompA', 'CompB')
    r.rpush('processor:CPU2', 'CompC')
print("Redis test data populated.")
