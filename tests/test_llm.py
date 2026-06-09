
from runtime.llm.client import LLMClient

client = LLMClient.from_env()
print("Model:", client.model)
print("Endpoint:", client._endpoint())

messages = [
    {"role": "user", "content": "Say hello!"}
]

response = client.chat(
    messages=messages,
    temperature=0.3,
    max_tokens=4096,
)
print("Response:", response)
