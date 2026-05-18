import requests

headers = {
    "Authorization": "Bearer sk-proj-YOUR_OPENAI_KEY_HERE"
}

response = requests.get(
    "https://api.openai.com/v1/models",
    headers=headers
)
print(response.status_code)
print(response.text)