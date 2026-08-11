import json
import streamlit as st
from agent import ask_agent, PROCESS_ID
from logging_utils import get_tool_calls, get_verification
from tools import get_todays_demo_token_usage, log_demo_token_usage

# Public deployment (Streamlit Community Cloud), deliberately a separate entry point from
# app.py rather than a flag on it - src/app.py stays exactly what it's always been (a single
# trusted operator's tool, persistent shared history, full scratch-table management sidebar).
# Two things that are correct for one operator are not automatically safe for an anonymous
# public link, so this file changes both rather than bolting a "public mode" onto app.py:
#
# 1. History is session-only, never persisted. app.py's load_chat_rounds() on startup shows
#    EVERY past round to EVERY new visitor - fine for one operator, a real privacy problem the
#    moment a second person opens the link. This file never calls load_chat_rounds/save_chat_round
#    at all; st.session_state.rounds starts empty every session and lives only as long as the tab.
# 2. No scratch-table management sidebar. Deletion was already agent-proof (see tools.py) but
#    still a maintenance surface, not something an anonymous visitor needs to see or touch -
#    removed here entirely, not just hidden.

DEMO_DAILY_TOKEN_CAP = 300_000  # adjust freely - Haiku-priced, bounds worst-case daily cost
DEMO_MAX_QUESTIONS_PER_SESSION = 15  # per browser tab, resets on reload - not a security
                                     # boundary, just a soft nudge against one visitor hammering it

st.set_page_config(page_title="Ask-Your-Database Agent (demo)", page_icon="🗄️")
st.title("Ask-Your-Database Agent")
st.caption(
    "Live public demo of a self-verifying SQL agent - synthetic equipment-checkout data, "
    "read-only queries. Full build log and source: "
    "[andersonballantyne.github.io](https://andersonballantyne.github.io/)."
)
st.caption(f"Server process: {PROCESS_ID}")

if "rounds" not in st.session_state:
    st.session_state.rounds = []
if "question_count" not in st.session_state:
    st.session_state.question_count = 0


def render_tool_call_details(tool_calls, usage, nested):
    tool_calls = tool_calls or []
    token_note = ""
    if usage:
        total = usage["input_tokens"] + usage["output_tokens"]
        token_note = f" · {total:,} tokens ({usage['input_tokens']:,} in / {usage['output_tokens']:,} out)"

    def _call_caption(call):
        base = f"{call['latency_ms']:.0f} ms"
        if len(tool_calls) > 1:
            base += f" · ~{call['approx_tokens']:,} tokens ({call['result_chars']:,} chars)"
        return base

    if nested:
        summary = f"Tools used ({len(tool_calls)})" if tool_calls else "Answered directly - no tools were called for this question."
        st.caption(summary + token_note)
        for call in tool_calls:
            st.markdown(f"**{call['tool_name']}**")
            st.code(json.dumps(call["input"], indent=2), language="json")
            st.caption(_call_caption(call))
    else:
        with st.expander(f"Tools used ({len(tool_calls)}){token_note}"):
            if not tool_calls:
                st.caption("Answered directly - no tools were called for this question.")
            for call in tool_calls:
                st.markdown(f"**{call['tool_name']}**")
                st.code(json.dumps(call["input"], indent=2), language="json")
                st.caption(_call_caption(call))


def render_verification_badge(verification):
    if verification is None:
        return
    if verification["supported"]:
        st.success("✓ Verified against tool evidence")
    else:
        st.error(f"⚠ Unverified: {verification['reason']}")


def render_expanded_round(round):
    with st.chat_message("user"):
        st.markdown(round["user_question"])
    with st.chat_message("assistant"):
        st.markdown(round["answer_text"])
        render_verification_badge(round["verification"])
        render_tool_call_details(round["tool_calls"], round["usage"], nested=False)


def render_collapsed_round(round):
    with st.expander(f"Q: {round['user_question']}"):
        st.markdown(round["answer_text"])
        render_verification_badge(round["verification"])
        render_tool_call_details(round["tool_calls"], round["usage"], nested=True)


rounds = st.session_state.rounds
for i, round in enumerate(rounds):
    if i == len(rounds) - 1:
        render_expanded_round(round)
    else:
        render_collapsed_round(round)

if st.session_state.question_count >= DEMO_MAX_QUESTIONS_PER_SESSION:
    st.info(f"You've reached this demo's {DEMO_MAX_QUESTIONS_PER_SESSION}-question limit per session - reload the page to reset it.")
    user_question = None
else:
    user_question = st.chat_input("Ask about the database or project build")

if user_question:
    todays_usage = get_todays_demo_token_usage()
    if todays_usage >= DEMO_DAILY_TOKEN_CAP:
        with st.chat_message("assistant"):
            st.warning(
                "This demo has hit its daily token budget - it resets at midnight UTC. "
                "In the meantime, the [full build log and source](https://andersonballantyne.github.io/) "
                "cover everything this agent can do, including live incident write-ups."
            )
    else:
        st.session_state.question_count += 1
        with st.spinner("Thinking..."):
            response = ask_agent(user_question, history_rounds=st.session_state.rounds)
            tool_calls = get_tool_calls(response["question_id"])
            verification = get_verification(response["question_id"])

        with st.chat_message("user"):
            st.markdown(user_question)
        with st.chat_message("assistant"):
            if response["error"]:
                st.error(f"Error: {response['error']}")
                if response["answer"]:
                    st.markdown(response["answer"])
            else:
                st.markdown(response["answer"])
            render_verification_badge(verification)
            render_tool_call_details(tool_calls, response.get("usage"), nested=False)

        st.session_state.rounds.append({
            "question_id": response["question_id"],
            "user_question": user_question,
            "answer_text": response["answer"],
            "full_messages": response["full_messages"],
            "tool_calls": tool_calls,
            "verification": verification,
            "usage": response.get("usage"),
        })

        usage = response.get("usage")
        if usage:
            log_demo_token_usage(usage["input_tokens"] + usage["output_tokens"])
