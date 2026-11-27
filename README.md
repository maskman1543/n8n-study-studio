# Study Studio

Study Studio is a local web app that sends notes and PDFs to an n8n webhook and stores generated study packs in a SQLite library.

## Start the app

1. Open PowerShell in this folder.
2. Run `python server.py`.
3. Open `http://127.0.0.1:8001` in your browser.
4. Leave the server running while using the app.

The backend uses only Python's standard library. Study packs are stored in `study_library.sqlite3` beside the app files.

## Study library

- Generated packs are saved automatically.
- **Study library** lists saved packs and lets you open, edit, or delete them.
- **Edit** opens the pack JSON so you can update notes, flashcards, and quiz questions.
- Submitted quizzes are saved as attempt cards with scores, selected answers, correct answers, and explanations. Add or update a reflection note, or delete an attempt card.

The REST API is available at `/api/studies` for listing and creating packs. Use `/api/studies/{id}` to read, update, or delete one pack. Quiz attempts are listed at `/api/studies/{id}/attempts` and can be read, updated, or deleted at `/api/attempts/{attemptId}`. `/api/health` reports whether the local backend is available.

## n8n

Configure the chat model and credentials in n8n, import or update the workflow from `study_studio_n8n_workflow.json`, and publish it. Add the webhook URL in the app's **Add materials** page.
