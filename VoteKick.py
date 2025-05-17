import nextcord
from nextcord import SlashOption
from nextcord.ext import commands
from nextcord.ui import Button, View
import asyncio

bot = commands.Bot(command_prefix=["/", "!"], intents=nextcord.Intents.all())
active_votes = {}
active_voice_votes = {}
vote_lock = asyncio.Lock()
CONFIG = {
    "ADMIN_ROLES": {1197136679744577627, 1274023850119659750, 1300198400964427989},
    "RESTRICT_ROLE_ID": 1355611947692982513,
    "COOLDOWN_SECONDS": 300,
    "RESTRICTION_DURATION": 1800,
}

class VoteView(View):
    def __init__(self, user, reason, interaction):
        super().__init__()
        self.user = user
        self.reason = reason
        self.interaction = interaction
        self.vote_result = {"yes": 0, "no": 0}
        self.id_voted = set()
        self.remaining_seconds = 30
        self.vote_message = None
        self.add_item(AcceptButton(self))
        self.add_item(RejectButton(self))

    def build_embed(self):
        embed = nextcord.Embed(
            title="📢 Vote to Restrict a Member",
            description=(
                f"A vote has been started to restrict {self.user.mention} from the voice channel.\n"
                f"**Reason:** {self.reason}"
            ),
            color=nextcord.Color.orange()
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"Vote ends in {self.remaining_seconds} seconds.")
        embed.add_field(
            name="Current votes",
            value=f"✅ Yes: {self.vote_result['yes']}\n❌ No: {self.vote_result['no']}",
            inline=False
        )
        return embed

    async def start_timer(self):
        for _ in range(0, 30, 5):
            await asyncio.sleep(5)
            self.remaining_seconds -= 5
            try:
                await self.vote_message.edit(embed=self.build_embed())
            except (nextcord.errors.NotFound, nextcord.errors.Forbidden):
                break

