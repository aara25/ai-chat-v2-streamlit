"""
Streamlit UI for ai_chat_v2.

Sign-in takes user_email, workspace_id AND project_id (unlike agentic-api's
UI, which only needs the first two) - see the design doc's "Conversation and
thread model": every thread is pinned to one project for its lifetime, so
the project has to be chosen before any thread can be listed or created.
There's no separate GET credential check here (ai_chat_v2/main.py doesn't
have one) - signing in just calls list_threads, which runs the same auth
gate internally; a bad email/workspace surfaces as that call's error.

After sign-in: the thread list for that project is shown (shared across the
workspace - see the design doc - so a teammate's threads on this project
show up here too), with a "Start new conversation" action alongside them.
Once a thread is open, sending a message streams the orchestrator's steps
live - which agent(s) the supervisor called and what it asked them, each
one's real reasoning text as it happens (agent_thinking), the REAL, dynamic
tool calls each one makes with their actual arguments AND response (not a
generic "agent is running" placeholder - see app/orchestrator/runtime.py's
event shapes), then the final answer with its evidence (transcript / AI note
/ insight) rendered underneath, matching the shared Evidence schema in
app/schemas/evidence.py. The sidebar also tracks this workspace's per-model
token usage (daily + per-thread session budgets - see
app/services/usage_limits.py) as `usage` events arrive mid-stream.

Run with: streamlit run streamlit_app.py
Talks to the deployed ai_chat_v2 Cloud Function at API_URL below.
"""
from __future__ import annotations

import json
import time

import requests
import streamlit as st

API_URL = "https://us-central1-looppanel.cloudfunctions.net/ai-chat-v2"

AGENT_LABELS = {
    "tool_agent": "Tool-Calling Agent",
    "rag_agent": "RAG Agent",
    None: "Supervisor",
}

st.set_page_config(page_title="AI Chat v2")

if "authed" not in st.session_state:
    st.session_state.authed = False
    st.session_state.user_email = ""
    st.session_state.workspace_id = ""
    st.session_state.project_id = ""
    st.session_state.threads = []  # from list_threads
    st.session_state.current_thread_id = None
    st.session_state.messages = []  # [{"role", "content", "evidence": [...], "model": ...}]
    st.session_state.model_catalog = {}  # {provider: [{"id", "label"}, ...]} from list_models
    st.session_state.selected_model = None  # None = deployment default
    st.session_state.usage_by_model = {}  # {model_id: {"daily": {...}, "session": {...}}} - from `usage` events

PROVIDER_LABELS = {"openai": "OpenAI", "google": "Gemini", "anthropic": "Claude"}


def model_display_label(model_id: str) -> str:
    """"OpenAI - GPT-5.1" - Streamlit's selectbox has no native grouping, so
    the provider is folded into the label text instead of a separate optgroup."""
    for provider, models in st.session_state.model_catalog.items():
        for model in models:
            if model["id"] == model_id:
                return f"{PROVIDER_LABELS.get(provider, provider)} - {model['label']}"
    return model_id


def post_action(action: str, **fields) -> tuple[bool, dict]:
    payload = {
        "action": action,
        "user_email": st.session_state.user_email,
        "workspace_id": st.session_state.workspace_id,
        **fields,
    }
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
    except requests.RequestException as exc:
        return False, {"error": f"Could not reach the API at {API_URL}: {exc}"}

    try:
        data = response.json()
    except ValueError:
        return False, {"error": f"Unexpected response (HTTP {response.status_code})"}

    return (response.status_code == 200 and data.get("success", False)), data


def render_sign_in_form() -> None:
    st.title("AI Chat v2")
    st.caption("Sign in with your email, workspace, and the project you want to chat about.")

    with st.form("sign_in"):
        email = st.text_input("Email", placeholder="you@yourcompany.com")
        workspace_id = st.text_input("Workspace ID")
        project_id = st.text_input("Project ID")
        submitted = st.form_submit_button("Continue", use_container_width=True)

    if submitted:
        email, workspace_id, project_id = email.strip(), workspace_id.strip(), project_id.strip()
        if not (email and workspace_id and project_id):
            st.error("Email, workspace ID, and project ID are all required.")
            return

        st.session_state.user_email = email
        st.session_state.workspace_id = workspace_id
        st.session_state.project_id = project_id

        with st.spinner("Checking your account and loading threads..."):
            ok, data = post_action("list_threads", project_id=project_id)

        if ok:
            st.session_state.authed = True
            st.session_state.threads = data.get("threads", [])
            models_ok, models_data = post_action("list_models")
            if models_ok:
                st.session_state.model_catalog = models_data.get("models", {})
            st.rerun()
        else:
            st.error(data.get("error") or "Could not sign in with those details.")


