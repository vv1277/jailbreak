import requests

API = "http://localhost:3000"
keys = ["admin", "secret", "s3cretkey2019"]

for k in keys:
    response = requests.get(
        f"{API}/admin/users",
        headers={"X-Internal-Key": k}
    )

    print("key:", k)
    print("status:", response.status_code)
    print(response.text[:300])
    print("-" * 50)