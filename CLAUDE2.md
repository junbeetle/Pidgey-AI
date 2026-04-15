Please read the current README.md and update it with:

1. Add live URLs at the very top:
   Frontend: https://hong-agentic-ai-p1.web.app
   Backend: https://pidgey-ai-backend-836832472845.us-central1.run.app

2. Make sure these sections exist and are accurate:
   - Step 1 Collect: eBird API + Open-Meteo, runtime fetching,
     file + function names
   - Step 2 EDA: pandas operations before LLM, what's computed,
     file + function names  
   - Step 3 Hypothesize: grounded in data, cites numbers,
     file + function names
   - Core Requirements table with file locations
   - Grab-bag electives table (Structured Output, Second Data
     Retrieval, Data Visualization, Parallel Execution)
   - OOS three-layer architecture description
   - How to run locally
   - Sample queries

Read these files first to get accurate function names:
backend/main.py, backend/graph.py, backend/agents/eda_agent.py,
backend/agents/hypothesis_agent.py, backend/tools/ebird_tool.py