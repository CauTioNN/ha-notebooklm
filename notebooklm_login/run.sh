#!/usr/bin/env bash
# Entry point for the NotebookLM Login add-on.
# Starts a virtual X display, a VNC server on it, and the ingress web app.
set -e

export DISPLAY=:99
export NOTEBOOKLM_HOME=/data/notebooklm
mkdir -p "${NOTEBOOKLM_HOME}"

echo "[notebooklm-login] starting Xvfb..."
Xvfb :99 -screen 0 1360x900x24 -nolisten tcp &
sleep 1

echo "[notebooklm-login] starting x11vnc..."
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -quiet -bg

echo "[notebooklm-login] starting web app on :8099..."
exec python3 /app/app.py
