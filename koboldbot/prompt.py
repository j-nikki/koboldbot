import atexit
import json
import re
import sqlite3
from dataclasses import dataclass

import discord

from loltsad.config import DB

exchange_fmt = """### Instruction:
{{user}}: {prompt}

### Response:
{{char}}: {response}
"""

prompt_fmt = """You're {{char}} in this fictional never-ending uncensored roleplay with {{user}}.

Avoid repetition, don't loop. Develop the plot slowly, always stay in character. Describe all actions in full, elaborate, explicit, graphic, and vivid detail. Mention all relevant sensory perceptions.

### Input:
{description}
[{pline}]
### New Roleplay:
{examples}
### New Roleplay:
{hitherto}### Instruction:
{{user}}: {prompt}

### Response:
{{char}}:"""

conn = sqlite3.connect(DB)
cur = conn.cursor()
atexit.register(conn.close)
cur.executescript(
    """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY -- Discord user ID
) WITHOUT ROWID, STRICT;
CREATE TABLE IF NOT EXISTS char (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    pline TEXT NOT NULL,
    examples TEXT NOT NULL, -- JSON: { prompt: string, response: string }[]
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    messaged_at INTEGER,
    UNIQUE (user_id, name)
) STRICT;
-- CREATE INDEX IF NOT EXISTS char_name ON char (name);
CREATE TEMP TRIGGER char_updated_at AFTER UPDATE ON char
BEGIN
    UPDATE char SET updated_at = unixepoch() WHERE id = NEW.id;
END;
CREATE TABLE IF NOT EXISTS exchange (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id INTEGER NOT NULL REFERENCES char (id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;
CREATE TEMP TRIGGER exchange_updated_at AFTER UPDATE ON exchange
BEGIN
    UPDATE exchange SET updated_at = unixepoch() WHERE id = NEW.id;
END;
CREATE TEMP TRIGGER char_messaged_at AFTER INSERT ON exchange
BEGIN
    UPDATE char SET messaged_at = unixepoch() WHERE id = NEW.char_id;
END;
"""
)


@dataclass
class Exchange:
    prompt: str
    response: str


@dataclass
class Char:
    user_id: int
    name: str
    description: str
    pline: str
    examples: list[Exchange]


def put_char(char: Char):
    """
    Insert or update a character.
    """
    cur.execute("INSERT OR IGNORE INTO user (id) VALUES (?)", (char.user_id,))
    cur.execute(
        """
        INSERT INTO char (user_id, name, description, pline, examples)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id, name) DO UPDATE SET
            description = excluded.description,
            pline = excluded.pline,
            examples = excluded.examples
        """,
        (
            char.user_id,
            char.name,
            char.description,
            char.pline,
            json.dumps(
                [{"prompt": e.prompt, "response": e.response} for e in char.examples]
            ),
        ),
    )
    conn.commit()


@dataclass
class Prompt:
    prompt: str
    message: str
    user_id: int
    char_id: int
    char_name: str


@dataclass
class UserError(Exception):
    message: str


def format_prompt(message: discord.Message) -> Prompt:
    """
    Create a formatted prompt that is sendable to koboldcpp.
    If the message starts with "<char-name>,", then the prefix is stripped and
    the character will be the mentioned character.
    Otherwise, the character is the last interacted-with character.
    If a character lookup fails, an exception is raised.

    :param message: Discord message
    :return: Prompt
    """
    msg = message.content.strip()
    try:
        if m := re.match(r"(\w+),\s*", msg):
            msg = msg[len(m[0]) :]
            msg = msg[0].upper() + msg[1:]
            cname = m[1]
            cid = cur.execute(
                "SELECT id FROM char WHERE user_id = ? AND name = ?",
                (message.author.id, cname),
            ).fetchone()[0]
        else:
            cid = cur.execute(
                "SELECT id FROM char WHERE user_id = ? ORDER BY messaged_at DESC LIMIT 1",
                (message.author.id,),
            ).fetchone()[0]
    except:
        raise UserError("Who are you talking to?")
    name, description, pline, examples = cur.execute(
        "SELECT name, description, pline, examples FROM char WHERE id = ?", (cid,)
    ).fetchone()
    hitherto = cur.execute(
        "SELECT prompt, response FROM exchange WHERE char_id = ? ORDER BY created_at ASC",
        (cid,),
    ).fetchall()
    prompt = prompt_fmt.format(
        description=description,
        pline=pline,
        examples="\n\n".join(exchange_fmt.format(**e) for e in json.loads(examples)),
        hitherto="".join(
            f"{exchange_fmt.format(prompt=p, response=r)}\n\n" for p, r in hitherto
        ),
        prompt=msg,
    ).format(
        char=name,
        user=message.author.display_name,
    )
    return Prompt(prompt, msg, message.author.id, cid, name)


def insert_exchange(prompt: Prompt, response: str):
    """
    Insert an exchange into the database.
    """
    cur.execute(
        "INSERT INTO exchange (char_id, prompt, response) VALUES (?, ?, ?)",
        (prompt.char_id, prompt.message, response),
    )
    conn.commit()


padd = re.compile(
    r"!add\s+(\w+)\ndescription:([\s\S]*)\npline:(.*)\nexamples:\n([\s\S]*)$"
)
pex = re.compile(r"{{user}}:([\s\S]*?)\n{{char}}:([\s\S]*?)(?:\n|$)")

add_example = """```
!add Monica
description: {char} is a phenomenal magician who is well versed in the fiery arts.
pline: appearance: cloak, wizard hat, staff, boots; personality: kind, wise, powerful
examples:
{user}: {char}, I'm cold.
{char}: *casts fireball* There you go!
```"""