def sign_out() -> None:
    for key in (
        "authed", "user_email", "workspace_id", "project_id",
        "threads", "current_thread_id", "messages",
        "model_catalog", "selected_model", "usage_by_model",
    ):
        st.session_state.pop(key, None)


def refresh_threads() -> None:
    ok, data = post_action("list_threads", project_id=st.session_state.project_id)
    if ok:
        st.session_state.threads = data.get("threads", [])


def open_thread(thread_id: str) -> None:
    ok, data = post_action("get_thread", thread_id=thread_id)
    if ok:
        st.session_state.current_thread_id = thread_id
        st.session_state.messages = data.get("messages", [])
        st.rerun()
    else:
        st.error(data.get("error") or "Could not open that thread.")


def start_new_conversation() -> None:
    ok, data = post_action("create_thread", project_id=st.session_state.project_id)
    if ok:
        st.session_state.current_thread_id = data["thread_id"]
        st.session_state.messages = []
        refresh_threads()
        st.rerun()
    else:
        st.error(data.get("error") or "Could not start a new conversation.")


def render_thread_list() -> None:
    st.title("AI Chat v2")
    st.caption(f"Project `{st.session_state.project_id}` - threads are shared across the workspace.")

    if st.button("Start new conversation", use_container_width=True, type="primary"):
        start_new_conversation()
        return

    st.divider()
    if not st.session_state.threads:
        st.info("No threads yet on this project. Start one above.")
        return

    for thread in st.session_state.threads:
        title = thread.get("title") or "(untitled)"
        created_by = thread.get("created_by", "unknown")
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"**{title}**\n\nstarted by `{created_by}`")
            if col2.button("Open", key=f"open_{thread['id']}", use_container_width=True):
                open_thread(thread["id"])


def render_model_picker() -> None:
    """Flattens the provider-grouped catalog into one selectbox - the chosen
    model id is sent as SendMessageRequest.model and saved per-message (see
    conversation_store.save_message), not just once per thread, since the
    selection can change mid-thread."""
    all_model_ids = [m["id"] for models in st.session_state.model_catalog.values() for m in models]
    if not all_model_ids:
        return

    if st.session_state.selected_model not in all_model_ids:
        st.session_state.selected_model = None  # stale/unset selection - fall back to the deployment default

    # No `index=` here on purpose: `key` already binds this widget to
    # st.session_state.selected_model (initialized above), and Streamlit
    # disallows setting both a key's session_state value and `index` at once.
    st.selectbox(
        "Model",
        options=[None] + all_model_ids,
        format_func=lambda model_id: "Deployment default" if model_id is None else model_display_label(model_id),
        key="selected_model",
    )


def render_usage_breakdown() -> None:
    """This workspace's token usage, per model, as of the last `usage` event
    seen (one arrives before every turn starts and again right after it
    finishes - see app/orchestrator/runtime.py). Daily is shared across the
    WHOLE WORKSPACE (every thread, every model-user); session is just THIS
    thread's own budget for that model (app/services/usage_limits.py) - kept
    as two separate bars since they reset on different triggers (midnight vs.
    "start a new conversation")."""
    if not st.session_state.usage_by_model:
        st.caption("No usage recorded yet this session - send a message to see it.")
        return

    for model_id, usage in st.session_state.usage_by_model.items():
        st.markdown(f"**{model_display_label(model_id)}**")
        daily, session = usage.get("daily") or {}, usage.get("session") or {}
        if daily.get("limit"):
            st.progress(
                min(daily["used"] / daily["limit"], 1.0),
                text=f"Daily: {daily['used']:,} / {daily['limit']:,} tokens ({daily.get('remaining', 0):,} left today)",
            )
        if session.get("limit"):
            st.progress(
                min(session["used"] / session["limit"], 1.0),
                text=f"This thread: {session['used']:,} / {session['limit']:,} tokens ({session.get('remaining', 0):,} left)",
            )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"**Signed in as**\n\n{st.session_state.user_email}")
        st.markdown(f"**Workspace**\n\n`{st.session_state.workspace_id}`")
        st.markdown(f"**Project**\n\n`{st.session_state.project_id}`")
        st.divider()
        render_model_picker()
        st.divider()
        st.markdown("**Token usage**")
        render_usage_breakdown()
        st.divider()
        if st.button("Back to threads", use_container_width=True):
            st.session_state.current_thread_id = None
            st.session_state.messages = []
            refresh_threads()
            st.rerun()
        if st.button("Sign out", use_container_width=True):
            sign_out()
            st.rerun()


