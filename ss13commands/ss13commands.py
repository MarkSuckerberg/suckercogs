#Standard Imports
import asyncio
import ipaddress
import struct
import select
import socket
import urllib.parse
import html.parser as htmlparser
import time
import textwrap
from datetime import datetime
import logging

#Discord Imports
import discord

#Redbot Imports
from redbot.core import commands, checks, Config, utils
import json

__version__ = "1.1.0"
__author__ = "Crossedfall"

log = logging.getLogger("red.SS13Status")

class SS13Commands(commands.Cog):

    def __init__(self, bot):

        self.bot = bot
        self.config = Config.get_conf(self, 3257193194, force_registration=True)

        default_global = {
            "server": None,
            "game_port": None,
            "server_url": "byond://127.0.0.1:7777", 
            "comms_key": "default_pwd",
        }

        self.config.register_global(**default_global)

    @commands.guild_only()
    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def setss13(self, ctx):
        """
        Configuration group for the SS13 status command
        """
        pass
    
    @setss13.command(aliases=['host'])
    async def server(self, ctx, host: str):
        """
        Sets the server IP used for status checks
        """
        try:
            await self.config.server.set(host)
            await ctx.send(f"Server set to: `{host}`")
        except (ValueError, KeyError, AttributeError):
            await ctx.send("There was an error setting the host! Please check your entry and try again.")
    
    @setss13.command()
    async def port(self, ctx, port: int):
        """
        Sets the port used for the status checks
        """
        try:
            if 1024 <= port <= 65535: # We don't want to allow reserved ports to be set
                await self.config.game_port.set(port)
                await ctx.send(f"Host port set to: `{port}`")
            else:
                await ctx.send(f"`{port}` is not a valid port!")
        except (ValueError, KeyError, AttributeError):
            await ctx.send("There was a problem setting your port. Please check to ensure you're attempting to use a port from 1024 to 65535")

    @setss13.command()
    async def commskey(self, ctx, key: str):
        """
        Set the communications key for the server
        """
        try:
            await self.config.comms_key.set(key) #Used to verify incoming game data
            await ctx.send("Comms key set.")
            try:
                await ctx.message.delete()
            except(discord.DiscordException):
                await ctx.send("I do not have the required permissions to delete messages. You may wish to edit/remove your comms key manually.")
        
        except(ValueError, KeyError, AttributeError):
            await ctx.send("There was a problem setting your communications key. Please check your entry and try again.")

    @setss13.command()
    async def current(self, ctx):
        """
        Lists the current settings
        """
        settings = await self.config.all()
        embed=discord.Embed(title="__Current Settings:__")
        
        for k, v in settings.items():
            if k == 'comms_key': #We don't want to actively display the comms key
                embed.add_field(name=f"{k}:", value="`redacted`", inline=False)
            else:
                embed.add_field(name=f"{k}:", value=v, inline=False)
        
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command()
    async def send_ooc(self, ctx, message:str):
        await self.topic_query_server(ctx, querystr="ooc_send", params={"message": message})

    @commands.guild_only()
    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def send_ccannounce(self, ctx, message:str, sender="Central Command"):
        await self.topic_query_server(ctx, querystr="Comms_Console", params={"message": message, "message_sender": sender})

    @commands.guild_only()
    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def send_ahelp(self, ctx, target:str, msg:str):
        await self.topic_query_server(ctx, querystr=f"adminmsg={target}", params={"msg": msg})

    @commands.guild_only()
    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def namecheck(self, ctx, target:str):
        await self.topic_query_server(ctx, querystr=f"namecheck={target}")

    @commands.guild_only()
    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def verify(self, ctx, target:str, msg:str):
        await self.topic_query_server(ctx, querystr=f"adminmsg={target}", params={"msg": msg})

    async def topic_query_server(self, ctx, querystr="status", params=None): #I could combine this with the previous def but I'm too scared to mess with it; credit to Aurora for most of this code
        """
        Queries the server for information
        """

        server = await self.config.server()
        port = await self.config.game_port()

        message = {}
        message["sender"] = ctx.author #Coz why not
        message["source"] = "Discord"

        message.update(params)

        if(await self.config.comms_key()): #Little risky but mnehhh
            message["key"] = await self.config.comms_key()

        message = json.dumps(message, separators=("&", "=")) #This is just how SS13 (at least /tg/) seperates attributes

        message = message.replace("{", "")
        message = message.replace("}", "")
        message = message.replace("\"", "")

        message = f"?{querystr}{message}"

        await ctx.send(f"Querying gameserver with message: {message}")

        reader, writer = await asyncio.open_connection(server, port)            
        query = b"\x00\x83"
        query += struct.pack('>H', len(message) + 6)
        query += b"\x00\x00\x00\x00\x00"
        query += message.encode()
        query += b"\x00" #Creates a packet for byond according to TG's standard

        writer.write(query)

        data = b''
        while True:
            buffer = await reader.read(1024)
            data += buffer
            if len(buffer) < 1024:
                break

        writer.close()

        size_bytes = struct.unpack(">H", data[2:4])
        size = size_bytes[0] - 1

        index = 5
        index_end = index + size
        string = data[5:index_end].decode("utf-8")
        string = string.replace("\x00", "")

        await ctx.send(f"Got Answer from Gameserver: {string}")
        return string

