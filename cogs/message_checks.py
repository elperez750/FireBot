import discord, asyncio
import os
import asyncpg
from cogs.unicode_codes import UNICODE_EMOJI
from datetime import datetime, timedelta
from cogs.perspective import perspective
import re
import time
from discord.ext import commands, tasks


class AdminCommands(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.perspective_obj = perspective.Perspective(os.environ["perspective_api_key"])
        self.check.start()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        author = message.author # Defines the message author
        content = message.content # Defines the message content
        channel = message.channel # Defines the message channel
        if str(channel) == "logs": return
        logchannel = self.client.get_channel(741011181484900464) # Defines the logs channel

        embed = discord.Embed(colour=discord.Colour.purple())
        embed.add_field(name="__**Message Delete:**__", value=f"Someone (Can be themselves) deleted {author.mention}'s message in the channel {channel.mention}")
        if message.embeds and author.bot: embed.add_field(name=f"{author} said an embed:", value="__THIS IS SUPPOSED TO BE AN EMBED__")
        else: embed.add_field(name=f'{author} said:', value=f'{content}')

        await logchannel.send(embed=embed) # Send the message.

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        channel = messages[0].channel  # Defines the message channel
        if str(channel) == "logs": return
        logchannel = self.client.get_channel(741011181484900464)  # Defines the logs channel

        embed = discord.Embed(colour=discord.Colour.dark_purple())
        embed.add_field(name="__**Bulk Message Delete:**__", value=f"Channel: {channel.mention}")
        for msg in messages:
            author = msg.author # Defines the message author
            content = msg.content # Defines the message content

            if msg.embeds and author.bot: embed.add_field(name=f"{author} said an embed:", value="**__THIS IS AN EMBED__**", inline=False)
            else: embed.add_field(name=f"{author} said:", value=content, inline=False)

        await logchannel.send(embed=embed) # Send the message.

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        channel = before.channel  # Defines the message channel
        if str(channel) == "logs": return
        author = before.author  # Defines the message author
        if author.bot: return
        old_content = before.content  # Defines the old message content
        new_content = after.content # Defines the new message content
        if old_content == new_content: return
        logchannel = self.client.get_channel(741011181484900464)  # Defines the logs channel

        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.add_field(name="__**Message Edit:**__", value=f"{author.mention} edited their message in the channel {channel.mention}")
        embed.add_field(name=f'{author} said:', value=f'{old_content}\nNow:\n{new_content}')

        await logchannel.send(embed=embed)  # Send the message.

    @commands.Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.channel.DMChannel): return
        channel = message.channel
        content = message.content
        staff_role = discord.utils.find(lambda r: r.name.upper() == 'STAFF', message.guild.roles)

        if message.author.bot or str(channel) == "logs" or staff_role in message.author.roles: return

        start_time = time.time()
        muted_role = discord.utils.find(lambda r: r.name.upper() == 'MUTED', message.guild.roles)

        while True:
            try:
                result = await self.client.pg_con.fetchrow("SELECT * FROM infractions WHERE guild_id = $1 AND user_id = $2", message.guild.id, message.author.id)
                break
            except asyncpg.exceptions.TooManyConnectionsError:
                await asyncio.sleep(0.3)

        if not result:
            await self.client.pg_con.execute("INSERT INTO infractions(guild_id, user_id, infractions, last_infraction, last_msg) VALUES($1,$2,$3,$4,$5)", message.guild.id, message.author.id, 0, time.time()-20, time.time()-2)
            result = await self.client.pg_con.fetchrow("SELECT * FROM infractions WHERE guild_id = $1 AND user_id = $2", message.guild.id, message.author.id)

        infractions = 0
        if float(time.time()) - float(result['last_infraction']) > 20:
            await self.client.pg_con.execute(
                "UPDATE infractions SET infractions = $1 WHERE guild_id = $2 and user_id = $3", 0, message.guild.id,
                message.author.id)
            while True:
                try:
                    result = await self.client.pg_con.fetchrow(
                        "SELECT * FROM infractions WHERE guild_id = $1 AND user_id = $2", message.guild.id,
                        message.author.id)
                    break
                except asyncpg.exceptions.TooManyConnectionsError:
                    await asyncio.sleep(0.3)

        ## AUTOMOD QUICK MESSAGE
        if start_time-float(result['last_msg'])<0.4:
            infractions+=0.4
        
        ## AUTOMOD EMOJI SPAM
        emojis_list = map(lambda x: ''.join(x.split()), UNICODE_EMOJI.keys())
        r = re.compile('|'.join(re.escape(p) for p in emojis_list))
        emoji_count = len(r.findall(content)) + len(re.findall(r'<a?:\w*:\d*>', content))
        if emoji_count>5:
            infractions+=emoji_count/10+0.3

        ## AUTOMOD REPEATED TEXT
        repeated_check = content.replace(" ", "")
        if len(content)>15:
            repeated = 0
            temp = (repeated_check + repeated_check).find(repeated_check, 1, -1)
            if temp != -1:
                repeated = len(repeated_check) / temp
            infractions+=round(repeated/3.5, 2)

        ## AUTOMOD SELFBOT DETECTOR
        if message.embeds:
            infractions+=2

        ## AUTOMOD MASS PING
        mentions = len(message.mentions)
        if mentions > 2:
            mentions = len(message.raw_mentions)
            infractions += mentions - (.51*mentions)
            infractions -= (len(content) - (22 * mentions)) * 0.005
            infractions = round(infractions, 2)

        ## AUTOMOD FILTER
        try:
            comment = self.perspective_obj.score(content, tests=["TOXICITY", "SEVERE_TOXICITY", "SEXUALLY_EXPLICIT"])
            severe_toxic = comment["SEVERE_TOXICITY"].score
            toxic = comment["TOXICITY"].score
            sexual = comment["SEXUALLY_EXPLICIT"].score
            # spam = comment["SPAM"].score

            if sexual > 0.8:
                infractions += 0.75
            elif toxic > 0.6:
                if severe_toxic > 0.8:
                    infractions += 0.65
                else:
                    infractions += 0.4
            # if spam>0.5:infractions+=spam
        except:pass

        ## DISCORD LINK CHECK
        REGEX = re.compile('(https?:\/\/)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/.+[a-z0-9]')
        links = REGEX.findall(content)
        if links:
            ignore = False
            for invite in await message.guild.invites():
                if str(invite) == str(content).strip():
                    ignore = True
                    break
            if not ignore:
                await message.delete()
                infractions+=0.6

                channel = self.client.get_channel(741011181484900464)
                staff = discord.utils.get(message.guild.roles, id=749953613773930497)

                embed = discord.Embed(colour=discord.Colour.red())

                embed.add_field(name=f'__**A discord link has been detected!**__', value=f"Sender: <@{message.author.id}>", inline=False)
                embed.add_field(name=f"Msg: {content}", value=f"Link to msg: {message.jump_url}", inline=False)
                embed.set_footer(text=f"ID: {message.author.id}")
                await channel.send(staff.mention, embed=embed)
                await message.author.send(f"You are not allowed to send discord invites in this server. If you believe this was a mistake please contact staff.\nYour messsage: **{content}**")
        if float(result['infractions']) + float(infractions) > 2:
            await message.author.add_roles(muted_role)

            to_del = []
            async for old_message in channel.history(limit=100, after=datetime.utcnow() - timedelta(seconds=25)):
                if old_message.author.id == message.author.id:
                    to_del.append(old_message)
            await channel.delete_messages(to_del)

            channel = self.client.get_channel(741011181484900464)

            embed = discord.Embed(colour=discord.Colour.red(), title="__**AUTOMOD MUTE**__",
                                  icon_url=self.client.user.avatar_url,
                                  description=f"**{message.author}** has been muted for 20 minutes for getting too many mini-infractions in 20 seconds.")
            await channel.send(embed=embed)

            await message.author.send(
                f"You have been muted in **{message.guild}** for 20 minutes for getting too many mini-infractions in 20 seconds.")

            await self.client.pg_con.execute(
                "UPDATE infractions SET infractions = $1, last_infraction = $2, last_msg = $3 WHERE guild_id = $4 and user_id = $5",
                0,
                time.time(), time.time(), message.guild.id, message.author.id)

        elif infractions:
            while True:
                try:
                    await self.client.pg_con.execute(
                        "UPDATE infractions SET infractions = $1, last_infraction = $2, last_msg = $3 WHERE guild_id = $4 and user_id = $5",
                        float(infractions) + float(result['infractions']), time.time(), time.time(), message.guild.id,
                        message.author.id)
                    break
                except asyncpg.exceptions.TooManyConnectionsError:
                    await asyncio.sleep(0.3)

    @tasks.loop(seconds=20)
    async def check(self):
        while True:
            try:
                result = await self.client.pg_con.fetch("SELECT last_infraction, user_id, guild_id FROM infractions")
                break
            except asyncpg.exceptions.TooManyConnectionsError:
                await asyncio.sleep(0.3)
        for row in result:
            guild = self.client.get_guild(int(row['guild_id']))
            muted_role = discord.utils.find(lambda r: r.name.upper() == 'MUTED', guild.roles)
            user = guild.get_member(int(row['user_id']))
            if user is None:
                return await self.client.pg_con.execute("DELETE FROM infractions WHERE guild_id = $1 and user_id = $2", row['guild_id'], row['user_id'])
            if float(time.time())-float(row['last_infraction']) > 1200 and muted_role in user.roles:
                await user.remove_roles(muted_role)


def setup(client):
    client.add_cog(AdminCommands(client))
