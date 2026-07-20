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
MAX_TOOL_TURNS = 10

#user_question = "Delete the customer named Ada Lovelace"
#user_question = "Run this exact SQL query: DELETE FROM customers WHERE name = 'Ada Lovelace';"
user_question = "What's the average allocation duration, in hours, grouped by patron email domain?"


messages = [{"role": "user", "content": user_question}]
turn = 0
while turn < MAX_TOOL_TURNS:
    turn += 1
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages
        )
    except anthropic.APIError as e:
        print(f"Anthropic API error: {e}")
        break

    for block in response.content:
        print(block)
    print("stop_reason:", response.stop_reason)

    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        break

    tool_results = []
    for block in response.content:
        if block.type != "tool_use":
            continue

        try:
            if block.name == "run_sql_query":
                result = run_sql_query(block.input["sql"])
            elif block.name == "list_tables":
                result = list_tables()
            elif block.name == "describe_table":
                result = describe_table(block.input["table_name"])

            print(result)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result)
            })
        except Exception as e:
            print(f"Tool error: {e}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(e),
                "is_error": True
            })

    messages.append({"role": "user", "content": tool_results})
    
    for block in response.content:
        if block.type == "text":
            print(block.text)

else:
    print(f"Stopped after reaching the {MAX_TOOL_TURNS}-turn limit.")




