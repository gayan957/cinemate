# CineMate UI redesign (Streamlit)

This bundle replaces **only the frontend** of your existing CineMate repository. No agent, PostgreSQL schema, `.env`, or dependency changes are needed.

## Included files

- `frontend/app.py`: Guardian-only API client and four UI states (login, signup, before search, after search)
- `frontend/styles.css`: dark, restrained cinematic styling, with simple responsive adjustments
- `frontend/assets/cinema-backdrop.jpg`: cinematic background cropped from the earlier approved concept image; no search UI is baked into it
- `frontend/ui_utils.py`: poster matching, response formatting, safe error text
- `frontend/tests/test_ui_utils.py`: independent tests for the helper logic
- `COMMIT_PLAN.md`: a 24-step implementation sequence for meaningful student contributions

## Install into your CineMate project

In PowerShell, **from `C:\Users\LENOVO\Desktop\cinemate`**:

```powershell
# Make sure you have a clean baseline before editing
 git status
 git switch -c feat/cinemate-frontend

# Back up your existing frontend file outside this repository (or use Git to restore it later)
 Copy-Item frontend\app.py "$env:TEMP\cinemate-app-before-ui.py"
```

Extract this zip, then **copy its `frontend` folder contents into your existing CineMate `frontend` folder**, preserving the `assets` and `tests` directories. Do **not** replace your entire CineMate project folder.

If you have not already installed the project's Python requirements, use the existing project setup guide. The redesign itself adds no packages.

Run:

```powershell
python -m unittest discover -s frontend/tests -v
python run_all.py
```

Browse to `http://localhost:8501`. You can also launch the UI independently with `streamlit run frontend/app.py` while the Guardian is already running.

## Important backend constraints

- The Guardian's `/register` route accepts **username, password, age**, not email/full name/OAuth signup.
- All API calls go to `GUARDIAN_URL`. The UI does not connect directly to Orchestrator, Retrieval or Analysis.
- Poster cards use existing `posters` and `recommendations` data from `/ask`.
- "Why this match?" shows an actual returned reason and retrieval score; the score is **not** a viewer star rating.
- The app can request clarification through the existing options from Guardian.
- The background and cards are UI only: they do not create movie streaming, trailers, watchlists, or new endpoints.

## Notes

- CSS uses modern Streamlit component class names and keyed containers. The app is designed for a recent Streamlit version matching the existing code's `width="stretch"` conventions; layout details can vary by version.
- The previous 90-second Guardian timeout and resource issues are **backend limitations**; styling does not fix or override them.
- Always review with your group before pushing to a shared branch.
