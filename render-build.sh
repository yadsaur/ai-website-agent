#!/usr/bin/env bash
set -e
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/.playwright
pip install -r requirements.txt
playwright install chromium
