import json
import streamlit as st
from agent import ask_agent, PROCESS_ID
from logging_utils import get_tool_calls, get_verification, get_usage
from tools import save_chat_round, load_chat_rounds, list_stale_scratch_tables, delete_scratch_tables

# Streamlit reruns this whole script on every interaction, so history has to live in
# session_state explicitly - a plain Python list would reset to empty on every rerun.
# Persistence (Build 6 Phase 3.5) is what makes session_state survive a real restart too:
# rounds now loads from agent_scratch.chat_rounds on first load instead of starting empty.

st.set_page_config(page_title="Ask-Your-Database Agent", page_icon="🗄️")
st.title("Ask-Your-Database Agent")
st.caption(f"Server process: {PROCESS_ID} — changes only if the app restarts")


# Deletion lives here, not as an agent tool - the conversational agent can only ever list/
# recommend (list_stale_scratch_tables, read-only). Actual deletion requires a real button
# click in this sidebar, so it never depends on the model correctly judging whether a chat
# reply counts as genuine user confirmation. Two-tier: 7+ days old is worth mentioning,
# 30+ days old is actually offered for deletion - a table can be old enough to flag without
# being old enough to remove.
with st.sidebar:
    st.subheader("Scratch table cleanup")

    if "scratch_cleanup_result" in st.session_state:
        result = st.session_state.pop("scratch_cleanup_result")
        if result["deleted"]:
            st.success(f"Deleted: {', '.join(result['deleted'])}")
        if result["skipped"]:
            st.warning("Skipped: " + "; ".join(f"{s['table_name']} ({s['reason']})" for s in result["skipped"]))

    stale = list_stale_scratch_tables()
    eligible = [t for t in stale if t["age_days"] is not None and t["eligible_for_deletion"]]
    worth_mentioning = [t for t in stale if t["age_days"] is not None and not t["eligible_for_deletion"]]
    unknown_age = [t for t in stale if t["age_days"] is None]

    if not stale:
        st.caption("No scratch tables 7+ days old.")
    if worth_mentioning:
        st.caption("Worth a look (not yet eligible for deletion):")
        for t in worth_mentioning:
            st.caption(f"  · {t['table_name']} ({t['age_days']}d)")
    if unknown_age:
        st.caption(f"{len(unknown_age)} table(s) with no tracked creation date - not evaluated.")

    if eligible:
        st.caption("Eligible for deletion (30+ days old):")
        labels = {t["table_name"]: f"{t['table_name']} ({t['age_days']}d)" for t in eligible}
        selected = st.multiselect(
            "Select tables to delete", list(labels.keys()), format_func=lambda name: labels[name]
        )
        if selected and st.button(f"Delete {len(selected)} selected table(s)", type="primary"):
            st.session_state.scratch_cleanup_result = delete_scratch_tables(selected)
            st.rerun()


if "rounds" not in st.session_state:
    persisted = load_chat_rounds()
    for round in persisted:
        # Tool-call detail isn't persisted in chat_rounds itself - logs/tool_calls.jsonl
        # already survives a restart via its own bind mount (Build 6 Phase 3), so this
        # re-derives display data the same way a live session already does, no duplication.
        round["tool_calls"] = get_tool_calls(round["question_id"])
        round["verification"] = get_verification(round["question_id"])
        round["usage"] = get_usage(round["question_id"])

    st.session_state.rounds = persisted


def render_tool_call_details(tool_calls, usage, nested):
    # Streamlit doesn't allow nesting st.expander inside another st.expander - nested=True
    # (a collapsed FAQ round) renders this plainly instead; nested=False (the one expanded
    # round) keeps the real collapsible widget, since it's never itself inside an expander.
    tool_calls = tool_calls or []
    # Token usage is per-question (every API turn, not per tool call) - logged alongside the
    # final answer in logs/tool_calls.jsonl, so it's available for reloaded rounds too, not
    # just ones answered live this session. None only for entries logged before this existed.
    token_note = ""
    if usage:
        total = usage["input_tokens"] + usage["output_tokens"]
        token_note = f" · {total:,} tokens ({usage['input_tokens']:,} in / {usage['output_tokens']:,} out)"

    if nested:
        summary = f"Tools used ({len(tool_calls)})" if tool_calls else "Answered directly - no tools were called for this question."
        st.caption(summary + token_note)
        for call in tool_calls:
            st.markdown(f"**{call['tool_name']}**")
            st.code(json.dumps(call["input"], indent=2), language="json")
            st.caption(f"{call['latency_ms']:.0f} ms")
    else:
        with st.expander(f"Tools used ({len(tool_calls)}){token_note}"):
            if not tool_calls:
                st.caption("Answered directly - no tools were called for this question.")
            for call in tool_calls:
                st.markdown(f"**{call['tool_name']}**")
                st.code(json.dumps(call["input"], indent=2), language="json")
                st.caption(f"{call['latency_ms']:.0f} ms")

def render_verification_badge(verification):
    if verification is None:
        return
    if verification["supported"]:
        st.success("✓ Verified against tool evidence")
    else:
        st.error(f"⚠ Unverified: {verification['reason']}")


def render_expanded_round(round):
    # The one round shown in full - either the round just answered this turn, or (on a
    # fresh load) whichever round was most recently asked in an earlier session.
    with st.chat_message("user"):
        st.markdown(round["user_question"])
    with st.chat_message("assistant"):
        st.markdown(round["answer_text"])
        render_verification_badge(round["verification"])
        render_tool_call_details(round["tool_calls"], round["usage"], nested=False)


def render_collapsed_round(round):
    # Older rounds fold into a labeled expander - clears up "which response is mine" (the
    # newest answer is always the one left open) and doubles as a scannable FAQ list, since
    # the question text itself is the collapsed label.
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

user_question = st.chat_input("Ask about the database or project build")

if user_question:
    with st.spinner("Thinking..."):
        response = ask_agent(user_question, history_rounds=st.session_state.rounds)
        tool_calls = get_tool_calls(response["question_id"])
        verification = get_verification(response["question_id"])


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

    save_chat_round(response["question_id"], user_question, response["answer"], response["full_messages"])