def render_evidence(evidence: list[dict]) -> None:
    if not evidence:
        return
    with st.expander(f"Evidence ({len(evidence)})"):
        for item in evidence:
            source_type = item.get("source_type")
            if source_type == "transcript":
                where = item.get("file_name") or item.get("source_id")
                span = f" ({item.get('start_timestamp')}-{item.get('end_timestamp')})" if item.get("start_timestamp") else ""
                speaker = f" - **{item['speaker']}**" if item.get("speaker") else ""
                st.markdown(f"Transcript - **{where}**{span}{speaker}\n\n> {item.get('quote')}")
            elif source_type == "ai_note":
                st.markdown(f"Note `{item.get('note_id')}`\n\n> {item.get('quote')}")
            elif source_type == "insight":
                st.markdown(f"Insight `{item.get('insight_id')}`\n\n> {item.get('quote')}")
            elif source_type == "tool_result":
                st.markdown(f"Tool response - **{item.get('tool_name')}**({format_tool_params(item.get('tool_params'))})")
                st.json(item.get("tool_response"), expanded=False)
            else:
                st.markdown(f"{item.get('quote')}")


def format_tool_params(params: dict) -> str:
    return ", ".join(f"{key}={value!r}" for key, value in (params or {}).items())


def stream_orchestrator_response(prompt: str, status_box) -> tuple[str | None, list[dict]]:
    """POSTs send_message and processes the SSE stream, writing each step
    into `status_box` as it arrives - which agent(s) the supervisor called
    and what it asked them, each one's real reasoning text as it happens
    (agent_thinking), and the real, per-tool calls each one makes INCLUDING
    their actual response content - matching app/orchestrator/runtime.py's
    event shapes exactly. Also updates st.session_state.usage_by_model from
    any `usage` events seen (app/services/usage_limits.py). Returns
    (final_answer, evidence), (None, []) on failure."""
    payload = {
        "action": "send_message",
        "user_email": st.session_state.user_email,
        "workspace_id": st.session_state.workspace_id,
        "thread_id": st.session_state.current_thread_id,
        "content": prompt,
    }
    if st.session_state.selected_model:
        payload["model"] = st.session_state.selected_model

    try:
        # Matches the backend's own ceiling (cloudbuild.yaml's function
        # --timeout and app/config.py's request_timeout_seconds, both raised
        # to 300s) - a shorter client timeout than the backend's own would
        # mean the UI gives up and shows a connection error before the
        # backend would ever actually finish a large project's turn.
        response = requests.post(API_URL, json=payload, stream=True, timeout=300)
    except requests.RequestException as exc:
        status_box.update(label="Connection error", state="error")
        st.error(f"Could not reach the API: {exc}")
        return None, []

    if response.status_code == 429:
        status_box.update(label="Usage limit reached", state="error")
        try:
            data = response.json()
        except ValueError:
            data = {}
        st.error(data.get("error") or "This workspace has hit its token usage limit.")
        return None, []

    if response.status_code != 200:
        status_box.update(label="Request failed", state="error")
        try:
            error_message = response.json().get("error", f"HTTP {response.status_code}")
        except ValueError:
            error_message = f"HTTP {response.status_code}"
        st.error(error_message)
        return None, []

    final_text, evidence, failed = None, [], False
    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue

            event = json.loads(raw_line[len("data: "):])
            event_type = event.get("type")

            if event_type == "run_started":
                status_box.update(label="Working...")
            elif event_type == "usage":
                st.session_state.usage_by_model[event["model"]] = {"daily": event.get("daily"), "session": event.get("session")}
            elif event_type == "agent_call_started":
                agent = event.get("agent")
                status_box.write(f"**{AGENT_LABELS.get(agent, agent)}** asked: {event.get('question')}")
            elif event_type == "agent_thinking":
                # The model's own reasoning, attached to the same message it
                # requested a tool call with - shown distinctly from both the
                # agent-call banner above and the tool-call lines below, so a
                # reader can follow WHY a tool was called, not just which one.
                status_box.markdown(f"> 💭 _{event.get('text')}_")
            elif event_type == "tool_call_started":
                tool_name = event.get("tool")
                params = format_tool_params(event.get("params"))
                status_box.caption(f"🔧 Calling `{tool_name}({params})`")
            elif event_type == "tool_progress":
                # Live per-transcript status from a correctness-first scan (see
                # app/tools/analytics.py) - this is what keeps a slow-but-correct
                # answer feeling live instead of a silent multi-second wait.
                status_box.caption(event.get("detail"))
            elif event_type == "tool_call_completed":
                tool_name = event.get("tool")
                outcome = "✅" if event.get("success") else "❌" if event.get("success") is False else "•"
                duration = event.get("duration_ms") or 0
                status_box.caption(f"{outcome} `{tool_name}` finished ({duration:.0f}ms)")
                if event.get("error"):
                    status_box.caption(f"&nbsp;&nbsp;&nbsp;⚠️ {event['error']}")
                if event.get("response") is not None:
                    with status_box.expander(f"{tool_name} response", expanded=False):
                        st.json(event["response"])
            elif event_type == "agent_call_completed":
                agent = event.get("agent")
                duration = event.get("duration_ms") or 0
                status_box.write(f"**{AGENT_LABELS.get(agent, agent)}** finished ({duration:.0f}ms)")
            elif event_type == "run_completed":
                final_text = event.get("response")
                evidence = event.get("evidence", [])
                status_box.update(label="Done", state="complete", expanded=False)
            elif event_type == "error":
                failed = True
                status_box.update(label="Error", state="error")
                st.error(event.get("error") or "Something went wrong")
    except requests.RequestException as exc:
        status_box.update(label="Connection lost", state="error")
        st.error(f"The connection dropped before an answer arrived: {exc}")
        return None, []

    if final_text is None and not failed:
        status_box.update(label="No answer", state="error")
        st.error("The stream ended without an answer. Try asking again.")

    return final_text, evidence


