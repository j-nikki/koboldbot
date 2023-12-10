import json
import re
from typing import AsyncGenerator

import discord
from discord.ext import commands

from koboldbot.config import CHAN, KOBOLD_HOST, PROMPT_BASE, TOKEN
from koboldbot.message_event import EventSource
from koboldbot.prompt import (
    Char,
    Exchange,
    UserError,
    add_example,
    format_prompt,
    insert_exchange,
    padd,
    pex,
    put_char,
)


def _at_author(ctx: commands.Context):
    return (
        ""
        if ctx.channel.type == discord.ChannelType.private
        else f"{ctx.author.mention} "
    )


async def _generate(
    message: discord.Message, ctx: commands.Context
) -> AsyncGenerator[str, None]:
    prompt = format_prompt(message)
    input_ = {
        **PROMPT_BASE,
        "prompt": prompt.prompt,
    }
    url = f"{KOBOLD_HOST}/extra/generate/stream"
    payload = json.dumps(input_)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    res = ""
    acc = ""
    ntok = 0
    maxtok = input_["max_length"]
    async with EventSource(
        url, option={"method": "POST"}, no_reconnect=True, data=payload, headers=headers
    ) as event_source:
        async for event in event_source:
            token: str = json.loads(event.data)["token"]
            if m := re.match(r"([\.?!])(\s*)", token):
                acc += m[1]
                res += acc
                yield res
                acc = m[2]
            else:
                acc += token
            ntok += 1
            if ntok == maxtok:
                break
    res = res.strip()
    if res:
        insert_exchange(prompt, res)


class MyClient(commands.Bot):
    _gens: dict[int, AsyncGenerator[str, None]] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gens = {}

    async def on_ready(self):
        print("Logged on as", self.user)

    async def on_message(self, message: discord.Message):
        if message.channel.name != CHAN:
            return
        ctx = await self.get_context(message)
        if message.author == self.user:
            return
        if message.content.startswith("!add"):
            m = padd.match(message.content)
            if not m:
                await ctx.send(
                    f"{_at_author(ctx)}Invalid syntax. Example:\n{add_example}"
                )
                return
            name, description, pline, examples = m.groups()
            lstex = list(pex.finditer(examples))
            if sum(len(m[0]) for m in lstex) != len(examples):
                await ctx.send(f"{_at_author(ctx)}Invalid examples.")
                return
            char = Char(
                user_id=message.author.id,
                name=name.strip(),
                description=description.strip(),
                pline=pline.strip(),
                examples=[
                    Exchange(prompt=m[1].strip(), response=m[2].strip()) for m in lstex
                ],
            )
            try:
                put_char(char)
                await ctx.send(f"{_at_author(ctx)}Added character {name}.")
            except:
                await ctx.send(f"{_at_author(ctx)}Failed to add character.")
            return
        try:
            async with ctx.typing():
                msg: discord.Message | None = None
                async for res in _generate(message, ctx):
                    if msg:
                        await msg.edit(content=f"{_at_author(ctx)} {res}")
                    else:
                        msg = await ctx.send(f"{_at_author(ctx)} {res}")
        except UserError as e:
            await ctx.send(f"{_at_author(ctx)}{e.message}")


intents = discord.Intents.all()
intents.message_content = True
client = MyClient(intents=intents, command_prefix="!")

client.run(TOKEN)
