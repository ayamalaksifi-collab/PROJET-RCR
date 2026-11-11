
import os
import requests
from dotenv import load_dotenv

# 1. Load the variables from .env
load_dotenv()

# 2. Retrieve our API key
api_key = os.getenv("GROQ_API_KEY")

# 3. Check that the key exists
if not api_key:
    raise ValueError("GROQ_API_KEY was not found!")

# 4. Define the API endpoint
url = "https://api.groq.com/openai/v1/chat/completions"

# 5. Prepare the request headers
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 6. Prepare the request body
data = {
    "model": "openai/gpt-oss-120b",
    "messages": [
        {
            "role": "user",
            "content": "Réponds juste : OK"
        }
    ]
}

# 7. Send the request
response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=60
)

# 8. Display the result
print("Status code:", response.status_code)

if response.status_code == 200:
    result = response.json()

    answer = result["choices"][0]["message"]["content"]

    print("Model response:", answer)

else:
    print("Error:", response.text)
