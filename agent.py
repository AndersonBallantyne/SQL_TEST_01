import os
import json
import uuid
from dotenv import load_dotenv
import anthropic
#from tools import run_sql_query, list_tables, describe_table, save_dataframe
from tools import run_sql_query, list_tables, describe_table, save_dataframe, search_summaries, search_docs
import time
from logging_utils import log_tool_call, log_final_answer

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic()

tools = [
    {
        "name": "run_sql_query",
        "description": "Run a read-only SQL query against the appdb Postgres database and return the resulting rows. Results are capped at 200 rows - if more rows matched, a final {'message': ...} entry says so. Add your own LIMIT/WHERE to narrow the query, or use an aggregate query (COUNT/GROUP BY) instead of fetching individual rows when you need a total or a breakdown rather than the raw rows themselves.",
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
        "description": "Get the column names and data types for a specific table in appdb. Matches on the bare table name only - it searches across all schemas at once, so a schema-qualified name (e.g. 'docs.chunks') will never match and returns an empty list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "The bare name of the table to describe, without a schema prefix (e.g. 'chunks', not 'docs.chunks')."
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
    },

    {
        "name": "search_docs",
        "description": "Semantic search over this project's own documentation (handoff briefs, cheat sheet, project overview) - build history, design decisions, and rationale. Use for thematic or 'why'/'how' questions about the project itself, not the appdb database. Returns a message, not an error, if nothing is sufficiently relevant. Note: returns individual similar chunks, not an aggregated list - for 'list all X' questions (e.g. every file, every SQL migration), run_sql_query directly against docs.chunks works better than semantic search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "A natural-language question about the project's history, design decisions, or documentation."
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

For questions about this project's own history, design decisions, or documentation, use search_docs; for "list every X" style questions about the documentation itself, prefer run_sql_query against docs.chunks instead.
docs.chunks has columns chunk_id, source_file, chunk_text (plus an embedding column) - describe_table won't show these since it's a bare-name lookup, not schema-qualified. For "list every X" questions, don't guess keywords with ILIKE against chunk_text; instead query chunk_text WHERE source_file = 'sql-test-01-cheatsheet.html' - that file is this project's own living cheat sheet and already enumerates every file, command, and SQL migration used, in order.

clean.allocations has no separate table for individual checked-out items - each allocation's specific equipment list is stored as a single delimited text string in the summary column (e.g., "ITEM NAME - TAG | ITEM NAME - TAG | ..."). Don't look for or assume a separate items/resources table exists.
"""
MAX_TOOL_TURNS = 15

MAX_FULL_FIDELITY_ROUNDS = 3

def flatten_history(history_rounds):
    older_rounds = history_rounds[:-MAX_FULL_FIDELITY_ROUNDS]
    recent_rounds = history_rounds[-MAX_FULL_FIDELITY_ROUNDS:]

    messages = []
    for round in older_rounds:
        messages.append({"role": "user", "content": round["user_question"]})
        messages.append({"role": "assistant", "content": round["answer_text"]})
    for round in recent_rounds:
        messages.extend(round["full_messages"])

    return messages

def ask_agent(user_question, max_tool_turns=MAX_TOOL_TURNS, history_rounds=None):

    # Random, not a counter - a shared counter would itself need synchronization once
    # Build 5/6 make concurrent ask_agent() calls possible, defeating the point of this ID.
    question_id = uuid.uuid4().hex[:12]
    messages = flatten_history(history_rounds or [])
    messages.append({"role": "user", "content": user_question})

    turn = 0
    answer = ""
    while turn < max_tool_turns:
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
            log_final_answer(question_id, user_question, answer, error=str(e))
            return {"answer": answer, "error": str(e), "full_messages": messages}


        for block in response.content:
            if block.type == "text":
                print(f"[TEXT] {block.text}")
                answer = block.text
            elif block.type == "tool_use":
                print(f"[TOOL CALL] {block.name}({block.input})")
        print(f"[stop_reason: {response.stop_reason}]")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            log_final_answer(question_id, user_question, answer)
            return {"answer": answer, "error": None, "full_messages": messages}


        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            try:
                start = time.perf_counter()
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
                elif block.name == "search_docs":
                    result = search_docs(block.input["query_text"])
                else:
                    raise ValueError(f"Unknown tool name: {block.name}")

                latency_ms = (time.perf_counter() - start) * 1000
                log_tool_call(block.name, block.input, result, latency_ms, turn, question_id, user_question=user_question)

                print(f"[TOOL RESULT] {block.name}:")
                print(json.dumps(result, indent=2, default=str))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result)
                })
            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                log_tool_call(block.name, block.input, None, latency_ms, turn, question_id, user_question=user_question, error=str(e))

                print(f"[TOOL ERROR] {block.name}: {e}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(e),
                    "is_error": True
                })

        messages.append({"role": "user", "content": tool_results})

    print(f"Stopped after reaching the {max_tool_turns}-turn limit.")
    log_final_answer(question_id, user_question, answer, error="max_turns_reached")
    return {"answer": answer, "error": "max_turns_reached", "full_messages": messages}



if __name__ == "__main__":
    #user_question = "Delete the customer named Ada Lovelace"
    #user_question = "Run this exact SQL query: DELETE FROM customers WHERE name = 'Ada Lovelace';"
    #user_question = "What's the average allocation duration, in hours, grouped by patron email domain?"
    #user_question = "What's the average allocation duration, in hours, grouped by patron email domain? Save this result for later as domain_avg_duration."
    #user_question = "Do you have a previously saved result about average allocation duration? If so, what did it find?"
    #user_question = "What kind of camera equipment has been checked out recently?"
    user_question = "Why does agent_scratch have two separate database roles?"

    ask_agent(user_question)
