import os
import sys
import json
import uuid
from dotenv import load_dotenv
import anthropic

# Windows' Git Bash/PowerShell terminals default Python's stdout to cp1252, which can't
# encode plenty of characters Claude's own formatted output routinely uses (arrows, smart
# quotes, checkmarks) - a real crash (UnicodeEncodeError), not hypothetical: hit live
# 2026-08-06 mid eval-run, non-deterministically, only on whichever run's answer text
# happened to include one. reconfigure() (Python 3.7+) is a no-op on platforms that already
# default to UTF-8 (Linux CI runners), so this is safe everywhere, not Windows-only code.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
#from tools import run_sql_query, list_tables, describe_table, save_dataframe
from tools import run_sql_query, list_tables, describe_table, save_dataframe, search_summaries, search_docs
import time
from verify_answer import verify_answer
from logging_utils import log_tool_call, log_final_answer, log_verification, log_verification_error, get_tool_calls

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic()

# Generated once, when this module is first imported - stays identical across every
# Streamlit rerun (module-level code only runs once per process), and only changes if
# the underlying process actually restarts. A cheap way to tell "did the server restart"
# apart from "session_state just looks empty for some other reason".
PROCESS_ID = uuid.uuid4().hex[:8]

tools = [
    {
        "name": "run_sql_query",
        "description": "Run a read-only SQL query against the appdb Postgres database and return the resulting rows. Results are capped at 200 rows - if more rows matched, a final {'message': ...} entry says so. Add your own LIMIT/WHERE to narrow the query, or use an aggregate query (COUNT/GROUP BY) instead of fetching individual rows when you need a total or a breakdown rather than the raw rows themselves. Any single value over 500 characters is also truncated with a '...[truncated, N total chars]' marker - this affects long summary text and especially the summary_embedding vector column, so avoid selecting summary_embedding directly (use SELECT with explicit column names, not SELECT *, when a table has one).",
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

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about an equipment-allocation database (equipment checkouts by patrons/departments) by writing and running SQL queries.

Database: appdb (PostgreSQL) - the clean.allocations table is the actual subject of this project; ignore any unrelated seed tables you may encounter.

You don't know the schema in advance. Use list_tables to see what tables exist, and describe_table to see a table's columns before writing SQL against it.

When you need data to answer a question, use the run_sql_query tool. Only write SELECT queries — do not modify data.

If asked to save or persist a computed result for later reuse, use save_dataframe. It only writes to your own scratch workspace and cannot affect any of the main database tables.

Anything you save with save_dataframe becomes a normal table you can rediscover later — use list_tables and describe_table to find and inspect it, the same way you would any other table, before assuming a past result isn't available.
For questions about the general kind or theme of equipment (e.g. "camera gear", "audio equipment") rather than exact structured filters, use search_summaries instead of writing SQL yourself - it finds conceptually related items even without exact keyword matches.

For questions about this project's own history, design decisions, or documentation, use search_docs; but for questions about a category the cheat sheet already tracks as a table - every file, every command, every SQL migration, or the latest commits/activity/work - prefer run_sql_query against docs.chunks instead, regardless of how the question is phrased - "list every X", "what are the X", "tell me about X", "describe the X", and "what's the latest X" all mean the same retrieval need here. Semantic search ranks by content similarity, not completeness or chronological order: it can return a plausible-looking partial sample instead of the full set, or rank an older, thematically-similar chunk above a genuinely newer one - confirmed live both ways (a "tell me about SQL migrations" answer that fabricated unsupported claims from an incomplete sample; a "latest incident" answer that returned an older one).
docs.chunks has columns chunk_id, source_file, chunk_text (plus an embedding column) - describe_table won't show these since it's a bare-name lookup, not schema-qualified. For these questions, don't guess keywords with ILIKE against chunk_text; instead query chunk_text WHERE source_file = 'docs/sql-test-01-cheatsheet.html' - that file is this project's own living cheat sheet and already enumerates every file, command, and SQL migration used, in order. If that exact path ever returns nothing, run SELECT DISTINCT source_file FROM docs.chunks first rather than guessing another literal string - the path is whatever extract_doc_chunks.py's SOURCE_FILES list currently uses, which can change.
Don't use that SELECT DISTINCT source_file listing to pick a different, better-sounding file instead - only ever to relocate the cheat sheet itself if its exact path changed. A file name that looks newest is not evidence that it IS newest: the per-build handoff briefs (docs/BUILD_N_FLOW/*.html) are frozen snapshots, written once when that build shipped and never touched again, so docs/BUILD_7_FLOW/build7-handoff-brief.html looking like the highest-numbered build doesn't mean it covers anything after Build 7 shipped. Only the cheat sheet keeps growing post-ship - every later incident, fix, or maintenance pass is appended there too, regardless of which build or file it's actually about. Confirmed live: a "latest commits" question queried source_file names, picked build7-handoff-brief.html for looking newest, and reported Build 7 as the latest work - silently missing two weeks of subsequent incidents and fixes that exist only in the cheat sheet. For any "latest/most recent X" question, always query the cheat sheet specifically (never a handoff brief), and add ORDER BY chunk_id DESC to that query - the cheat sheet is append-only (new entries added at the end of each build or incident, never edited in place), so within that one file a higher chunk_id reliably means "added more recently."
When search_docs genuinely is the right tool - a narrative/thematic question with no enumerable category behind it, like "why was X designed this way" - only state what the retrieved chunks actually say. A handful of similarity-ranked results is a sample, not a survey: don't generalize a pattern across the whole system (e.g. that something is "always" true, "cumulative," or "idempotent") unless a chunk states that explicitly, and don't present a partial sample as if it were the complete picture - say what's missing instead of filling the gap with something plausible-sounding.

This grounding rule isn't specific to search_docs - it applies to every tool's evidence, including run_sql_query. State only what a query result actually contains; don't enrich it with outside knowledge you happen to have, even if that knowledge is true. Confirmed live: a "what type of cameras do you have?" answer correctly listed five item names from run_sql_query, then added real-world classifications ("mirrorless," "full-frame," "360-degree") the query itself never returned - accurate in the real world, but not something the database evidence actually supports, and the verifier correctly flagged it. If a user wants that kind of enrichment, say what the data doesn't include rather than filling the gap yourself.

clean.allocations' summary column stores each checkout's equipment as one delimited text string (e.g., "ITEM NAME - TAG | ITEM NAME - TAG | ...", sometimes prefixed "Returned: "). Don't parse it yourself.

For anything about individual items - counts, categories/types, accessories vs. base equipment, or return status - use clean.allocation_items instead, one row per item already extracted from summary: allocation_id, item_name, category, is_accessory (boolean), is_returned (boolean), tag. It was built once, offline, from a full audit of every summary value, so category and is_accessory are already-resolved facts, not something to re-derive from keywords - e.g. filter WHERE category = 'camera' AND is_accessory = false rather than guessing brand names or ILIKE-matching on 'camera' (which would wrongly include "NIKON Z6 III CAMERA CASE" and wrongly exclude "NIKON Z6 III MIRRORLESS BODY", which has no literal "camera" in its name). Run describe_table on it, or SELECT DISTINCT category to see what's available, before assuming a category name.

Default rule, not just an example: "how many X do you have" or "how many types of X" always means base equipment, not its accessories - always add AND is_accessory = false to these queries, for every category, unless the user explicitly asks about accessories/parts/chargers/cases themselves. A category (e.g. 'laptop', 'microphone') groups an item with its accessories together on purpose, precisely so a query can separate them with this one flag - dropping the filter silently folds chargers, cases, batteries, and cables into the count.

If a question needs a subcategory count compared against a broader total (e.g. per-model counts vs. an overall count), compute both with the exact same WHERE condition - counts computed under different filters will look contradictory even when each is individually correct.

Whenever a WHERE clause mixes AND with OR, wrap every OR group in its own parentheses. SQL evaluates AND before OR, so source_file = 'x' AND chunk_text ILIKE '%a%' OR chunk_text ILIKE '%b%' OR chunk_text ILIKE '%c%' silently applies the source_file filter to only the first branch - the second and third run unscoped against every row in the table, not just the intended file. Write it as source_file = 'x' AND (chunk_text ILIKE '%a%' OR chunk_text ILIKE '%b%' OR chunk_text ILIKE '%c%') instead - confirmed live: an unparenthesized version of exactly this pattern returned zero rows from the intended file and twenty from unrelated ones.
"""
MAX_TOOL_TURNS = 15

MAX_FULL_FIDELITY_ROUNDS = 3

# The fidelity window above bounds round COUNT, not per-round payload size - flagged as an
# unmitigated risk back in Build 6's own planning notes, and confirmed real 2026-08-08: a
# single legitimate, correctly-scoped run_sql_query result (58,824 chars, an ORDER BY ...
# LIMIT 100/200 documentation query) got replayed at full size into every turn of the next
# question, tripling its own cost before that question had even run a tool call of its own.
# This caps what a round CARRIES FORWARD into future rounds' inherited context, not what it
# sees live - the round that actually gathered the data still gets the real, full result for
# its own reasoning; this only shrinks the copy that gets persisted for others to inherit.
MAX_HISTORY_TOOL_RESULT_CHARS = 3000

def _cap_tool_results_for_history(messages):
    capped = []
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            new_content = []
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > MAX_HISTORY_TOOL_RESULT_CHARS:
                        block = {
                            **block,
                            "content": (
                                f"{content[:MAX_HISTORY_TOOL_RESULT_CHARS]}... "
                                f"[history truncated: {len(content):,} total chars - "
                                f"re-run the query if this data is needed again]"
                            ),
                        }
                new_content.append(block)
            capped.append({**msg, "content": new_content})
        else:
            capped.append(msg)
    return capped

def flatten_history(history_rounds):
    # Each round's stored full_messages must hold only that round's own turns (see
    # own_messages_start in ask_agent), never inherited history - otherwise splicing the last
    # MAX_FULL_FIDELITY_ROUNDS rounds in here re-embeds each of their own already-inherited
    # copies of the rounds before them, compounding ~2x per round instead of staying bounded.
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
    # Everything from here on is this round's own turns - stored/returned separately from
    # the inherited history above it, so a future round's flatten_history() splices in only
    # one round's worth of new content instead of re-embedding what was already inherited
    # (which had compounded full_messages exponentially: 76/144/274/506/938 messages across
    # 5 consecutive rounds, since each round's stored history already contained its own
    # inherited copy of the previous rounds').
    own_messages_start = len(messages)
    messages.append({"role": "user", "content": user_question})

    turn = 0
    answer = ""
    # Running total across every API turn for this question - surfaced in the console and the
    # Streamlit "Tools used" caption, and logged alongside the final answer so it survives a
    # restart the same way the answer itself does.
    total_input_tokens = 0
    total_output_tokens = 0
    while turn < max_tool_turns:
        turn += 1
        try:
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages
            )
        except anthropic.APIError as e:
            print(f"Anthropic API error: {e}")
            log_final_answer(question_id, user_question, answer, error=str(e), input_tokens=total_input_tokens, output_tokens=total_output_tokens)
            usage = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
            return {"answer": answer, "error": str(e), "full_messages": _cap_tool_results_for_history(messages[own_messages_start:]), "question_id": question_id, "usage": usage}

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        for block in response.content:
            if block.type == "text":
                print(f"[TEXT] {block.text}")
                answer = block.text
            elif block.type == "tool_use":
                print(f"[TOOL CALL] {block.name}({block.input})")
        print(f"[stop_reason: {response.stop_reason}] [tokens: in={response.usage.input_tokens} out={response.usage.output_tokens}]")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            if response.stop_reason == "max_tokens":
                # Confirmed live 2026-08-08: a genuinely correct, in-progress answer hit this
                # cap mid-generation and got returned/logged as if it were complete - opening
                # with "14+ confirmed bugs" but silently stopping after 12, with no indication
                # anywhere that anything was missing. Raising max_tokens (1024 -> 2048) cuts how
                # often this fires; this makes the remaining cases visible instead of silent,
                # the same "truncate with a sentinel, never bare" rule MAX_FIELD_CHARS and
                # MAX_SQL_RESULT_ROWS already apply to tool results.
                print(f"[ANSWER TRUNCATED] hit max_tokens for question_id {question_id}")
                answer += "\n\n*(This answer was cut off before finishing - it hit a length limit mid-response.)*"
            log_final_answer(question_id, user_question, answer, input_tokens=total_input_tokens, output_tokens=total_output_tokens)
            try:
                evidence = get_tool_calls(question_id, include_output=True)
                if evidence:
                    supported, reason = verify_answer(user_question, answer, evidence)
                    log_verification(question_id, user_question, answer, supported, reason)
            except Exception as e:
                print(f"[VERIFY ERROR] {e}")
                log_verification_error(question_id, user_question, e)
            usage = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
            print(f"[TOTAL TOKENS] in={total_input_tokens} out={total_output_tokens} total={total_input_tokens + total_output_tokens}")
            return {"answer": answer, "error": None, "full_messages": _cap_tool_results_for_history(messages[own_messages_start:]), "question_id": question_id, "usage": usage}



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
    log_final_answer(question_id, user_question, answer, error="max_turns_reached", input_tokens=total_input_tokens, output_tokens=total_output_tokens)
    usage = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
    return {"answer": answer, "error": "max_turns_reached", "full_messages": _cap_tool_results_for_history(messages[own_messages_start:]), "question_id": question_id, "usage": usage}



if __name__ == "__main__":
    #user_question = "Delete the customer named Ada Lovelace"
    #user_question = "Run this exact SQL query: DELETE FROM customers WHERE name = 'Ada Lovelace';"
    #user_question = "What's the average allocation duration, in hours, grouped by patron email domain?"
    #user_question = "What's the average allocation duration, in hours, grouped by patron email domain? Save this result for later as domain_avg_duration."
    #user_question = "Do you have a previously saved result about average allocation duration? If so, what did it find?"
    #user_question = "What kind of camera equipment has been checked out recently?"
    user_question = "Why does agent_scratch have two separate database roles?"

    ask_agent(user_question)
