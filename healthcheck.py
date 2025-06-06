import requests

res = requests.get("https://api.ecfr.gov/v1/titles")
print(res.status_code)
print(res.text)
