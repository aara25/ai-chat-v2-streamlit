# Looppanel AI chat - Streamlit test pages

This repo holds two test pages, each its own app with its own main file:

| Page | Main file | Backend |
|---|---|---|
| New AI chat (first cut) | `ai_chat_app.py` | the `ai-chat-staging` function (`ai_chat` in the looppanel-backend repo) |
| AI Chat v2 (being deprecated) | `streamlit_app.py` | the `ai-chat-v2` function |

Run only one at a time, or deploy them as two separate apps: the pages use the same session keys and clash if combined into one multipage app.

## New AI chat: `ai_chat_app.py`

Sign in with a user id and that user's workspace id. The page has a project and file picker (a question about something else is searched across every project the user can open), the greeting and recommended questions for the selection, Fast research with streamed steps, sources and follow-up questions, chat history, and a Settings tab with the organisation prompt and the project summary. Deep research, metadata filtering and attaching files are shown disabled until the backend supports them.

```
pip install -r requirements.txt
streamlit run ai_chat_app.py
```

The backend URL defaults to `https://us-central1-looppanel.cloudfunctions.net/ai-chat-staging`. Change it in the "API URL" field, or set `AI_CHAT_API_URL`.

On Streamlit Community Cloud, create the app with main file `ai_chat_app.py`.

---

# AI Chat v2 - Streamlit UI

A front end for the `ai_chat_v2` Cloud Function (lives in the looppanel-backend repo). It signs in with email, workspace ID and project ID, lists the project's shared threads, and streams each answer live: which agent the supervisor called, that agent's own reasoning as it happens, the tools it ran (with their actual arguments and response, not just a status), the final answer and its evidence, and this workspace's token usage per model (daily and per-thread budgets) in the sidebar.

## Run locally

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The backend URL is hardcoded in `streamlit_app.py` (`API_URL`), currently `https://us-central1-looppanel.cloudfunctions.net/ai-chat-v2`. Change that constant if the deployed function's URL ever changes.

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. On share.streamlit.io, create an app from that repo with main file `streamlit_app.py`.

The function must be reachable from the internet, and its CORS is not involved (Streamlit calls it from the server, not the browser).

## Access warning

Sign-in is an email lookup with no password, the same check the backend does. A publicly hosted app lets anyone who knows a valid email, workspace ID and project ID read that project's threads. Restrict the app's viewers in Streamlit Cloud's sharing settings, or add real authentication before exposing it.

Note: the new page asks for a user id and workspace id and the backend trusts both, so the same access warning applies to it: restrict who can open a hosted copy.
