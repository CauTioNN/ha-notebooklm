"""Ingress web app for the NotebookLM Login add-on.

Serves a small control panel embedding a noVNC view of a Chromium window. The
user runs the Google sign-in interactively; the resulting ``storage_state.json``
is then copied into the Home Assistant config directory where the NotebookLM
integration's "Sign in with Google" config-flow step reads it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from aiohttp import ClientSession, WSMsgType, web

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("notebooklm-login")

VNC_HOST = "127.0.0.1"
VNC_PORT = 5900
NOVNC_DIR = "/usr/share/novnc"
STORAGE_PATH = "/data/notebooklm/profiles/default/storage_state.json"
# Home Assistant config dir is mounted here via `map: homeassistant_config:rw`.
RESULT_PATH = "/homeassistant/.notebooklm_login_result.json"
# Deep link (relative to the HA frontend origin — the Ingress page is same-origin)
# that opens the "Set up NotebookLM" dialog once credentials are saved.
SETUP_REDIRECT = "/config/integrations/dashboard/add?domain=notebooklm"
# After a successful capture we redirect the user, then stop ourselves a few
# seconds later (redirect first, so the top window has navigated away before the
# Ingress page is torn down).
SELF_STOP_DELAY = 6

_state: dict[str, object] = {"proc": None, "captured": False, "error": None}


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>NotebookLM Login</title>
<style>
  body { font-family: sans-serif; margin: 0; background: #1c1c1c; color: #eee; }
  header { padding: 10px 16px; background: #111; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  button { padding: 8px 14px; border: 0; border-radius: 6px; background: #03a9f4; color: #fff; cursor: pointer; }
  button.secondary { background: #444; }
  #status { margin-left: auto; font-size: 14px; }
  #screen { width: 100vw; height: calc(100vh - 52px); background: #000; }
  .ok { color: #8bc34a; } .err { color: #ff5252; }
</style>
</head>
<body>
<header>
  <strong>NotebookLM &mdash; Google sign-in</strong>
  <button id="start">1. Open Google login</button>
  <button id="capture" class="secondary">2. Save credentials</button>
  <span id="status">Idle</span>
  <a id="continue" href="#" target="_top" style="display:none; margin-left:10px; color:#8bc34a;">Continue to setup &rarr;</a>
</header>
<div id="screen"></div>
<script type="module">
  import RFB from './novnc/core/rfb.js';
  const base = location.pathname.replace(/\\/$/, '');
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = `${proto}://${location.host}${base}/websockify`;
  const statusEl = document.getElementById('status');

  function connect() {
    try {
      const rfb = new RFB(document.getElementById('screen'), wsUrl);
      rfb.scaleViewport = true;
      rfb.addEventListener('connect', () => { statusEl.textContent = 'Display connected'; });
      rfb.addEventListener('disconnect', () => { setTimeout(connect, 1500); });
    } catch (e) { statusEl.textContent = 'VNC error: ' + e; }
  }
  connect();

  async function post(path) {
    const r = await fetch(`${base}${path}`, { method: 'POST' });
    return r.json();
  }
  document.getElementById('start').onclick = async () => {
    statusEl.textContent = 'Launching browser...';
    const r = await post('/api/start');
    statusEl.textContent = r.status === 'started' ? 'Sign in in the window below'
      : (r.status === 'running' ? 'Already running' : ('Error: ' + (r.error || '')));
  };
  function goToSetup(url) {
    // Prefer navigating the top window (we run inside the HA Ingress iframe).
    try { window.top.location.assign(url); }
    catch (e) { window.location.assign(url); }
  }

  document.getElementById('capture').onclick = async () => {
    statusEl.textContent = 'Saving...';
    const r = await post('/api/capture');
    if (!r.ok) {
      statusEl.innerHTML = '<span class="err">' + (r.error || 'No credentials yet') + '</span>';
      return;
    }
    statusEl.innerHTML = '<span class="ok">Saved &#10003; &mdash; opening NotebookLM setup&hellip;</span>';
    const url = r.redirect || '/config/integrations/dashboard';
    // Manual fallback in case the browser blocks the auto-navigation.
    const cont = document.getElementById('continue');
    cont.href = url;
    cont.style.display = 'inline';
    setTimeout(() => goToSetup(url), 800);
  };

  setInterval(async () => {
    const r = await fetch(`${base}/api/status`).then(x => x.json());
    if (r.captured) statusEl.innerHTML = '<span class="ok">Credentials saved.</span>';
  }, 4000);
</script>
</body>
</html>
"""


