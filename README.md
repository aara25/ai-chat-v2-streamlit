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
