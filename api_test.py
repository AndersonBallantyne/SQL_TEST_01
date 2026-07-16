import os
from dotenv import load_dotenv
import anthropic

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic() # reads ANTHROPIC_API_KEY from the environment automatically

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say hello in one sentence"}]

)

for block in response.content:
    if block.type == "text":
        print(block.text)

print("stop_reason:", response.stop_reason)
print("usage:", response.usage)
