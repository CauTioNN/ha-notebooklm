# NotebookLM Login add-on

This add-on lets you sign in to Google **from inside Home Assistant** to
authenticate the [NotebookLM integration](https://github.com/teng-lin/ha-notebooklm).
It runs a real Chromium window on a virtual display and streams it to your
browser through the add-on's Ingress panel (noVNC), so you can complete the
normal Google login. The captured session is then written to your Home
Assistant config directory where the integration picks it up.

> You only need this add-on if you want the **"Sign in with Google"** option.
> The integration also supports a no-add-on path: paste a `storage_state.json`
> you generated on your own computer with `notebooklm login`.

## How to use

1. Install and **Start** the add-on, then open **Open Web UI** (Ingress).
2. Click **1. Open Google login**. A Chromium window appears in the panel.
3. Complete the Google sign-in for the account you use with NotebookLM.
4. When NotebookLM has loaded and the login window closes, click
   **2. Save credentials**. You should see *"Saved!"*.
5. Go to **Settings → Devices & Services → Add Integration → NotebookLM**,
   choose **Sign in with Google**, and press **Submit**.

You can stop the add-on after the integration has been configured.

## Notes & security

- The add-on writes the credentials to `/homeassistant/.notebooklm_login_result.json`.
  The integration **deletes that file** as soon as it has read it.
- Credentials are Google session cookies. Treat them like a password; only run
  this on a Home Assistant instance you control.
- Architectures: `amd64` and `aarch64` (Chromium availability).
- This uses Google's **undocumented** NotebookLM endpoints via the community
  `notebooklm-py` library. It is not affiliated with Google and may break if
  Google changes its APIs.

## Troubleshooting

- **Blank screen / "Display connected" but no browser:** press
  *1. Open Google login* again; Chromium can take a few seconds to appear.
- **"No credentials yet":** finish the Google sign-in (NotebookLM must finish
  loading) before pressing *Save credentials*.
