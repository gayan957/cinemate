"""
The smallest possible LLM call. Proves your key and connection work.

Usage:
    python agents/orchestrator/hello_llm.py
"""
import sys

from groq import Groq

sys.path.insert(0, ".")
from shared.config import GROQ_API_KEY, LLM_MODEL

client = Groq(api_key=GROQ_API_KEY)

response = client.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    max_tokens=50,
)

print(response.choices[0].message.content)