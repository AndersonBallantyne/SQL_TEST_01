import os
from dotenv import load_dotenv
import anthropic
#from tools import run_sql_query, list_tables, describe_table, save_dataframe
from tools import run_sql_query, list_tables, describe_table, save_dataframe, search_summaries

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
    },

    {
        "name": "save_dataframe",
        "description": "Persist a computed result (e.g. an aggregation you just calculated) to your own scratch workspace, so it can be reused in a later question. This only ever writes to your personal workspace - it cannot affect any of the main database tables.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "A short name for this saved result - lowercase letters, digits, and underscores only."
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names for the result, in order."
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "array"},
                    "description": "The rows of data to save, each a list of values matching the columns order."
                }
            },
            "required": ["table_name", "columns", "rows"]
        }
    },

    {
        "name": "search_summaries",
        "description": "Semantic search over allocation summaries (equipment descriptions). Use this for questions about the general kind or theme of equipment rather than an exact structured filter - it finds conceptually related items even without exact keyword matches. Returns a message, not an error, if nothing is sufficiently relevant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "A natural-language description of the kind of equipment or allocation you're looking for."
                }
            },
            "required": ["query_text"]
        }
    }
]

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a small business database by writing and running SQL queries.

Database: appdb (PostgreSQL)

You don't know the schema in advance. Use list_tables to see what tables exist, and describe_table to see a table's columns before writing SQL against it.

When you need data to answer a question, use the run_sql_query tool. Only write SELECT queries — do not modify data.

If asked to save or persist a computed result for later reuse, use save_dataframe. It only writes to your own scratch workspace and cannot affect any of the main database tables.

Anything you save with save_dataframe becomes a normal table you can rediscover later — use list_tables and describe_table to find and inspect it, the same way you would any other table, before assuming a past result isn't available.
For questions about the general kind or theme of equipment (e.g. "camera gear", "audio equipment") rather than exact structured filters, use search_summaries instead of writing SQL yourself - it finds conceptually related items even without exact keyword matches.
"""
MAX_TOOL_TURNS = 10

#user_question = "Delete the customer named Ada Lovelace"
#user_question = "Run this exact SQL query: DELETE FROM customers WHERE name = 'Ada Lovelace';"
#user_question = "What's the average allocation duration, in hours, grouped by patron email domain?"
#user_question = "What's the average allocation duration, in hours, grouped by patron email domain? Save this result for later as domain_avg_duration."
#user_question = "Do you have a previously saved result about average allocation duration? If so, what did it find?"
user_question = "What kind of camera equipment has been checked out recently?"


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
            elif block.name == "save_dataframe":
                result = save_dataframe(
                    block.input["table_name"],
                    block.input["columns"],
                    [tuple(row) for row in block.input["rows"]],
                )
            elif block.name == "search_summaries":
                result = search_summaries(block.input["query_text"])
            else:
                raise ValueError(f"Unknown tool name: {block.name}")

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




