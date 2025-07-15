import redis
import time
import random
r = redis.Redis(host='localhost', port=6379, decode_responses=True, db=6)
# r.flushdb()

# Example device/component data
devices = ['Device1', 'Device2', 'Device3']
components = {
    'Device1': ['Component1', 'Component2'],
    'Device2': ['Component3', 'Component4'],
    'Device3': ['Component5']
}

# # Set devices list
r.delete('devices')
for d in devices:
    r.rpush('devices', d)
    # Ensure the components list is fresh for each device
    r.delete(f'{d}:components')
    for comp in components[d]:
        try:
            r.rpush(f'{d}:components', comp)
        except redis.RedisError as e:
            print(f"Error pushing component {comp} for device {d}: {e}")

while True:
    now = time.time()
    # for device in devices:
    device = random.choice(devices)
    # Set heartbeat for each device
    r.set(f'{device}:heartbeat', now)
    # Set components list for each device
    # r.delete(f'{device}:components')
    time.sleep(0.1)  # Simulate some delay
    comp = random.choice(components[device])
            # Set component status and execution time
    r.set(f'{device}:{comp}:status', 'running')
    r.set(f'{device}:{comp}:execution_time', round(random.uniform(0.3, 1.5), 3))
    r.set(f'{device}:{comp}:start_execution', now)
    # for comp in components[device]:


    # Add a log entry for demo
    r.rpush('log', f'Test log entry from Python at {time.strftime("%Y-%m-%d %H:%M:%S")}')
    time.sleep(2)

print("Redis test data populated.")
