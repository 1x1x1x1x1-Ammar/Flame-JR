import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

LOG_CHANNEL_FILE = "log_channel.txt"
TEMPBANS_FILE = "tempbans.json"
BLOCKED_WORDS_FILE = "blocked_words.json"
WARNINGS_FILE = "warnings.json"
INVITE_FILE = "invite.txt"

ALLOWED_ROLE_NAMES = {"Owner", "Co owner", "Manager", "Helper"}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# =========================
# File helpers
# =========================
def load_json(file_path: str, default: Any) -> Any:
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            return default
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(file_path: str, data: Any) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_log_channel_id() -> int:
    try:
        if not os.path.exists(LOG_CHANNEL_FILE):
            with open(LOG_CHANNEL_FILE, "w", encoding="utf-8") as f:
                f.write("0")
            return 0
        with open(LOG_CHANNEL_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return int(content) if content.isdigit() else 0
    except Exception:
        return 0


def write_log_channel_id(channel_id: int) -> None:
    with open(LOG_CHANNEL_FILE, "w", encoding="utf-8") as f:
        f.write(str(channel_id))


def load_tempbans() -> list[dict[str, Any]]:
    data = load_json(TEMPBANS_FILE, [])
    return data if isinstance(data, list) else []


def save_tempbans(data: list[dict[str, Any]]) -> None:
    save_json(TEMPBANS_FILE, data)


def load_blocked_words() -> dict[str, list[str]]:
    data = load_json(BLOCKED_WORDS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_blocked_words(data: dict[str, list[str]]) -> None:
    save_json(BLOCKED_WORDS_FILE, data)


def load_warnings() -> dict[str, dict[str, int]]:
    data = load_json(WARNINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_warnings(data: dict[str, dict[str, int]]) -> None:
    save_json(WARNINGS_FILE, data)


def read_invite() -> Optional[str]:
    try:
        if not os.path.exists(INVITE_FILE):
            return None
        with open(INVITE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except Exception:
        return None


def write_invite(url: str) -> None:
    with open(INVITE_FILE, "w", encoding="utf-8") as f:
        f.write(url)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_duration_to_seconds(duration: str) -> int:
    duration = duration.strip().lower()
    if len(duration) < 2:
        raise ValueError("Invalid duration format.")
    unit = duration[-1]
    value = duration[:-1]
    if not value.isdigit():
        raise ValueError("Duration number is invalid.")
    amount = int(value)
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "d":
        return amount * 24 * 60 * 60
    raise ValueError("Duration unit must be m, h, or d.")


async def safe_dm(user: discord.abc.Messageable, message: str) -> bool:
    try:
        await user.send(message)
        return True
    except Exception:
        return False


def member_has_allowed_role(member: discord.Member) -> bool:
    return any(role.name in ALLOWED_ROLE_NAMES for role in member.roles)


def get_text_channel_from_guild(guild: discord.Guild, channel_id: int) -> Optional[discord.TextChannel]:
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def send_log(guild: discord.Guild, embed: discord.Embed) -> None:
    channel_id = read_log_channel_id()
    if channel_id <= 0:
        return
    channel = get_text_channel_from_guild(guild, channel_id)
    if channel is None:
        try:
            fetched = await bot.fetch_channel(channel_id)
        except Exception:
            return
        if not isinstance(fetched, discord.TextChannel):
            return
        channel = fetched
    try:
        await channel.send(embed=embed)
    except Exception:
        pass


def build_log_embed(action: str, moderator: discord.Member, target: str, reason: str) -> discord.Embed:
    embed = discord.Embed(title=f"🔥 Flamy jr | {action}", color=discord.Color.orange(), timestamp=utc_now())
    embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=False)
    embed.add_field(name="Target", value=target, inline=False)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.set_footer(text="Flamy jr • Moderation Log")
    return embed


def build_cool_embed(action: str, target_name: str, moderator_name: str, reason: str, color: discord.Color, emoji: str) -> discord.Embed:
    embed = discord.Embed(title=f"{emoji} Flamy jr | {action}", color=color, timestamp=utc_now())
    embed.add_field(name="👤 User", value=target_name, inline=False)
    embed.add_field(name="🛡️ Moderator", value=moderator_name, inline=False)
    embed.add_field(name="📝 Reason", value=reason or "No reason provided", inline=False)
    embed.set_footer(text="Flamy jr • Action successful")
    return embed


def hierarchy_check(interaction: discord.Interaction, member: discord.Member) -> Optional[str]:
    guild = interaction.guild
    if guild is None:
        return "This command can only be used in a server."
    me = guild.me
    if me is None:
        return "I could not access my member data in this server."
    if member == interaction.user:
        return "You cannot use this command on yourself."
    if guild.owner is not None and member == guild.owner:
        return "You cannot moderate the server owner."
    if isinstance(interaction.user, discord.Member):
        if interaction.user != guild.owner and member.top_role >= interaction.user.top_role:
            return "You cannot moderate someone with an equal or higher role than you."
    else:
        return "Could not verify your server member data."
    if member.top_role >= me.top_role:
        return "I cannot moderate this member because their role is higher than or equal to my top role."
    return None


async def add_tempban_record(guild_id: int, user_id: int, username: str, unban_at_iso: str, reason: str, moderator_id: int) -> None:
    data = load_tempbans()
    data = [x for x in data if not (x.get("guild_id") == guild_id and x.get("user_id") == user_id)]
    data.append({
        "guild_id": guild_id,
        "user_id": user_id,
        "username": username,
        "unban_at": unban_at_iso,
        "reason": reason,
        "moderator_id": moderator_id
    })
    save_tempbans(data)


def remove_tempban_record(guild_id: int, user_id: int) -> None:
    data = load_tempbans()
    new_data = [x for x in data if not (x.get("guild_id") == guild_id and x.get("user_id") == user_id)]
    save_tempbans(new_data)


async def send_unban_notification(guild: discord.Guild, user: discord.User) -> str:
    """Send a stylish DM with the invite link. Returns status string."""
    invite = read_invite()
    if not invite:
        try:
            await user.send(f"✅ You have been unbanned from **{guild.name}**. Welcome back!")
            return "no_invite"
        except Exception as e:
            print(f"[DM] Failed (no invite) to {user}: {e}")
            return "failed"
    embed = discord.Embed(
        title="🔓 You have been unbanned!",
        description=f"Welcome back to **{guild.name}**!",
        color=discord.Color.green(),
        timestamp=utc_now()
    )
    embed.add_field(name="🔗 Rejoin Link", value=f"[Click here to join]({invite})", inline=False)
    embed.set_footer(text="We're happy to have you again!")
    try:
        await user.send(embed=embed)
        return "success"
    except Exception as e:
        print(f"[DM] Failed with invite to {user}: {e}")
        return "failed"


async def find_banned_user(guild: discord.Guild, query: str) -> Optional[discord.User]:
    q = query.strip()
    bans = [entry async for entry in guild.bans(limit=None)]
    if q.isdigit():
        target_id = int(q)
        for entry in bans:
            if entry.user.id == target_id:
                return entry.user
    q_lower = q.lower()
    for entry in bans:
        user = entry.user
        if str(user).lower() == q_lower:
            return user
    for entry in bans:
        user = entry.user
        if user.name.lower() == q_lower:
            return user
        global_name = getattr(user, "global_name", None)
        if isinstance(global_name, str) and global_name.lower() == q_lower:
            return user
        display_name = getattr(user, "display_name", None)
        if isinstance(display_name, str) and display_name.lower() == q_lower:
            return user
    for entry in bans:
        user = entry.user
        candidates = [str(user), user.name, getattr(user, "global_name", None), getattr(user, "display_name", None)]
        for item in candidates:
            if isinstance(item, str) and q_lower in item.lower():
                return user
    return None


# =========================
# Permission Check
# =========================
async def check_allowed_role(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if member_has_allowed_role(member):
        return True
    await interaction.response.send_message(
        f"❌ You do not have one of the allowed roles:\n{', '.join(sorted(ALLOWED_ROLE_NAMES))}",
        ephemeral=True
    )
    return False


# =========================
# Events
# =========================
@bot.event
async def on_ready() -> None:
    print(f"✅ Logged in as {bot.user}")
    if not tempban_checker.is_running():
        tempban_checker.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    print("✅ Flamy jr is ready.")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return
    guild = message.guild
    author = message.author
    if not isinstance(author, discord.Member):
        return
    if member_has_allowed_role(author):
        return
    guild_id_str = str(guild.id)
    blocked_data = load_blocked_words()
    words = blocked_data.get(guild_id_str, [])
    if not words:
        return
    content_lower = message.content.lower()
    blocked_found = None
    for word in words:
        if word.lower() in content_lower:
            blocked_found = word
            break
    if not blocked_found:
        return
    try:
        await message.delete()
    except Exception:
        pass
    warnings_data = load_warnings()
    if guild_id_str not in warnings_data:
        warnings_data[guild_id_str] = {}
    user_id_str = str(author.id)
    current = warnings_data[guild_id_str].get(user_id_str, 0)
    current += 1
    warnings_data[guild_id_str][user_id_str] = current
    save_warnings(warnings_data)
    await safe_dm(author, f"⚠️ Your message in **{guild.name}** contained a blocked word and was deleted.\nWarning {current}/3.")
    if current >= 3:
        try:
            await author.timeout(timedelta(minutes=10), reason="Auto‑timeout after 3 word filter warnings")
            warnings_data[guild_id_str][user_id_str] = 0
            save_warnings(warnings_data)
            await safe_dm(author, f"🚫 You have been timed out for 10 minutes in **{guild.name}** due to repeated use of blocked words.")
            embed = discord.Embed(title="🔥 Flamy jr | Auto Timeout", color=discord.Color.dark_gold(), timestamp=utc_now())
            embed.add_field(name="User", value=f"{author} (`{author.id}`)", inline=False)
            embed.add_field(name="Reason", value="3 word filter warnings", inline=False)
            await send_log(guild, embed)
        except Exception:
            pass


# =========================
# Tempban loop
# =========================
@tasks.loop(minutes=1)
async def tempban_checker() -> None:
    data = load_tempbans()
    if not data:
        return
    now = utc_now()
    remaining: list[dict[str, Any]] = []
    for entry in data:
        try:
            guild_id = int(entry["guild_id"])
            user_id = int(entry["user_id"])
            username = str(entry.get("username", f"User {user_id}"))
            unban_at_raw = str(entry["unban_at"])
            guild = bot.get_guild(guild_id)
            if guild is None:
                remaining.append(entry)
                continue
            unban_at = datetime.fromisoformat(unban_at_raw)
            if now >= unban_at:
                try:
                    user = await bot.fetch_user(user_id)
                    await guild.unban(user, reason="Temporary ban expired")
                    dm_status = await send_unban_notification(guild, user)
                    embed = discord.Embed(title="🔥 Flamy jr | Tempban Expired", color=discord.Color.green(), timestamp=utc_now())
                    embed.add_field(name="Target", value=f"{username} (`{user_id}`)", inline=False)
                    embed.add_field(name="Status", value="User unbanned automatically.", inline=False)
                    if dm_status == "success":
                        embed.add_field(name="DM", value="Invite sent", inline=False)
                    elif dm_status == "no_invite":
                        embed.add_field(name="DM", value="Sent without invite (no link set)", inline=False)
                    else:
                        embed.add_field(name="DM", value="Failed to send (user blocked or DMs off)", inline=False)
                    await send_log(guild, embed)
                except Exception:
                    remaining.append(entry)
            else:
                remaining.append(entry)
        except Exception:
            remaining.append(entry)
    save_tempbans(remaining)


@tempban_checker.before_loop
async def before_tempban_checker() -> None:
    await bot.wait_until_ready()


# =========================
# Slash Commands
# =========================
@bot.tree.command(name="help", description="Show all commands (private)")
async def slash_help(interaction: discord.Interaction):
    if not await check_allowed_role(interaction):
        return
    embed = discord.Embed(title="🔥 Flamy jr Command Center", description="All commands are slash‑based and private.", color=discord.Color.dark_red(), timestamp=utc_now())
    embed.add_field(name="/setlog #channel", value="Set log channel", inline=False)
    embed.add_field(name="/showlog", value="Show current log channel", inline=False)
    embed.add_field(name="/kick @user reason", value="Kick a member", inline=False)
    embed.add_field(name="/ban @user reason", value="Ban a member", inline=False)
    embed.add_field(name="/tempban @user duration reason", value="Temporary ban", inline=False)
    embed.add_field(name="/unban user", value="Unban by ID or name", inline=False)
    embed.add_field(name="/timeout @user duration reason", value="Timeout a member", inline=False)
    embed.add_field(name="/untimeout @user reason", value="Remove timeout", inline=False)
    embed.add_field(name="/clear [amount]", value="Purge messages", inline=False)
    embed.add_field(name="/addword word", value="Add blocked word", inline=False)
    embed.add_field(name="/removeword word", value="Remove blocked word", inline=False)
    embed.add_field(name="/listwords", value="List blocked words", inline=False)
    embed.add_field(name="/warnings @user", value="Check warnings", inline=False)
    embed.add_field(name="/clearwarnings @user", value="Reset warnings", inline=False)
    embed.add_field(name="/setinvite url", value="Set unban invite link", inline=False)
    embed.add_field(name="/getinvite", value="Show stored invite link (ephemeral)", inline=False)
    embed.add_field(name="🛡️ Allowed Roles", value=", ".join(sorted(ALLOWED_ROLE_NAMES)), inline=False)
    embed.set_footer(text="Flamy jr • m = minutes, h = hours, d = days")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="setlog", description="Set the log channel")
@app_commands.describe(channel="The text channel for logs")
async def slash_setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await check_allowed_role(interaction):
        return
    write_log_channel_id(channel.id)
    embed = discord.Embed(title="📋 Log Channel Updated", description=f"Set to {channel.mention}", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="showlog", description="Show current log channel")
async def slash_showlog(interaction: discord.Interaction):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    channel_id = read_log_channel_id()
    if channel_id <= 0:
        await interaction.response.send_message("❌ No log channel set.", ephemeral=True)
        return
    channel = get_text_channel_from_guild(guild, channel_id)
    if channel is not None:
        await interaction.response.send_message(f"📄 Current log channel: {channel.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"📄 Saved log channel ID: `{channel_id}` but not found.", ephemeral=True)


@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="The member to kick", reason="Reason for the kick")
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    error = hierarchy_check(interaction, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await safe_dm(member, f"👢 You were kicked from **{guild.name}**.\nReason: {reason}")
    try:
        await member.kick(reason=reason)
        embed = build_cool_embed("Kick", f"{member} (`{member.id}`)", str(interaction.user), reason, discord.Color.orange(), "👢")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Kick", interaction.user, f"{member} (`{member.id}`)", reason)
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to kick this user.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="The member to ban", reason="Reason for the ban")
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    error = hierarchy_check(interaction, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await safe_dm(member, f"🔨 You were banned from **{guild.name}**.\nReason: {reason}")
    try:
        await member.ban(reason=reason)
        embed = build_cool_embed("Ban", f"{member} (`{member.id}`)", str(interaction.user), reason, discord.Color.red(), "🔨")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Ban", interaction.user, f"{member} (`{member.id}`)", reason)
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to ban this user.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="tempban", description="Temporarily ban a member")
@app_commands.describe(member="The member", duration="e.g., 10m, 2h, 3d", reason="Reason")
async def slash_tempban(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    error = hierarchy_check(interaction, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    try:
        seconds = parse_duration_to_seconds(duration)
    except ValueError:
        await interaction.response.send_message("❌ Invalid duration. Use like: `10m`, `2h`, `3d`", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    unban_time = utc_now() + timedelta(seconds=seconds)
    await safe_dm(member, f"⏳ You were temporarily banned from **{guild.name}**.\nDuration: {duration}\nReason: {reason}")
    try:
        await member.ban(reason=f"{reason} | Tempban: {duration}")
        if isinstance(interaction.user, discord.Member):
            await add_tempban_record(guild.id, member.id, str(member), unban_time.isoformat(), reason, interaction.user.id)
        embed = build_cool_embed("Temp Ban", f"{member} (`{member.id}`)", str(interaction.user), f"{reason} | Duration: {duration}", discord.Color.dark_red(), "⏳")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Temp Ban", interaction.user, f"{member} (`{member.id}`)", f"{reason} | Duration: {duration}")
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to tempban this user.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="unban", description="Unban a user by ID or name")
@app_commands.describe(user="Banned user's ID or name")
async def slash_unban(interaction: discord.Interaction, user: str):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    target = await find_banned_user(guild, user)
    if target is None:
        await interaction.followup.send("❌ Banned user not found.", ephemeral=True)
        return
    try:
        await guild.unban(target, reason=f"Unbanned by {interaction.user}")
        remove_tempban_record(guild.id, target.id)
        dm_status = await send_unban_notification(guild, target)
        embed = build_cool_embed("Unban", f"{target} (`{target.id}`)", str(interaction.user), "User restored access", discord.Color.green(), "🔓")
        if dm_status == "success":
            embed.set_footer(text="Flamy jr • Invite DM sent")
        elif dm_status == "no_invite":
            embed.set_footer(text="Flamy jr • No invite set; DM sent without link")
        else:
            embed.set_footer(text="Flamy jr • Could not DM user (user blocked or DMs off)")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Unban", interaction.user, f"{target} (`{target.id}`)", "User restored access")
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to unban.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(member="The member", duration="e.g., 10m, 2h, 3d", reason="Reason")
async def slash_timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    error = hierarchy_check(interaction, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    try:
        seconds = parse_duration_to_seconds(duration)
    except ValueError:
        await interaction.response.send_message("❌ Invalid duration. Use like: `10m`, `2h`, `3d`", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await safe_dm(member, f"⏰ You were timed out in **{guild.name}**.\nDuration: {duration}\nReason: {reason}")
    try:
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        embed = build_cool_embed("Timeout", f"{member} (`{member.id}`)", str(interaction.user), f"{reason} | Duration: {duration}", discord.Color.gold(), "⏰")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Timeout", interaction.user, f"{member} (`{member.id}`)", f"{reason} | Duration: {duration}")
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to timeout this user.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="untimeout", description="Remove a member's timeout")
@app_commands.describe(member="The member", reason="Reason")
async def slash_untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    error = hierarchy_check(interaction, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await safe_dm(member, f"✅ Your timeout was removed in **{guild.name}**.\nReason: {reason}")
    try:
        await member.timeout(None, reason=reason)
        embed = build_cool_embed("Untimeout", f"{member} (`{member.id}`)", str(interaction.user), reason, discord.Color.teal(), "✅")
        await interaction.followup.send(embed=embed, ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            log_embed = build_log_embed("Untimeout", interaction.user, f"{member} (`{member.id}`)", reason)
            await send_log(guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack permission to remove timeout.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)


@bot.tree.command(name="clear", description="Delete messages in this channel")
@app_commands.describe(amount="Number of messages (max 100)")
async def slash_clear(interaction: discord.Interaction, amount: int = 10):
    if not await check_allowed_role(interaction):
        return
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("❌ Text channel only.", ephemeral=True)
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        embed = discord.Embed(title="🧹 Channel Cleared", description=f"Deleted **{len(deleted)}** messages.", color=discord.Color.purple(), timestamp=utc_now())
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I need 'Manage Messages' permission.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="addword", description="Add a blocked word")
@app_commands.describe(word="Word to block")
async def slash_addword(interaction: discord.Interaction, word: str):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    word = word.strip().lower()
    if not word:
        await interaction.response.send_message("❌ Provide a word.", ephemeral=True)
        return
    data = load_blocked_words()
    guild_id = str(guild.id)
    if guild_id not in data:
        data[guild_id] = []
    if word in data[guild_id]:
        await interaction.response.send_message(f"❌ `{word}` is already blocked.", ephemeral=True)
    else:
        data[guild_id].append(word)
        save_blocked_words(data)
        await interaction.response.send_message(f"✅ Added `{word}` to blocked words.", ephemeral=True)


@bot.tree.command(name="removeword", description="Remove a blocked word")
@app_commands.describe(word="Word to unblock")
async def slash_removeword(interaction: discord.Interaction, word: str):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    word = word.strip().lower()
    if not word:
        await interaction.response.send_message("❌ Provide a word.", ephemeral=True)
        return
    data = load_blocked_words()
    guild_id = str(guild.id)
    if guild_id not in data:
        data[guild_id] = []
    if word in data[guild_id]:
        data[guild_id].remove(word)
        save_blocked_words(data)
        await interaction.response.send_message(f"✅ Removed `{word}` from blocked words.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ `{word}` is not blocked.", ephemeral=True)


@bot.tree.command(name="listwords", description="List blocked words")
async def slash_listwords(interaction: discord.Interaction):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    data = load_blocked_words()
    guild_id = str(guild.id)
    words = data.get(guild_id, [])
    if not words:
        await interaction.response.send_message("📭 No blocked words.", ephemeral=True)
    else:
        word_list = "\n".join(f"• `{w}`" for w in sorted(words))
        embed = discord.Embed(title="🚫 Blocked Words", description=word_list, color=discord.Color.dark_purple(), timestamp=utc_now())
        embed.set_footer(text=f"Total: {len(words)} words")
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="warnings", description="Check a member's warnings")
@app_commands.describe(member="Member to check")
async def slash_warnings(interaction: discord.Interaction, member: discord.Member):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    data = load_warnings()
    guild_id = str(guild.id)
    user_id = str(member.id)
    count = data.get(guild_id, {}).get(user_id, 0)
    embed = discord.Embed(title="⚠️ Warning Status", description=f"{member.display_name} has **{count}** warning(s).", color=discord.Color.orange(), timestamp=utc_now())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="clearwarnings", description="Reset a member's warnings")
@app_commands.describe(member="Member to clear")
async def slash_clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not await check_allowed_role(interaction):
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    data = load_warnings()
    guild_id = str(guild.id)
    if guild_id in data:
        user_id = str(member.id)
        if user_id in data[guild_id]:
            data[guild_id][user_id] = 0
            save_warnings(data)
            await interaction.response.send_message(f"✅ Cleared warnings for {member.display_name}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ {member.display_name} had no warnings.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {member.display_name} had no warnings.", ephemeral=True)


@bot.tree.command(name="setinvite", description="Set the invite link for unbanned users")
@app_commands.describe(url="Discord invite URL")
async def slash_setinvite(interaction: discord.Interaction, url: str):
    if not await check_allowed_role(interaction):
        return
    if not (url.startswith("https://discord.gg/") or url.startswith("https://discord.com/invite/")):
        await interaction.response.send_message("❌ Invalid Discord invite URL.", ephemeral=True)
        return
    write_invite(url)
    await interaction.response.send_message(f"✅ Invite link set to:\n{url}", ephemeral=True)


@bot.tree.command(name="getinvite", description="Show the stored invite link (ephemeral)")
async def slash_getinvite(interaction: discord.Interaction):
    if not await check_allowed_role(interaction):
        return
    invite = read_invite()
    if invite:
        await interaction.response.send_message(f"🔗 Stored invite: {invite}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No invite link set. Use `/setinvite`.", ephemeral=True)


# =========================
# Error Handling
# =========================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if interaction.response.is_done():
        return
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        except Exception:
            pass


if not TOKEN:
    raise ValueError("DISCORD_TOKEN is missing in .env")

bot.run(TOKEN)