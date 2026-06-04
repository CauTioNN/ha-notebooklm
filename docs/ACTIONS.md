# Actions (services) reference

Every action is registered under the `notebooklm.` domain and can be called from
automations, scripts, or **Developer Tools → Actions**.

Two arguments are shared by (almost) all of them:

- `config_entry_id` — *optional*. Which NotebookLM account to use. Only needed if
  you have more than one account configured.
- `notebook_id` — *optional*. The notebook to act on. If omitted, the action uses
  your **default notebook** (set during setup / in **Configure → General**), so
  you normally never pass it.

Long generations (audio, video, quiz, report, …) are **fire-and-forget**: the
action returns a `task_id` immediately and fires a
`notebooklm_artifact_ready` event when finished. Pass `wait: true` to block
instead and get the download URL back in the response.

---

## Notebooks

### `notebooklm.create_notebook`
Create a new notebook.
- `title` *(required)* — name of the notebook.
- **Returns:** `notebook_id`.

### `notebooklm.delete_notebook`
Delete a notebook (defaults to the default notebook).

### `notebooklm.list_notebooks`
List all notebooks in the account.
- **Returns:** `notebooks`.

## Sources

### `notebooklm.add_url`
Add a web page or YouTube URL as a source.
- `url` *(required)*, `wait` *(optional)*.
- **Returns:** `source_id`.

### `notebooklm.add_text`
Add pasted text as a source.
- `title` *(required)*, `content` *(required)*.
- **Returns:** `source_id`.

### `notebooklm.add_research`
Run a research query and import the discovered sources.
- `query` *(required)*, `source` (`web` or `drive`), `mode` (`fast` or `deep`).
- **Returns:** `task_id`.

## Ask

### `notebooklm.ask`
Ask the notebook a question and get the answer back.
- `question` *(required)*, `conversation_id` *(optional, to continue a chat)*.
- **Returns:** `answer`, `references`.

```yaml
action: notebooklm.ask
data:
  question: "Summarize the key risks in my sources."
response_variable: result
# result.answer now holds the text
```

## Generate

All generators take optional `instructions` and (most) a `language` code, plus
`wait`. They return a `task_id` (or `note_id` for the mind map).

| Action | Notable options | Returns |
|--------|-----------------|---------|
| `generate_audio` | `format` (deep-dive/brief/critique/debate), `length` | `task_id` |
| `generate_video` | `format` (explainer/brief), `style` | `task_id` |
| `generate_quiz` | `difficulty`, `quantity` | `task_id` |
| `generate_flashcards` | `difficulty`, `quantity` | `task_id` |
| `generate_report` | `format` (briefing-doc/study-guide/blog-post) | `task_id` |
| `generate_slide_deck` | `format` (detailed/presenter), `length` | `task_id` |
| `generate_infographic` | `orientation`, `detail` | `task_id` |
| `generate_data_table` | `instructions` (describe the table) | `task_id` |
| `generate_mind_map` | `instructions` | `note_id` |

### `notebooklm.download`
Download a generated artifact to a file inside Home Assistant.
- `artifact_type` *(required)*, `output_path` *(required)*, `artifact_id`
  *(optional, defaults to the latest)*, `format` (e.g. `json`, `markdown`,
  `pptx`, `csv`).
- **Returns:** `path`.

## Documentation

### `notebooklm.sync_documentation`
Export a scrubbed snapshot of Home Assistant and sync it into the documentation
notebook (replaces each section in place — no duplicates).
- `notebook_id` *(optional)*, `categories` *(optional)*.
- **Returns:** `sources_written`.

---

## Events

Wire these to automations (see [`examples/automations.yaml`](../examples/automations.yaml)):

- `notebooklm_artifact_ready` — `{notebook_id, artifact_type, artifact_id, url}`
- `notebooklm_artifact_failed` — `{notebook_id, artifact_type, artifact_id, error}`
- `notebooklm_source_added` — `{notebook_id, source_id, title}`
- `notebooklm_documentation_synced` — `{entry_id, notebook_id, categories, sources_written, status, error}`
- `notebooklm_auth_expired` — `{entry_id, account, detail}`

> The full, always-current parameter list (with selectors and defaults) lives in
> [`custom_components/notebooklm/services.yaml`](../custom_components/notebooklm/services.yaml);
> Home Assistant also shows it in the **Actions** UI.
