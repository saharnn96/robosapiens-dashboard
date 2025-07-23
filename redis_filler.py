import redis
import time
import random
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
# r.flushdb()

# Example device/component data
devices = ['Device1', 'Device2', 'Device3']
nodes = ['Monitor', 'Execute', 'Analysis', 'Plan', 'Legitimate']

# # Set devices list
r.delete('devices:list')
for d in devices:
    r.rpush('devices:list', d)
    # Ensure the components list is fresh for each device
    r.delete(f'devices:{d}:nodes')
    for node in nodes:
        try:
            r.rpush(f'devices:{d}:nodes', node)
            r.set(f'devices:{d}:{node}:status', 'paused')
        except redis.RedisError as e:
            print(f"Error pushing component {node} for device {d}: {e}")

while True:
    now = time.time()
    # for device in devices:
    device = random.choice(devices)
    # Set heartbeat for each device
    r.set(f'devices:{device}:heartbeat', now)
    # Set components list for each device
    # r.delete(f'{device}:components')
    time.sleep(0.1)  # Simulate some delay
    node = random.choice(nodes)
            # Set component status and execution time
    r.set(f'devices:{device}:{node}:status', 'running')
    r.set(f'{node}:execution_time', round(random.uniform(0.3, 1.5), 3))
    r.set(f'{node}:start_execution', now)
    # Add a log entry for demo
    r.rpush(f'{node}:logs', f'Test log entry from {node} at {time.strftime("%Y-%m-%d %H:%M:%S")}')
    time.sleep(2)

print("Redis test data populated.")
