# Digital Leads Dashboard

This is a deployment-ready Dash dashboard for online hosting.

## Files

- `app.py` — Dash app
- `dashboard_data.csv` — source data
- `requirements.txt` — Python dependencies
- `Procfile` — start command for platforms such as Heroku
- `render.yaml` — optional Render blueprint configuration

## Deploy on Render

1. Create a GitHub repository and upload all files in this folder.
2. Go to Render and create a **New Web Service**.
3. Connect the GitHub repository.
4. Use these settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:server`
5. Deploy. Render will provide a public URL when deployment finishes.

## Run locally for testing

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8050/`.
