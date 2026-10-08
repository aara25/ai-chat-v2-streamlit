# Looppanel AI chat - Streamlit test page

`streamlit_app.py` is the page for the new AI chat (the first cut), and it is the main file for the Streamlit app. The old AI Chat v2 page is kept as a copy in `ai_chat_v2_app.py`; it is not the app's main file.

| Page | File | Backend |
|---|---|---|
| New AI chat (first cut) | `streamlit_app.py` | the `ai-chat-staging` function (`ai_chat` in the looppanel-backend repo) |
| AI Chat v2 (being deprecated, kept as a copy) | `ai_chat_v2_app.py` | the `ai-chat-v2` function |

## New AI chat: `streamlit_app.py`

Sign in with a user id and that user's workspace id. The page has a project and file picker (a question about something else is searched across every project the user can open), the greeting and recommended questions for the selection, Fast research with streamed steps, sources and follow-up questions, chat history, and a Settings tab with the organisation prompt and the project summary. Deep research, metadata filtering and attaching files are shown disabled until the backend supports them.

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The backend URL defaults to `https://us-central1-looppanel.cloudfunctions.net/ai-chat-staging`. Change it in the "API URL" field, or set `AI_CHAT_API_URL`.

On Streamlit Community Cloud, the main file is `streamlit_app.py`.

Note: the new page asks for a user id and workspace id and the backend trusts both, so the same access warning below applies to it: restrict who can open a hosted copy.

---

# AI Chat v2 - Streamlit UI (kept as a copy, `ai_chat_v2_app.py`)

A front end for the `ai_chat_v2` Cloud Function (lives in the looppanel-backend repo). It signs in with email, workspace ID and project ID, lists the project's shared threads, and streams each answer live: which agent the supervisor called, that agent's own reasoning as it happens, the tools it ran (with their actual arguments and response, not just a status), the final answer and its evidence, and this workspace's token usage per model (daily and per-thread budgets) in the sidebar.

## Run locally

```
pip install -r requirements.txt
streamlit run ai_chat_v2_app.py
```

The backend URL is hardcoded in `ai_chat_v2_app.py` (`API_URL`), currently `https://us-central1-looppanel.cloudfunctions.net/ai-chat-v2`. Change that constant if the deployed function's URL ever changes.

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. On share.streamlit.io, create an app from that repo with main file `ai_chat_v2_app.py`.

The function must be reachable from the internet, and its CORS is not involved (Streamlit calls it from the server, not the browser).

## Access warning

Sign-in is an email lookup with no password, the same check the backend does. A publicly hosted app lets anyone who knows a valid email, workspace ID and project ID read that project's threads. Restrict the app's viewers in Streamlit Cloud's sharing settings, or add real authentication before exposing it.

Note: the new page asks for a user id and workspace id and the backend trusts both, so the same access warning applies to it: restrict who can open a hosted copy.
