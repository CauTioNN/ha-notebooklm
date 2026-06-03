# NotebookLM for Home Assistant

Control [Google NotebookLM](https://notebooklm.google.com) from Home Assistant.
This project gives you a config-flow integration (with re-authentication) plus a
full set of **services/actions** you can call from automations and scripts —
create notebooks, add sources, ask questions, and generate podcasts, videos,
quizzes, reports, mind maps and more.

> ⚠️ **Unofficial.** This uses Google's undocumented NotebookLM endpoints via the
> community [`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) library.
> It is **not affiliated with Google** and may break if Google changes its APIs.
> Use at your own risk. No personal data is bundled — you authenticate your own
> account through the config flow.

## What you get

- **Config flow with two sign-in options** and full **re-authentication**:
  - **Sign in with Google** — interactive Google login *inside Home Assistant*
    via the companion **NotebookLM Login add-on** (runs Chromium + noVNC).
  - **Paste credentials** — paste a `storage_state.json` you generated on your
    own computer (no add-on needed).
- **Built-in entities** (created automatically — no helpers/scripts to copy):
  - `select` **Active notebook** — pick the notebook everything acts on, no IDs.
  - `text` **Question** + `button` **Ask** + `sensor` **Last answer** — a ready
    question→answer box.
  - `sensor` **Authentication status** and **Notebooks** (list in attributes).
- **Self-documenting Home Assistant** 🏠 — export a scrubbed snapshot of your HA
  (areas, entities, automations, scripts, scenes, helpers, integrations) into a
  notebook and **ask grounded questions about your own smart home** ("where is
  the media player?", "how do I enable Shabbat mode?"). Pick which sections to
  export, choose/create a target notebook, and set an auto-sync schedule. Adds a
  `select` **Documentation sync schedule**, a `button` **Sync documentation
  now**, and a `sensor` **Documentation last synced**.
- **Voice (Assist)** — a `NotebookLMAsk` intent is registered in code; ask your
  notebook by voice and hear the answer.
- **A full service set**, designed to be automation-friendly (a configurable
  default notebook, response data, and events for long-running jobs).

## Why run NotebookLM from Home Assistant?

NotebookLM turns *your* documents (manuals, contracts, notes, research, web
pages, YouTube) into a private knowledge base you can question and reshape.
Wiring it into HA means your **home automations can use that knowledge**:

- 🎙️ **Spoken daily briefing** — every morning, ask your notebook for the key
  points and have HA read them on your speakers.
- 🤖 **Voice Q&A** — ask your appliance manuals / house docs a question from
  Assist and get a sourced answer.
- 📥 **Drop-and-digest** — drop a PDF into a watched folder → HA adds it as a
  source and generates a podcast/summary automatically, then notifies you.
- 📰 **Auto-research** — kick off a web-research import on a schedule and get a
  briefing when it's done.

## Quick start

1. Install the integration and connect (below). The question box, Ask button,
   answer sensor and voice intent appear automatically — nothing to copy.
2. (Optional) Add the card from [`examples/dashboard.yaml`](examples/dashboard.yaml)
   to a dashboard for a ready management panel.
3. Pick a notebook in the **Active notebook** dropdown — every action runs on
   it, **no IDs to type**.
4. (Optional) Add automations from [`examples/automations.yaml`](examples/automations.yaml)
   and voice sentences from [`examples/custom_sentences/`](examples/custom_sentences/).

## Installation

> One-click buttons (require the repository to be **public**; the integration
> button also needs [HACS](https://hacs.xyz) installed):
>
> [![Add integration repo to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=CauTioNN&repository=ha-notebooklm&category=integration)
> &nbsp;
> [![Add the login add-on repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCauTioNN%2Fha-notebooklm)

### 1. Integration (via HACS)

1. Click the **HACS** button above (or HACS → **Custom repositories** → add
   `https://github.com/CauTioNN/ha-notebooklm`, category **Integration**).
2. Install **NotebookLM**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → NotebookLM**.

(Manual install: copy `custom_components/notebooklm` into your `config/custom_components/`.)

### 2. (Optional) Login add-on — for "Sign in with Google"

Only needed if you want to do the Google login from inside Home Assistant:

1. Click the **add-on repository** button above (or **Settings → Add-ons →
   Add-on Store → ⋮ → Repositories** → add
   `https://github.com/CauTioNN/ha-notebooklm`).
2. Install **NotebookLM Login**, start it, open its Web UI and sign in.
   See [the add-on docs](notebooklm_login/DOCS.md).

## Authentication

Pick one in the config flow:

| Option | Needs add-on? | How |
|--------|---------------|-----|
| **Sign in with Google** | Yes | Complete Google login in the add-on, then press *Submit*. |
| **Paste credentials** | No | On your PC: `pip install "notebooklm-py[browser]"`, `notebooklm login`, then paste the contents of `~/.notebooklm/profiles/default/storage_state.json`. |

Google session cookies expire after a while. When they do, the integration
automatically starts **re-authentication** — just repeat either method.

## Options

After setup, open the integration's **Configure** dialog to set:

- **General**
  - **Default notebook** — used by every service when you omit `notebook_id`, so
    automations can stay short.
  - **Update interval** — how often the notebook list / auth status refresh.
- **Self-documenting Home Assistant** — see below.

## Self-documenting Home Assistant

Turn your Home Assistant into a notebook you can question. The integration
exports a Markdown snapshot of your setup and syncs it into a NotebookLM
notebook; the existing `notebooklm.ask` service (and the **Ask** box / voice
intent) then answer questions **grounded in your actual config, with citations**
— about *your* home, not a generic guess.

**No AI required.** The export is purely mechanical (it reads HA's registries
and states). NotebookLM itself is the AI — so there's no local LLM, no API key,
and no extra cost beyond your Google account.

**Set it up:** integration → **Configure** → **Self-documenting Home Assistant**:

- **Documentation notebook** — pick an existing notebook, or type a name to
  **create a new one**.
- **Sections to export** — tick the parts you want: Overview, Areas & Devices,
  Entities, Automations, Scripts, Scenes, Helpers, Integrations.
- **Scrub** — emails, IP addresses and long tokens are redacted from values.
  Sensitive keys (passwords, **coordinates**, tokens, cookies) are **always**
  removed regardless — nothing private leaves the building.

**Updates, not duplicates.** Each section is one source titled e.g.
`🏠 HA · Automations`. A re-sync **deletes the previous version and re-adds it**,
so you always have exactly one current source per section — it never piles up
duplicates.

**Keep it fresh:** set the **Documentation sync schedule** entity to *Manual*,
*Daily*, *Every 3 days*, *Weekly* or *Monthly*, press **Sync documentation now**
for an immediate run, or call `notebooklm.sync_documentation` from an automation.
The **Documentation last synced** sensor shows the timestamp plus status.

## Services (actions)

All services accept an optional `config_entry_id` (only needed with multiple
accounts) and an optional `notebook_id` (falls back to the default notebook).

| Service | Purpose | Returns |
|---------|---------|---------|
| `notebooklm.create_notebook` | Create a notebook | `notebook_id` |
| `notebooklm.delete_notebook` | Delete a notebook | — |
| `notebooklm.list_notebooks` | List notebooks | `notebooks` |
| `notebooklm.add_url` | Add a web/YouTube URL source | `source_id` |
| `notebooklm.add_text` | Add pasted text as a source | `source_id` |
| `notebooklm.add_file` | Upload a local file as a source | `source_id` |
| `notebooklm.add_research` | Web/Drive research import | `task_id` |
| `notebooklm.ask` | Ask the notebook a question | `answer`, `references` |
| `notebooklm.generate_audio` | Audio Overview (podcast) | `task_id` |
| `notebooklm.generate_video` | Video Overview | `task_id` |
| `notebooklm.generate_quiz` / `generate_flashcards` | Quiz / flashcards | `task_id` |
| `notebooklm.generate_report` | Briefing doc / study guide / blog post | `task_id` |
| `notebooklm.generate_slide_deck` / `generate_infographic` | Slides / infographic | `task_id` |
| `notebooklm.generate_data_table` / `generate_mind_map` | Data table / mind map | `task_id` / `note_id` |
| `notebooklm.download` | Download an artifact to a file | `path` |
| `notebooklm.sync_documentation` | Export & sync the HA snapshot (no duplicates) | `sources_written` |

Long generations are **fire-and-forget**: the service returns a `task_id`
immediately and fires an event when finished (pass `wait: true` to block and
get the download URL in the response instead).

### Events

- `notebooklm_artifact_ready` — `{notebook_id, artifact_type, artifact_id, url}`
- `notebooklm_artifact_failed` — `{notebook_id, artifact_type, artifact_id, error}`
- `notebooklm_source_added` — `{notebook_id, source_id, title}`
- `notebooklm_documentation_synced` — `{entry_id, notebook_id, categories, sources_written, status, error}`
- `notebooklm_auth_expired` — `{entry_id, account, detail}` — fired when the
  stored Google session expires and can't be refreshed. A persistent
  notification is raised automatically; wire this event to push it to your
  phone:

  ```yaml
  - trigger:
      - trigger: event
        event_type: notebooklm_auth_expired
    action:
      - action: notify.mobile_app_phone
        data:
          title: "NotebookLM signed out"
          message: "Open the NotebookLM Login add-on to sign in again."
  ```

## Examples

Ask a question and store the answer (response data):

```yaml
action: notebooklm.ask
data:
  question: "Summarize the key risks in my sources."
response_variable: result
# result.answer now holds the text
```

Generate a podcast, then act when it's ready:

```yaml
# Script: start it
- action: notebooklm.generate_audio
  data:
    instructions: "Make it upbeat, 10 minutes."

# Automation: react to completion
- trigger:
    - trigger: event
      event_type: notebooklm_artifact_ready
  condition:
    - "{{ trigger.event.data.artifact_type == 'audio' }}"
  action:
    - action: notebooklm.download
      data:
        artifact_type: audio
        output_path: /media/notebooklm/podcast.mp3
    - action: notify.mobile_app_phone
      data:
        message: "Your NotebookLM podcast is ready 🎧"
```

## Voice (Assist)

The `NotebookLMAsk` intent is **built into the integration** — no script to copy.
You only need to give Assist sentences that map to it:

1. Copy the sentence files into your config:
   - [`examples/custom_sentences/en/notebooklm.yaml`](examples/custom_sentences/en/notebooklm.yaml) → `config/custom_sentences/en/notebooklm.yaml`
   - [`examples/custom_sentences/he/notebooklm.yaml`](examples/custom_sentences/he/notebooklm.yaml) → `config/custom_sentences/he/notebooklm.yaml`
2. Restart, then say or type to Assist:
   - **"ask my notebook &lt;anything&gt;"**
   - **"שאל את המחברת &lt;כל שאלה&gt;"**

It asks the **active notebook** and speaks the answer. (With an LLM-based Assist
agent, the intent can be invoked without the sentence files.)

## FAQ

### Why use this through Home Assistant instead of the NotebookLM website?

The website is for **manual, interactive** work. Home Assistant is the layer
that **runs NotebookLM automatically and wires it into your home** — triggers,
voice, speakers, notifications, and your other devices. It doesn't replace the
site; it gives it hands and feet.

| | NotebookLM website | Through Home Assistant |
|---|---|---|
| **Triggers** | Manual — you open and click | Time, file dropped, sensor, button, webhook, presence |
| **Where output goes** | Stays on screen | Spoken on speakers (TTS), push notification, dashboard, other automations |
| **Voice / hands-free** | None | Ask your knowledge base via **Assist**, no screen |
| **Chaining steps** | Manual | One pipeline: add source → wait → generate → download → notify, in the background |
| **Who can trigger it** | Needs a Google login | Any household member, one dashboard button, no login |
| **Beyond the web UI** | Limited | Batch download, quiz/flashcard export (JSON/MD), mind-map JSON, PPTX, source fulltext |

**The website is still better for** deep interactive exploration and visually
managing sources. In one line: *the website is to work with your knowledge; Home
Assistant is to make your home work with it for you.*

## Publishing the add-on (maintainers)

The add-on ships a **prebuilt image** so users pull it instead of building the
heavy Chromium image on-device:

1. Push to `main` — the workflow in `.github/workflows/builder.yaml` builds
   `amd64` + `aarch64` images and pushes them to GHCR
   (`ghcr.io/cautionn/ha-notebooklm/{arch}-addon-notebooklm_login`; GHCR image
   names must be lowercase).
2. Make the GHCR package **public** (Packages → settings) so Home Assistant can
   pull it without auth.

Installed as a **local** add-on (copied into `/addons`), the `image:` key is
ignored and Home Assistant builds the slim Dockerfile locally instead.

## Compatibility

- Home Assistant **2024.12** or newer.
- Built on `notebooklm-py==0.6.0` (installed automatically).

## License

[MIT](LICENSE).
