#!/bin/bash
set -e
echo "Setting up AI Website Agent..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
mkdir -p data/vectors
echo "Setup complete. Run: source venv/bin/activate && uvicorn backend.main:app --reload"
echo ""
echo "Optional: Install Ollama for LLM responses:"
echo "  curl -fsSL https://ollama.com/install.sh | sh"
echo "  ollama pull mistral:7b-instruct-q4_K_M"
