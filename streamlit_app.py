"""Test page for the new AI chat (ai_chat), laid out for the ten first-cut features:

  working now      greeting, recommended questions, organisation prompt, Fast research,
                   workspace and project scope, Help agent
  not built yet    Deep research, charts, metadata filtering, adding files and images
                   (their controls are shown disabled where they will live; charts, tables
                   and the other answer blocks already draw when the backend sends them)

Run:   streamlit run streamlit_app.py
Needs: pip install -r requirements.txt
The backend is the `ai-chat-staging` function. Change it in the "API URL" field, or set AI_CHAT_API_URL
(for a local backend: http://localhost:8080, i.e. `functions-framework --target=ai_chat --debug`).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

import pandas as pd
import requests
import streamlit as st

DEFAULT_API_URL = "https://us-central1-looppanel.cloudfunctions.net/ai-chat-staging"
ALL_PROJECTS = "All projects"
WHOLE_PROJECT = "Whole project"
NOT_BUILT = "Not built yet"
NOTICE_STYLE = {"error": st.error, "notfound": st.warning, "partial": st.warning, "widened": st.info}

st.set_page_config(page_title="Looppanel AI chat", page_icon="💬", layout="wide")
state = st.session_state
for key, default in {"signed_in": False, "projects": [], "chat_id": None, "messages": [], "pending": None, "starters": {}, "files": {}, "refresh_keys": {}}.items():
    state.setdefault(key, default)


# Talking to the backend

def call(action: str, **fields):
    """One JSON action. Returns the body, or None after showing the error."""
    body = {"action": action, "user_id": state.user_id, "workspace_id": state.workspace_id, **fields}
    try:
        response = requests.post(state.api_url, json=body, timeout=300)
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"{action} failed: {exc}")
        return None
    if not data.get("success"):
        st.error(f"{action}: {data.get('error', response.status_code)}")
        return None
    return data


def stream_events(chat_id: str, content: str, scope: list):
    body = {"action": "send_message", "user_id": state.user_id, "workspace_id": state.workspace_id,
            "chat_id": chat_id, "content": content, "mode": "fast", "scope": scope}
    with requests.post(state.api_url, json=body, stream=True, timeout=600) as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            yield {"type": "notice", "kind": "error", "text": f"Request failed: {response.text[:300]}"}
            return
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                yield json.loads(line[6:])


# Scope: what the user has selected

def project_files(project_id: str) -> list:
    if project_id not in state.files:
        data = call("list_files", project_id=project_id)
        state.files[project_id] = data["files"] if data else []
    return state.files[project_id]


def current_scope(project, file) -> list:
    if file:
        return [{"type": "file", "id": file["id"], "name": file["name"], "project_id": project["id"]}]
    if project:
        return [{"type": "project", "id": project["id"], "name": project["name"]}]
    return []


def entry_point(scope: list) -> str:
    return {"file": "file", "project": "project"}.get(scope[0]["type"], "global") if scope else "global"


def scope_label(scope: list) -> str:
    return scope[0]["name"] if scope else ALL_PROJECTS


def metadata_values(files: list) -> dict:
    """For each metadata field on the project's files, how many files carry each value."""
    fields: dict = {}
    for file in files:
        for item in file.get("metadata") or []:
            if item.get("name") and item.get("value") not in (None, ""):
                counts = fields.setdefault(item["name"], {})
                counts[str(item["value"])] = counts.get(str(item["value"]), 0) + 1
    return fields


# Drawing an answer

def segments_text(segments: list) -> str:
    return "".join(s["text"] + "".join(f" `[{n}]`" for n in s.get("cite", [])) for s in segments)


def clock(seconds) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def chart_frame(spec: dict, by_segment: bool) -> pd.DataFrame:
    rows = spec.get("rows") or []
    segment = spec.get("segment")
    if by_segment and segment:
        data = {group["label"]: [row.get("by_group", {}).get(group["id"], 0) for row in rows] for group in segment["groups"]}
    else:
        data = {spec.get("measure", "participants"): [row["total"] for row in rows]}
    return pd.DataFrame(data, index=[row["label"] for row in rows])


def draw_chart(block: dict, key: str) -> None:
    """A chart is drawn only from the numbers in its spec; the title and caption are the model's words."""
    spec = block["spec"]
    st.markdown(f"**{spec['title']}**")
    if spec.get("caption"):
        st.caption(spec["caption"])
    by_segment = False
    if spec.get("segment"):
        view = st.radio("View", ["Bar", f"By {spec['segment']['field']}"], horizontal=True, key=f"{key}-view", label_visibility="collapsed")
        by_segment = view != "Bar"
    frame = chart_frame(spec, by_segment)
    st.bar_chart(frame, horizontal=True)
    notes = []
    if spec.get("denominator"):
        notes.append(f"out of {spec['denominator']}")
    flags = spec.get("flags") or {}
    if flags.get("small_groups"):
        notes.append("small sample: " + ", ".join(flags["small_groups"]))
    if flags.get("unread_files"):
        notes.append(f"{flags['unread_files']} files not read")
    if flags.get("estimate"):
        notes.append("estimate")
    if spec.get("segment") and spec["segment"].get("unknown"):
        notes.append(f"{spec['segment']['unknown']} with no {spec['segment']['field']}")
    if notes:
        st.caption(" · ".join(notes))
    with st.expander("View data"):
        st.dataframe(frame, width="stretch")