async def index(_request: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def websockify(request: web.Request) -> web.WebSocketResponse:
    """Bridge the browser WebSocket to the local VNC TCP socket."""
    ws = web.WebSocketResponse(protocols=("binary",))
    await ws.prepare(request)
    try:
        reader, writer = await asyncio.open_connection(VNC_HOST, VNC_PORT)
    except OSError as err:
        _LOGGER.error("VNC connect failed: %s", err)
        await ws.close()
        return ws

    async def tcp_to_ws() -> None:
        try:
            while not ws.closed:
                data = await reader.read(65536)
                if not data:
                    break
                await ws.send_bytes(data)
        except (OSError, ConnectionError):
            pass
        finally:
            await ws.close()

    pump = asyncio.create_task(tcp_to_ws())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                writer.write(msg.data)
                await writer.drain()
            elif msg.type == WSMsgType.TEXT:
                writer.write(msg.data.encode())
                await writer.drain()
            else:
                break
    finally:
        pump.cancel()
        writer.close()
    return ws


async def api_start(_request: web.Request) -> web.Response:
    """Launch ``notebooklm login`` (opens Chromium on the virtual display)."""
    proc = _state.get("proc")
    if isinstance(proc, asyncio.subprocess.Process) and proc.returncode is None:
        return web.json_response({"status": "running"})

    env = {**os.environ, "DISPLAY": ":99", "NOTEBOOKLM_HOME": "/data/notebooklm"}
    try:
        _state["proc"] = await asyncio.create_subprocess_exec(
            "notebooklm",
            "login",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _state["captured"] = False
        _state["error"] = None
    except OSError as err:
        _state["error"] = str(err)
        return web.json_response({"status": "error", "error": str(err)})
    return web.json_response({"status": "started"})


async def api_status(_request: web.Request) -> web.Response:
    proc = _state.get("proc")
    running = isinstance(proc, asyncio.subprocess.Process) and proc.returncode is None
    return web.json_response(
        {
            "running": running,
            "captured": bool(_state.get("captured")),
            "storage_exists": os.path.exists(STORAGE_PATH),
            "error": _state.get("error"),
        }
    )


async def api_capture(_request: web.Request) -> web.Response:
    """Copy the captured storage_state into the Home Assistant config dir."""
    if not os.path.exists(STORAGE_PATH):
        return web.json_response(
            {"ok": False, "error": "No credentials yet — finish the Google sign-in first."}
        )
    try:
        payload = await asyncio.to_thread(_read_text, STORAGE_PATH)
        json.loads(payload)  # validate
        await asyncio.to_thread(_write_text, RESULT_PATH, payload)
    except (OSError, ValueError) as err:
        return web.json_response({"ok": False, "error": str(err)})
    _state["captured"] = True
    # Hand the user off to the integration setup, then shut ourselves down so the
    # heavy Chromium add-on isn't left running.
    asyncio.create_task(_schedule_self_stop(SELF_STOP_DELAY))
    return web.json_response({"ok": True, "redirect": SETUP_REDIRECT})


async def _schedule_self_stop(delay: int) -> None:
    """Stop this add-on via the Supervisor API after ``delay`` seconds.

    Falls back to exiting the process (which stops the container) if the
    Supervisor call isn't available.
    """
    await asyncio.sleep(delay)
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            async with ClientSession() as session:
                async with session.post(
                    "http://supervisor/addons/self/stop",
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status < 400:
                        _LOGGER.info("Stopping add-on via Supervisor API")
                        return
                    _LOGGER.warning(
                        "Supervisor stop returned HTTP %s; exiting instead",
                        resp.status,
                    )
        except OSError as err:
            _LOGGER.warning("Supervisor stop failed (%s); exiting instead", err)
    else:
        _LOGGER.warning("No SUPERVISOR_TOKEN; exiting to stop the container")
    # Fallback: exit the main process. run.sh `exec`s us, so the container stops.
    os._exit(0)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/websockify", websockify)
    app.router.add_post("/api/start", api_start)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/capture", api_capture)
    app.router.add_static("/novnc/", NOVNC_DIR, show_index=False)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="0.0.0.0", port=8099)
