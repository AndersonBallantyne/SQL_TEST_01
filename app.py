import json
import streamlit as st
from agent import ask_agent, PROCESS_ID
from logging_utils import get_tool_calls

# Streamlit reruns this whole script on every interaction, so message history has to live in
# session_state explicitly - a plain Python list would reset to empty on every rerun.

st.set_page_config(page_title="Ask-Your-Database Agent", page_icon="🗄️")
st.title("Ask-Your-Database Agent")
st.caption(f"Server process: {PROCESS_ID} — changes only if the app restarts")


if "messages" not in st.session_state:
    st.session_state.messages = []

if "rounds" not in st.session_state:
    st.session_state.rounds = []


def render_tool_calls(tool_calls):
    # Input only, not output - output can be a full row dump (see MAX_SQL_RESULT_ROWS), which
    # would turn this expander into the same doom-scrolling problem it's meant to avoid.
    tool_calls = tool_calls or []
    with st.expander(f"Tools used ({len(tool_calls)})"):
        if not tool_calls:
            st.caption("Answered directly - no tools were called for this question.")
        for call in tool_calls:
            st.markdown(f"**{call['tool_name']}**")
            st.code(json.dumps(call["input"], indent=2), language="json")
            st.caption(f"{call['latency_ms']:.0f} ms")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_tool_calls(message.get("tool_calls"))

user_question = st.chat_input("Ask about the database or project build")

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = ask_agent(user_question, history_rounds=st.session_state.rounds)
            tool_calls = get_tool_calls(response["question_id"])

        if response["error"]:
            # Surfaced distinctly, not swallowed - max_turns_reached or a raw API error both
            # still return whatever partial answer text exists, so show both rather than
            # picking one.
            st.error(f"Error: {response['error']}")
            if response["answer"]:
                st.markdown(response["answer"])
        else:
            st.markdown(response["answer"])

        render_tool_calls(tool_calls)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response["answer"],
        "tool_calls": tool_calls,
    })

    st.session_state.rounds.append({
        "user_question": user_question,
        "answer_text": response["answer"],
        "full_messages": response["full_messages"],
    })