def draw_sources(citations: list) -> None:
    if not citations:
        return
    with st.expander(f"Sources ({len(citations)})"):
        for c in citations:
            where = c.get("title") or c.get("file_name") or c.get("file_id") or ""
            label = c["type"].replace("_", " ") + (" · AI analysis" if c.get("derived") else "")
            st.markdown(f"**[{c['n']}]** {label} · {where} {clock(c.get('start'))}")
            if c.get("quote"):
                st.caption(c["quote"])
            if c.get("url"):
                st.markdown(c["url"])


def draw_blocks(blocks: list, citations: list, key: str, live: bool) -> None:
    """`live` is True for the newest answer only, so only its follow-up chips can be clicked."""
    by_number = {c["n"]: c for c in citations}
    for index, block in enumerate(blocks):
        kind = block["type"]
        if kind == "direct":
            st.markdown(segments_text(block["segments"]))
        elif kind == "sections":
            for section in block["sections"]:
                st.markdown(f"**{section['title']}**")
                for bullet in section["bullets"]:
                    st.markdown("- " + segments_text(bullet["segments"]))
        elif kind == "chart":
            draw_chart(block, f"{key}-chart-{index}")
        elif kind == "table":
            st.markdown(f"**{block['title']}**")
            st.dataframe(pd.DataFrame([row["cells"] for row in block["rows"]], columns=block["columns"]), width="stretch", hide_index=True)
        elif kind == "ai_card":
            st.info(f"**{block['title']}** {block.get('count_label', '')}\n\n{block.get('summary', '')}")
        elif kind == "snippets":
            for snippet in block["snippets"]:
                st.caption(f"[{snippet['citation_n']}] {snippet['file_name']}")
                for line in snippet["lines"]:
                    st.markdown(f"> **{line['speaker']}** {line['time']}  \n> {line['text']}")
        elif kind == "clips":
            st.markdown("**Clips**")
            for n in block["citation_ns"]:
                c = by_number.get(n, {})
                st.caption(f"[{n}] {c.get('file_name') or c.get('file_id') or ''} {clock(c.get('start'))} · {c.get('quote', '')[:160]}")
        elif kind == "did":
            took = f" · {block['duration_seconds']}s" if block.get("duration_seconds") else ""
            with st.expander(f"What I did · {block['summary']}{took}"):
                for step in block["steps"]:
                    st.markdown(f"- {step['label']}" + (f" ({step['count']})" if step.get("count") else ""))
    draw_sources(citations)
    for block in blocks:
        if block["type"] == "followups" and live:
            st.caption("Ask next")
            for index, item in enumerate(block["items"]):
                if st.button(item["question"], key=f"{key}-follow-{index}"):
                    state.pending = item["question"]
                    st.rerun()


def draw_starters(holder, starters: dict, note: str = "") -> None:
    """The greeting, the opener and the question buttons. A button's id comes from its question, so it is the same on every run (a click is never lost) and differs between two sets drawn in one run."""
    with holder.container():
        st.header(starters.get("greeting") or "Hello")
        if starters.get("opener"):
            st.write(starters["opener"])
        for index, item in enumerate(starters["items"]):
            if st.button(item["question"], key=f"starter-{hashlib.sha1(item['question'].encode()).hexdigest()[:10]}"):
                state.pending = item["question"]
                st.rerun()
            if item.get("article_url"):
                st.caption(f"[Help article]({item['article_url']})")
        if note:
            st.caption(note)


def request_refresh(key: str) -> None:
    state.refresh_keys[key] = True


