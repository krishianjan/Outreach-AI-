"""
app.py — Hugging Face Spaces entrypoint.
HF Spaces requires the main file to be app.py.
This simply imports and launches the Gradio app from test_ui.py.

Deploy steps:
  1. Push entire project folder to a HF Space (Gradio SDK)
  2. Set secrets in HF Space Settings:
       HUNTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, SCRAPEGRAPH_API_KEY
  3. HF Spaces auto-runs: python app.py
"""

import os

# On HF Spaces free tier, use current dir for SQLite (not persistent across restarts)
# On HF Spaces with persistent storage enabled ($9/mo), set DATA_DIR=/data
os.environ.setdefault("DB_PATH", os.path.join(
    os.environ.get("DATA_DIR", "."), "outreach.db"
))

# Import the full app — this runs init_db() and builds the Gradio UI
from test_ui import demo

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        show_error=True,
    )