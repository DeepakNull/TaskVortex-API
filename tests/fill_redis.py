import redis 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

payload = "A" * 5000 #50kb

i = 0

while True:
    i+=1 
    r.set(f"dummy:{i}", payload)
    
    if i % 100 == 0:
        print(f"Inserted {i} keys")