def show_starters(scope: list) -> None:
    """The greeting and the suggested questions for the selection.

    The backend answers at once from a pool the model wrote ahead of time; opening shows the same
    questions as last time and Refresh shows ones not seen before. When the pool is missing or running
    low, the page asks the backend to write more after it has drawn what it has, so it never waits."""
    key = json.dumps(scope, sort_keys=True)
    holder = st.empty()
    ask = {"scope": scope, "entry_point": entry_point(scope), "time_zone": state.time_zone}
    refresh = state.refresh_keys.pop(key, False)
    shown = state.starters.get(key)
    if shown is None or refresh:
        shown = call("get_starters", refresh=refresh, **ask)
        state.starters[key] = shown
        if not shown:
            return
        items_on_screen = shown["starters"]["items"]
        note = "That is everything for now. More ideas are on the way." if shown.get("exhausted") else ""
        if items_on_screen:
            draw_starters(holder, shown["starters"], note)
        else:
            with holder.container():
                st.caption("Writing suggestions for you…")
        if shown.get("more_coming") or not items_on_screen:
            written = call("get_starters", generate=True, **ask)
            if written and shown.get("exhausted"):
                # Nothing new was left, so the questions on screen are the old ones. Now that more are written, show them.
                again = call("get_starters", refresh=True, **ask)
                if again and again["starters"]["items"] and not again.get("exhausted"):
                    shown = again
                    state.starters[key] = shown
                    draw_starters(holder, shown["starters"])
                    written = None
            if written and not items_on_screen:
                shown = written
                state.starters[key] = shown
                if shown["starters"]["items"]:
                    draw_starters(holder, shown["starters"])
                else:
                    with holder.container():
                        st.caption("Suggestions are unavailable right now. You can still ask a question below.")
            elif written:
                state.starters[key] = {**shown, "more_coming": written["more_coming"]}
    else:
        draw_starters(holder, shown["starters"])
    shown = state.starters.get(key)
    if shown:
        timings = shown.get("timings_ms") or {}
        pool = shown.get("pool")
        detail = f" · {pool['size']} in the pool, {pool['unseen']} not shown yet" if pool else ""
        st.caption(f"Suggestions: {shown.get('source')} · {timings.get('total', '?')} ms{detail}")
        if "more_coming" not in shown:
            st.warning("This backend is an older version without Refresh, so the same questions come back. Redeploy ai-chat-staging.")
        st.button("Refresh suggestions", on_click=request_refresh, args=(key,))


def draw_notice(notice: dict) -> None:
    NOTICE_STYLE.get(notice["kind"], st.info)(notice["text"])


def run_turn(question: str, scope: list) -> None:
    """Creates the chat if needed, sends the question and draws the reply as it streams."""
    if not state.chat_id:
        created = call("create_chat", scope=scope, entry_point=entry_point(scope))
        if not created:
            return
        state.chat_id = created["chat_id"]
    state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    blocks, citations, notices = [], [], []
    with st.chat_message("assistant"):
        with st.status("Working…", expanded=True) as status:
            for event in stream_events(state.chat_id, question, scope):
                if event["type"] == "step":
                    counts = ", ".join(f"{v} {k}" for k, v in event.get("counts", {}).items())
                    st.write(("✗ " if event["status"] == "failed" else "✓ ") + event["label"] + (f" · {counts}" if counts else ""))
                elif event["type"] == "block":
                    blocks.append(event["block"])
                elif event["type"] == "citations":
                    citations = event["citations"]
                elif event["type"] == "notice":
                    notices.append(event)
                elif event["type"] == "run_completed":
                    status.update(label=f"Done ({event['status']})", state="complete" if event["status"] == "complete" else "error", expanded=False)
        for notice in notices:
            draw_notice(notice)
        draw_blocks(blocks, citations, f"m{len(state.messages)}", live=True)
    state.messages.append({"role": "assistant", "blocks": blocks, "citations": citations, "notices": notices})


def open_chat(chat_id: str) -> None:
    data = call("get_chat", chat_id=chat_id)
    if data:
        state.chat_id = chat_id
        state.messages = data["messages"]


# Sidebar: sign in

with st.sidebar:
    st.title("Looppanel AI")
    st.text_input("API URL", os.environ.get("AI_CHAT_API_URL", DEFAULT_API_URL), key="api_url")
    st.text_input("User id", key="user_id")
    st.text_input("Workspace id", key="workspace_id")
    st.text_input("Time zone (for the greeting)", getattr(getattr(st, "context", None), "timezone", None) or "Asia/Kolkata", key="time_zone")
    if st.button("Sign in", type="primary", width="stretch") and state.user_id and state.workspace_id:
        listed = call("list_projects")
        if listed is not None:
            state.update(signed_in=True, projects=listed["projects"], chat_id=None, messages=[], starters={}, files={})

if not state.signed_in:
    st.info("Enter the API URL, a user id and that user's workspace id, then sign in.")
    st.stop()


# Sidebar: where to look, metadata filters, chats