class AcceptButton(Button):
    def __init__(self, parent_view):
        super().__init__(label="✅ Yes", style=nextcord.ButtonStyle.success)
        self.parent_view = parent_view

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer()

        if interaction.user.id == self.parent_view.user.id:
            embed = nextcord.Embed(
                description="❌ **You cannot vote against yourself!**",
                color=nextcord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if interaction.user.id in self.parent_view.id_voted:
            embed = nextcord.Embed(
                description="❗ **You have already voted!**",
                color=nextcord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        self.parent_view.vote_result["yes"] += 1
        self.parent_view.id_voted.add(interaction.user.id)
        await self.parent_view.vote_message.edit(embed=self.parent_view.build_embed())

class RejectButton(Button):
    def __init__(self, parent_view):
        super().__init__(label="❌ No", style=nextcord.ButtonStyle.danger)
        self.parent_view = parent_view

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer()

        if interaction.user.id == self.parent_view.user.id:
            embed = nextcord.Embed(
                description="❌ **You cannot vote against yourself!**",
                color=nextcord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if interaction.user.id in self.parent_view.id_voted:
            embed = nextcord.Embed(
                description="❗ **You have already voted!**",
                color=nextcord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        self.parent_view.vote_result["no"] += 1
        self.parent_view.id_voted.add(interaction.user.id)
        await self.parent_view.vote_message.edit(embed=self.parent_view.build_embed())

class VoteKick(commands.Cog):
    @nextcord.slash_command(
        name="vote_kick",
        description="Vote to restrict a user from the voice channel",
        guild_ids=[1197116207283834980]
    )
    async def __vote_kick(
        self,
        interaction: nextcord.Interaction,
        user: nextcord.Member,
        reason: str = SlashOption(
            name="reason",
            description="Select a reason",
            choices=[
                "❗ Offensive behavior",
                "📢 Spam / Flood",
                "🎤 Mic abuse / Noise",
                "😡 Inappropriate behavior",
                "🚫 Rule violation",
                "📝 Other"
            ]
        )
    ):
        if interaction.user.id == user.id:
            await interaction.response.send_message(
                "❌ You cannot vote to restrict yourself!", ephemeral=True
            )
            return

        if any(role.id in CONFIG["ADMIN_ROLES"] for role in user.roles):
            await interaction.response.send_message(
                "❌ You cannot initiate a vote against an administrator!", ephemeral=True
            )
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel!", ephemeral=True
            )
            return

        if not user.voice or not user.voice.channel:
            await interaction.response.send_message(
                "❌ This user is not in a voice channel!", ephemeral=True
            )
            return

        if interaction.user.voice.channel != user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be in the same voice channel as the user!", ephemeral=True
            )
            return

        voice_channel = interaction.user.voice.channel

        # ❗ Check if a vote is already running in this voice channel
        async with vote_lock:
            if voice_channel.id in active_voice_votes:
                embed = nextcord.Embed(
                    title="🕓 Vote Already Running",
                    description="A vote is already in progress in this voice channel. Please wait until it finishes.",
                    color=nextcord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # 🔒 Cooldown for voting against same user
        if user.id in active_votes:
            remaining = int(CONFIG["COOLDOWN_SECONDS"] - (asyncio.get_event_loop().time() - active_votes[user.id]))
            if remaining > 0:
                cooldown_embed = nextcord.Embed(
                    title="⏳ Cooldown Active",
                    description=f"You must wait `{remaining}` seconds before initiating another vote against this user.",
                    color=nextcord.Color.orange()
                )
                await interaction.response.send_message(embed=cooldown_embed, ephemeral=True)
                return

        view = VoteView(user, reason, interaction)
        view.vote_message = await interaction.response.send_message(embed=view.build_embed(), view=view)

        # ✅ Register both user and channel as active
        async with vote_lock:
            active_votes[user.id] = asyncio.get_event_loop().time()
            active_voice_votes[voice_channel.id] = asyncio.get_event_loop().time()

        await view.start_timer()

        if view.vote_result["yes"] > view.vote_result["no"]:
            role = nextcord.utils.get(interaction.guild.roles, id=CONFIG["RESTRICT_ROLE_ID"])
            await user.add_roles(role)

            result = nextcord.Embed(
                title="Vote ended",
                description=f"✅ {user.mention} will be restricted from the channel.",
                color=nextcord.Color.green()
            )
            await view.vote_message.edit(embed=result, view=None)

            try:
                dm_embed = nextcord.Embed(
                    title="🔇 You were restricted",
                    description="You were restricted from the voice channel due to community vote.",
                    color=nextcord.Color.red()
                )
                dm_embed.add_field(name="Reason", value=reason)
                await user.send(embed=dm_embed)
            except (nextcord.Forbidden, nextcord.HTTPException):
                pass

        elif view.vote_result["yes"] < view.vote_result["no"]:
            result = nextcord.Embed(
                title="Vote ended",
                description=f"❌ {user.mention} will not be restricted from the channel.",
                color=nextcord.Color.red()
            )
            await view.vote_message.edit(embed=result, view=None)

        else:
            result = nextcord.Embed(
                title="Vote ended",
                description="❔ The votes are tied. No action taken.",
                color=nextcord.Color.greyple()
            )
            await view.vote_message.edit(embed=result, view=None)

        await asyncio.sleep(2)
        try:
            await view.vote_message.delete()
        except (nextcord.errors.NotFound, nextcord.errors.Forbidden):
            pass

        # ✅ Cleanup vote lock for this voice channel
        async with vote_lock:
            active_voice_votes.pop(voice_channel.id, None)

        # ✅ Apply restriction
        if view.vote_result["yes"] > view.vote_result["no"] and user.voice and user.voice.channel:
            overwrite = nextcord.PermissionOverwrite(connect=False)
            await voice_channel.set_permissions(user, overwrite=overwrite)
            try:
                await user.move_to(None)
            except nextcord.errors.HTTPException:
                pass

        if view.vote_result["yes"] > view.vote_result["no"]:
            saved_channel = voice_channel
            await asyncio.sleep(CONFIG["RESTRICTION_DURATION"])

            role = nextcord.utils.get(interaction.guild.roles, id=CONFIG["RESTRICT_ROLE_ID"])
            await saved_channel.set_permissions(user, overwrite=None)

            try:
                await user.remove_roles(role)
            except nextcord.Forbidden:
                pass

    @nextcord.slash_command(
        name="unban",
        description="Remove restriction from a user in all or one voice channel",
        guild_ids=[1197116207283834980],
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def unban(
        self,
        interaction: nextcord.Interaction,
        user: nextcord.Member,
        channel: str = SlashOption(
            name="channel",
            description="Select a channel or 'All'",
            choices=["All", "💭┃discussions", "🦉┃working", "⚓┃meeting room", "🎮┃playing", "🍺┃chillout"]
        )
    ):
        await interaction.response.defer(ephemeral=True)

        role = nextcord.utils.get(interaction.guild.roles, id=CONFIG["RESTRICT_ROLE_ID"])

        if role and role in user.roles:
            await user.remove_roles(role)

        if channel == "All":
            for ch in interaction.guild.voice_channels:
                await ch.set_permissions(user, overwrite=None)
            await interaction.followup.send(
                f"✅ Restrictions removed in all voice channels for {user.mention}.", ephemeral=True
            )
        else:
            voice_channel = nextcord.utils.get(interaction.guild.voice_channels, name=channel)
            if voice_channel:
                await voice_channel.set_permissions(user, overwrite=None)
                await interaction.followup.send(
                    f"✅ Restriction removed in {voice_channel.name} for {user.mention}.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Error: channel {channel} not found.", ephemeral=True
                )

def setup(bot: commands.Bot):
    bot.add_cog(VoteKick(bot))