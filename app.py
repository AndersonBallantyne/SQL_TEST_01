import streamlit as st
from agent import ask_agent, PROCESS_ID

st.set_page_config(page_title="Ask-Your-Database Agent", page_icon="🗄️")
st.title("Ask-Your-Database Agent")
st.caption(f"Server process: {PROCESS_ID} — changes only if the app restarts, not on every question")

# Streamlit reruns this whole script on every interaction, so message history has to live in
# session_state explicitly - a plain Python list would reset to empty on every rerun.
if "messages" not in st.session_state:
    st.session_state.messages = []

if "rounds" not in st.session_state:
    st.session_state.rounds = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_question = st.chat_input("Ask a question about the database...")

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = ask_agent(user_question, history_rounds=st.session_state.rounds)

        if response["error"]:
            # Surfaced distinctly, not swallowed - max_turns_reached or a raw API error both
            # still return whatever partial answer text exists, so show both rather than
            # picking one.
            st.error(f"Error: {response['error']}")
            if response["answer"]:
                st.markdown(response["answer"])
        else:
            st.markdown(response["answer"])

    st.session_state.messages.append({"role": "assistant", "content": response["answer"]})

    st.session_state.rounds.append({
        "user_question": user_question,
        "answer_text": response["answer"],
        "full_messages": response["full_messages"],
    })
