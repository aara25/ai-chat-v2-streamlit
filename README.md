# AI Chat v2 - Streamlit UI

A front end for the `ai_chat_v2` Cloud Function (lives in the looppanel-backend repo). It signs in with email, workspace ID and project ID, lists the project's shared threads, and streams each answer live: which agent the supervisor called, the tools it ran, the final answer and its evidence.

## Run locally

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The backend URL defaults to `http://localhost:8080` (`functions-framework --target=ai_chat_v2 --debug` in the backend repo). To point at a deployed function, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set `AI_CHAT_V2_API_URL`, or set the same name as an environment variable, or use the "API connection" field on the sign-in page.

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. On share.streamlit.io, create an app from that repo with main file `streamlit_app.py`.
3. In the app's Settings -> Secrets, set `AI_CHAT_V2_API_URL` to the deployed `ai_chat_v2` function URL.

The function must be reachable from the internet, and its CORS is not involved (Streamlit calls it from the server, not the browser).

## Access warning

Sign-in is an email lookup with no password, the same check the backend does. A publicly hosted app lets anyone who knows a valid email, workspace ID and project ID read that project's threads. Restrict the app's viewers in Streamlit Cloud's sharing settings, or add real authentication before exposing it.
