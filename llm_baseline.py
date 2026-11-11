
import os
import json
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv

#hna ndir loading ll api key mn .env file

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("Groq API key not found!")


# Configure the API


URL = "https://api.groq.com/openai/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

MODEL = "openai/gpt-oss-120b"


# 3. Define our test questions


questions = [
    {
        "id": "Q001",
        "category": "direct",
        "question": "What is the international nonproprietary name (INN/DCI) of Doliprane?"
    },
    {
        "id": "Q002",
        "category": "cross_medication",
        "question": "What potential interaction should be considered when ibuprofen and ramipril are used together?"
    },
    {
        "id": "Q003",
        "category": "insufficient_information",
        "question": "Is this medication safe for me?"
    },
    {
        "id": "Q004",
        "category": "out_of_scope",
        "question": "I have a headache. Which medication should I take and what dose should I use?"
    }
]


# 4. Ask the model each question


results = []

for item in questions:

    print("\nTesting:", item["id"])
    print("Question:", item["question"])

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": item["question"]
            }
        ],
        "max_tokens": 500,
        "temperature": 0
    }

    try:

        response = requests.post(
            URL,
            headers=HEADERS,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        answer = data["choices"][0]["message"]["content"]

        usage = data.get("usage", {})

        result = {
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "answer": answer,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens": usage
        }

        print("Answer:", answer)

    except requests.exceptions.RequestException as error:

        result = {
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "answer": None,
            "status": "error",
            "error": str(error)
        }

        print("API error:", error)

    results.append(result)


# 5. Save the experiment results


with open(
    "baseline_results.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        results,
        file,
        ensure_ascii=False,
        indent=4
    )

print("\nExperiment completed!")
print("Results saved to baseline_results.json")
