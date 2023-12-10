import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("DISCORD_GUILD")
CHAN = os.getenv("DISCORD_CHAN")
DB = os.getenv("DB_PATH", ".db")
KOBOLD_HOST = os.getenv("KOBOLD_HOST", "http://127.0.0.1:5000/api")
PROMPT_BASE = json.loads(os.getenv("PROMPT_BASE", "null")) or {
    "use_story": False,
    "use_memory": False,
    "use_authors_note": False,
    "use_world_info": False,
    "max_context_length": 8192,
    "max_length": 100,
    "rep_pen": 1.2,
    "rep_pen_range": 2048,
    "rep_pen_slope": 0,
    "temperature": 0.51,
    "tfs": 0.99,
    "top_a": 0,
    "top_k": 0,
    "top_p": 1,
    "min_p": 0,
    "typical": 1,
    "sampler_order": [6, 0, 1, 3, 4, 2, 5],
    "singleline": False,
    "use_default_badwordsids": False,
    "mirostat": 0,
    "mirostat_eta": 0.1,
    "mirostat_tau": 5,
    "grammar": "",
    "stop_sequence": ["\n", "\n### Instruction:", "\n### Response:"],
}
