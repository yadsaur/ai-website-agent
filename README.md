# AI Website Agent — Quick Start

## Setup
```bash
chmod +x setup.sh && ./setup.sh
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

## Optional: Enable LLM (better answers)
```bash
# Install Ollama: https://ollama.com
ollama pull mistral:7b-instruct-q4_K_M
ollama serve  # runs on localhost:11434
```

## Usage
1. Open http://localhost:8000/dashboard
2. Enter a website URL → click "Process Website"
3. Wait for status: Ready (1-3 min depending on site size)
4. Click "Get Embed Code" → copy the <script> tag
5. Paste into any HTML page's <body>
6. Open that HTML page → chat widget appears

## Without Ollama
The system still works — it uses the top retrieved chunk as the answer.
Answers are accurate but less conversational. Install Ollama for full RAG.
