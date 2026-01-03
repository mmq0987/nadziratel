import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timedelta, timezone

# ================= НАСТРОЙКИ =================
TOKEN = ""
GUILD_ID = 1170342894717108226
PUNISH_ROLE_ID = 1406898764492570718
ALLOWED_USER_ID = 1111359772797706380
DATA_FILE = "punished.json"
# =============================================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True


class PunishBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.loop.create_task(voice_kick_scheduler())


bot = PunishBot()

# ---------- ЛОГ ----------
def log_action(text):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}")


# ---------- ДОСТУП ----------
def only_allowed_user(interaction: discord.Interaction) -> bool:
    if interaction.user.id != ALLOWED_USER_ID:
        raise app_commands.CheckFailure("❌ Соси хуй, у тебя нет доступа.")
    return True


# ---------- ФАЙЛ ----------
def load_punished():
    if not os.path.exists(DATA_FILE):
        return set()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_punished():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(list(punished_users), f, indent=4)


punished_users = load_punished()

# ---------- READY ----------
@bot.event
async def on_ready():
    log_action(f"Бот запущен как {bot.user}")

    guild = bot.get_guild(GUILD_ID)
    role = guild.get_role(PUNISH_ROLE_ID)

    for uid in punished_users:
        member = guild.get_member(uid)
        if member and role not in member.roles:
            await member.add_roles(role, reason="Перевыдача наказания")
            log_action(f"Перевыдача роли наказания: {member}")


# ---------- /punish ----------
@bot.tree.command(name="punish", description="Наказать уебка")
@app_commands.check(only_allowed_user)
async def punish(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    role = interaction.guild.get_role(PUNISH_ROLE_ID)
    bot_member = interaction.guild.get_member(bot.user.id)

    if role >= bot_member.top_role or member.top_role >= bot_member.top_role:
        await interaction.followup.send("❌ Не могу наказать", ephemeral=True)
        return

    punished_users.add(member.id)
    save_punished()

    await member.add_roles(role, reason="Наказан уебок")
    log_action(f"НАКАЗАН: {member} ({member.id})")

    await interaction.followup.send(f"🔒 {member.mention} наказан", ephemeral=True)


# ---------- /unpunish ----------
@bot.tree.command(name="unpunish", description="Помилование уебка")
@app_commands.check(only_allowed_user)
async def unpunish(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    role = interaction.guild.get_role(PUNISH_ROLE_ID)

    punished_users.discard(member.id)
    save_punished()
    voice_timers.pop(member.id, None)

    await member.remove_roles(role, reason="Помилование уебка")
    log_action(f"ПОМИЛОВАН: {member} ({member.id})")

    await interaction.followup.send(f"🔓 {member.mention} помилован", ephemeral=True)


# ---------- /punish_list ----------
@bot.tree.command(name="punish_list", description="Список хуеглотов")
@app_commands.check(only_allowed_user)
async def punish_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not punished_users:
        await interaction.followup.send("📭 Список хуеглотов пуст", ephemeral=True)
        return

    lines = []
    for uid in punished_users:
        m = interaction.guild.get_member(uid)
        lines.append(f"🔒 {m.mention}" if m else f"❓ `{uid}`")

    await interaction.followup.send(
        "📋 **Список хуеглотов:**\n" + "\n".join(lines),
        ephemeral=True
    )


# ---------- АНТИ-АДМИН ----------
@bot.event
async def on_member_update(before, after):
    if after.id not in punished_users:
        return

    punish_role = after.guild.get_role(PUNISH_ROLE_ID)

    if punish_role in before.roles and punish_role not in after.roles:
        await after.add_roles(punish_role)
        log_action(f"ВОЗВРАТ РОЛИ: {after}")

    for role in set(after.roles) - set(before.roles):
        if role.permissions.administrator:
            await after.remove_roles(role)
            until = datetime.now(timezone.utc) + timedelta(days=1)
            await after.timeout(until)
            log_action(f"АНТИ-АДМИН: {after}")


# ---------- VOICE ----------
voice_timers = {}


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id not in punished_users:
        return

    now = datetime.now(timezone.utc)
    timers = voice_timers.get(member.id)

    # ЗАШЁЛ В ВОЙС
    if before.channel is None and after.channel is not None:
        last_kick = timers.get("last_kick") if timers else None

        if not last_kick or (now - last_kick).total_seconds() >= 600:
            voice_timers[member.id] = {"join_time": now, "last_kick": last_kick}
            log_action(f"ВОЙС: {member} зашел (20 мин)")
        else:
            voice_timers[member.id]["join_time"] = now
            log_action(f"ВОЙС: {member} зашел (5 мин)")

    # САМ ВЫШЕЛ ИЗ ВОЙСА
    elif before.channel is not None and after.channel is None:
        log_action(f"ВОЙС: {member} сам вышел из войса")


# ---------- ПЛАНИРОВЩИК ----------
async def voice_kick_scheduler():
    await bot.wait_until_ready()

    while True:
        now = datetime.now(timezone.utc)
        guild = bot.get_guild(GUILD_ID)

        for uid in list(punished_users):
            member = guild.get_member(uid)
            timers = voice_timers.get(uid)

            if not member or not timers:
                continue

            if member.voice and member.voice.channel:
                limit = 1200
                if timers.get("last_kick") and (now - timers["last_kick"]).total_seconds() < 600:
                    limit = 300

                if (now - timers["join_time"]).total_seconds() >= limit:
                    voice_timers[uid]["last_kick"] = now
                    await member.move_to(None)
                    log_action(f"АВТОКИК: {member} ({limit//60} мин)")
            else:
                if timers.get("last_kick") and (now - timers["last_kick"]).total_seconds() >= 600:
                    voice_timers.pop(uid, None)
                    log_action(f"СБРОС ВОЙС-НАКАЗАНИЯ: {member}")

        await discord.utils.sleep_until(
            datetime.now(timezone.utc) + timedelta(seconds=10)
        )


# ---------- ERR ----------
@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(str(error), ephemeral=True)


# ---------- START ----------
bot.run(TOKEN)

