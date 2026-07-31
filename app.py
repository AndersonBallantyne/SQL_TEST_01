import json
import streamlit as st
from agent import ask_agent, PROCESS_ID
from logging_utils import get_tool_calls
from tools import save_chat_round, load_chat_rounds

# Streamlit reruns this whole script on every interaction, so history has to live in
# session_state explicitly - a plain Python list would reset to empty on every rerun.
# Persistence (Build 6 Phase 3.5) is what makes session_state survive a real restart too:
# rounds now loads from agent_scratch.chat_rounds on first load instead of starting empty.

st.set_page_config(page_title="Ask-Your-Database Agent", page_icon="🗄️")
st.title("Ask-Your-Database Agent")
st.caption(f"Server process: {PROCESS_ID} — changes only if the app restarts")


if "rounds" not in st.session_state:
    persisted = load_chat_rounds()
    for round in persisted:
        # Tool-call detail isn't persisted in chat_rounds itself - logs/tool_calls.jsonl
        # already survives a restart via its own bind mount (Build 6 Phase 3), so this
        # re-derives display data the same way a live session already does, no duplication.
        round["tool_calls"] = get_tool_calls(round["question_id"])
    st.session_state.rounds = persisted


def render_tool_call_details(tool_calls, nested):
    # Streamlit doesn't allow nesting st.expander inside another st.expander - nested=True
    # (a collapsed FAQ round) renders this plainly instead; nested=False (the one expanded
    # round) keeps the real collapsible widget, since it's never itself inside an expander.
    tool_calls = tool_calls or []
    if nested:
        st.caption(f"Tools used ({len(tool_calls)})" if tool_calls else "Answered directly - no tools were called for this question.")
        for call in tool_calls:
            st.markdown(f"**{call['tool_name']}**")
            st.code(json.dumps(call["input"], indent=2), language="json")
            st.caption(f"{call['latency_ms']:.0f} ms")
    else:
        with st.expander(f"Tools used ({len(tool_calls)})"):
            if not tool_calls:
                st.caption("Answered directly - no tools were called for this question.")
            for call in tool_calls:
                st.markdown(f"**{call['tool_name']}**")
                st.code(json.dumps(call["input"], indent=2), language="json")
                st.caption(f"{call['latency_ms']:.0f} ms")


def render_expanded_round(round):
    # The one round shown in full - either the round just answered this turn, or (on a
    # fresh load) whichever round was most recently asked in an earlier session.
    with st.chat_message("user"):
        st.markdown(round["user_question"])
    with st.chat_message("assistant"):
        st.markdown(round["answer_text"])
        render_tool_call_details(round["tool_calls"], nested=False)


def render_collapsed_round(round):
    # Older rounds fold into a labeled expander - clears up "which response is mine" (the
    # newest answer is always the one left open) and doubles as a scannable FAQ list, since
    # the question text itself is the collapsed label.
    with st.expander(f"Q: {round['user_question']}"):
        st.markdown(round["answer_text"])
        render_tool_call_details(round["tool_calls"], nested=True)


rounds = st.session_state.rounds
for i, round in enumerate(rounds):
    if i == len(rounds) - 1:
        render_expanded_round(round)
    else:
        render_collapsed_round(round)

user_question = st.chat_input("Ask about the database or project build")

if user_question:
    with st.spinner("Thinking..."):
        response = ask_agent(user_question, history_rounds=st.session_state.rounds)
        tool_calls = get_tool_calls(response["question_id"])

    with st.chat_message("user"):
        st.markdown(user_question)
    with st.chat_message("assistant"):
        if response["error"]:
            # Surfaced distinctly, not swallowed - max_turns_reached or a raw API error both
            # still return whatever partial answer text exists, so show both rather than
            # picking one.
            st.error(f"Error: {response['error']}")
            if response["answer"]:
                st.markdown(response["answer"])
        else:
            st.markdown(response["answer"])
        render_tool_call_details(tool_calls, nested=False)

    st.session_state.rounds.append({
        "question_id": response["question_id"],
        "user_question": user_question,
        "answer_text": response["answer"],
        "full_messages": response["full_messages"],
        "tool_calls": tool_calls,
    })

    save_chat_round(response["question_id"], user_question, response["answer"], response["full_messages"])
