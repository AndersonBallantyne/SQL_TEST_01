import os
from dotenv import load_dotenv
import anthropic
from tools import run_sql_query, list_tables, describe_table

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic()

tools = [
    {
        "name": "run_sql_query",
        "description": "Run a read-only SQL query against the appdb Postgres database and return the resulting rows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SQL SELECT query to run aginst the database."
                }
            },
            "required": ["sql"]
        }
    },

    {
        "name": "list_tables",
        "description": "List all table names available in the appdb database.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },

    {   "name": "describe_table",
        "description": "Get the column names and data types for a specific table in appdb.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "The name of the table to describe."
                }
            },
            "required": ["table_name"]
        }      
    }
]

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a small business database by writing and running SQL queries.

Database: appdb (PostgreSQL)

You don't know the schema in advance. Use list_tables to see what tables exist, and describe_table to see a table's columns before writing SQL against it.

When you need data to answer a question, use the run_sql_query tool. Only write SELECT queries — do not modify data.
"""


user_question = "How many customers do we have?"

messages = [{"role": "user", "content": user_question}]

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    tools=tools,
    messages=[{"role": "user", "content": user_question}]
)
for block in response.content:
    print(block)

print("stop_reason:", response.stop_reason)

tool_use_block = next(block for block in response.content if block.type == "tool_use")

result = run_sql_query(tool_use_block.input["sql"])

print(result)

messages.append({"role": "assistant", "content": response.content})
messages.append({
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": tool_use_block.id,
            "content": str(result)
        }
    ]
})

final_response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    tools=tools,
    messages=messages
)

for block in final_response.content:
    if block.type == "text":
        print(block.text)