with st.sidebar:
    st.divider()
    st.subheader("Where to look")
    names = [ALL_PROJECTS] + [p["name"] for p in state.projects]
    picked = st.radio("Project", names, label_visibility="collapsed")
    project = next((p for p in state.projects if p["name"] == picked), None)
    file = None
    if project:
        for s in project.get("stages", []):
            st.caption(f"{s['label']}: {s['status']}" + (f" ({s['error']})" if s.get("error") else ""))
        files = project_files(project["id"])
        file_name = st.selectbox("File", [WHOLE_PROJECT] + [f["name"] for f in files])
        file = next((f for f in files if f["name"] == file_name), None)
    scope = current_scope(project, file)
    st.caption("The selection is where the chat looks first. A question about something else is searched across every project you can open.")

    if project:
        fields = metadata_values(project_files(project["id"]))
        st.subheader("Filter by metadata")
        if not fields:
            st.caption("The files in this project carry no metadata.")
        for name, values in fields.items():
            st.multiselect(name, [f"{value} ({count})" for value, count in values.items()], disabled=True, key=f"filter-{project['id']}-{name}")
        st.caption(f"{NOT_BUILT}: filters are listed from this project's file metadata but do not narrow questions yet.")

    st.divider()
    if st.button("New chat", width="stretch"):
        state.update(chat_id=None, messages=[])
    listed_chats = call("list_chats") or {"chats": []}
    for chat in listed_chats["chats"][:20]:
        left, right = st.columns([5, 1])
        if left.button(chat.get("title") or "Untitled", key=f"open-{chat['id']}", width="stretch"):
            open_chat(chat["id"])
        if right.button("✕", key=f"del-{chat['id']}"):
            call("delete_chat", chat_id=chat["id"])
            if state.chat_id == chat["id"]:
                state.update(chat_id=None, messages=[])
            st.rerun()
    if state.chat_id:
        new_title = st.text_input("Rename this chat", key=f"rename-{state.chat_id}")
        if new_title and st.button("Save name"):
            call("rename_chat", chat_id=state.chat_id, title=new_title)
            st.rerun()


chat_tab, settings_tab = st.tabs(["Chat", "Settings"])


# Settings: organisation prompt and project summary

with settings_tab:
    st.subheader("Organisation prompt")
    st.caption("Applies to every chat in this workspace and shapes the recommended questions. Only workspace editors can change it.")
    saved = (call("get_org_context") or {}).get("org_context")
    if saved:
        st.caption(f"Saved from {saved.get('source')} · {saved.get('status')} · {saved.get('original_chars')} characters")
    text = st.text_area("About your organisation", (saved or {}).get("used_text", ""), height=200, key="org-text")
    pdf = st.file_uploader("Or upload a PDF", type=["pdf"], key="org-pdf")
    if st.button("Save organisation prompt"):
        fields_to_send = {"pdf_base64": base64.b64encode(pdf.getvalue()).decode(), "file_name": pdf.name} if pdf else {"text": text}
        result = call("set_org_context", **fields_to_send)
        if result:
            state.starters = {}
            st.success(result.get("message") or "Saved. Recommended questions will be rewritten.")

    st.divider()
    st.subheader("Project summary")
    if not project:
        st.caption("Pick a project in the sidebar to see its summary.")
    else:
        rebuild = st.button("Rebuild now")
        data = call("get_project_summary", project_id=project["id"], rebuild=rebuild)
        summary = (data or {}).get("summary")
        if not summary:
            st.caption("No summary yet. Rebuild to write one.")
        else:
            st.caption(f"{summary.get('files_summarised')} of {summary.get('files_total')} files · built {summary.get('built_at')}")
            if summary.get("files_failed"):
                st.warning("Could not summarise: " + ", ".join(summary["files_failed"]))
            st.markdown(f"**In one paragraph**\n\n{summary.get('brief') or ''}")
            st.markdown(summary.get("text") or "")
            st.json(summary.get("facts") or {}, expanded=False)


# Chat: greeting and recommended questions, or the open chat

with chat_tab:
    top_left, top_middle, top_right = st.columns([5, 2, 2])
    top_left.caption(f"Looking in: **{scope_label(scope)}**")
    top_middle.toggle("Deep research", value=False, disabled=True, help=f"{NOT_BUILT}. Fast research is the only mode today.")
    with top_right.popover("Attach a file or image"):
        st.file_uploader("File or image", type=["pdf", "png", "jpg", "jpeg"], disabled=True, key="attachment")
        st.caption(f"{NOT_BUILT}.")

    # The areas are laid out first and filled once we know whether a question is on its way, so the
    # suggestions never stay on screen (greyed out) underneath an answer that is being written.
    starters_area = st.container()
    history_area = st.container()
    typed = st.chat_input(f"Ask about {scope_label(scope)}")
    question = state.pending or typed

    if not state.chat_id and not question:
        with starters_area:
            show_starters(scope)

    with history_area:
        for index, message in enumerate(state.messages):
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.markdown(message.get("content", ""))
                else:
                    for notice in message.get("notices", []):
                        draw_notice(notice)
                    last = index == len(state.messages) - 1
                    draw_blocks(message.get("blocks", []), message.get("citations", []), f"m{index}", live=last and not question)
        if question:
            state.pending = None
            run_turn(question, scope)
    if question:
        st.rerun()