def render_sender_label(message: dict) -> None:
    """Threads are shared across the workspace (see the design doc's
    "Conversation and thread model") - without showing who sent each
    message, a thread with more than one participant reads as an
    unattributed jumble. Only user messages need this; assistant messages
    have no ambiguity about who "sent" them."""
    if message.get("role") != "user":
        return
    sender = message.get("user_name") or message.get("user_email")
    if sender and sender != st.session_state.user_email:
        st.caption(sender)


def render_model_caption(message: dict) -> None:
    """Which model answered this message (or requested it, on a user
    message) - saved per-message in Firestore (see
    conversation_store.save_message), not just once per thread, since the
    selection can change mid-thread."""
    model_id = message.get("model")
    if model_id:
        st.caption(model_display_label(model_id))


def render_chat() -> None:
    st.title("AI Chat v2")

    for message in st.session_state.messages:
        with st.chat_message(message.get("role", "assistant")):
            render_sender_label(message)
            st.markdown(message.get("content", ""))
            render_evidence(message.get("evidence") or [])
            if message.get("role") == "assistant":
                render_model_caption(message)

    prompt = st.chat_input("Ask about this project's transcripts, notes, or insights...")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt, "model": st.session_state.selected_model})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.status("Thinking...", expanded=True) as status_box:
            final_text, evidence = stream_orchestrator_response(prompt, status_box)

        if final_text:
            st.write_stream(stream_words_with_delay(final_text))
            render_evidence(evidence)
            answer_model = st.session_state.selected_model
            if answer_model:
                st.caption(model_display_label(answer_model))
            st.session_state.messages.append(
                {"role": "assistant", "content": final_text, "evidence": evidence, "model": answer_model}
            )

    # Refreshes the sidebar's usage breakdown with what this turn just spent -
    # it was rendered before this turn ran, so without a rerun it would keep
    # showing last turn's numbers until the next unrelated interaction.
    st.rerun()


def stream_words_with_delay(text: str, delay: float = 0.02):
    """The backend delivers the final answer as one complete message, not
    token-by-token - this reveals it word by word so it reads as live rather
    than popping in all at once."""
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(delay)


if not st.session_state.authed:
    render_sign_in_form()
elif not st.session_state.current_thread_id:
    render_sidebar()
    render_thread_list()
else:
    render_sidebar()
    render_chat()
