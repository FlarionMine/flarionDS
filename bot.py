import discord
from discord.ext import commands, tasks
import json
import os
import secrets
from typing import Optional
from datetime import datetime

# ===================== CONFIG =====================

from config import (
    DISCORD_TOKEN,
    GUILD_ID,
    DISCORD_LOGS_ROLE_ID,
    REPORT_CHANNEL_ID,
    INFO_LOG_CHANNEL_ID,
    COUNTER_FILE,
    REPORT_MODERATOR_ROLES,
    LOG_SENDER_ROLES,
)

# Если этих переменных нет в config.py — задай их здесь или через Railway Environment Variables
INACTIVE_LOG_CHANNEL_ID = int(os.environ.get("INACTIVE_LOG_CHANNEL_ID", 1481975996436713512))
INACTIVE_ADMIN_ROLE     = int(os.environ.get("INACTIVE_ADMIN_ROLE",     123456789012345678))

INACTIVE_REQUEST_CHANNEL_ID = 1481975908318580766
INACTIVE_RESULT_CHANNEL_ID  = 1481975996436713512

LOG_AUTH_FILE = "log_auth_tokens.json"
INACTIVE_FILE = "inactive_users.json"

# ===================== FILE FUNCTIONS =====================

def load_counter():
    if not os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "w") as f:
            json.dump({"counter": 0}, f)
    with open(COUNTER_FILE, "r") as f:
        return json.load(f)["counter"]

def save_counter(value):
    with open(COUNTER_FILE, "w") as f:
        json.dump({"counter": value}, f)

def load_inactive():
    if not os.path.exists(INACTIVE_FILE):
        with open(INACTIVE_FILE, "w") as f:
            json.dump({}, f)
    with open(INACTIVE_FILE, "r") as f:
        return json.load(f)

def save_inactive(data):
    with open(INACTIVE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_log_tokens() -> dict:
    if not os.path.exists(LOG_AUTH_FILE):
        with open(LOG_AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}
    with open(LOG_AUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_log_tokens(data: dict) -> None:
    with open(LOG_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def has_logs_access(member: discord.Member) -> bool:
    return any(role.id == DISCORD_LOGS_ROLE_ID for role in member.roles)

# ===================== STATE =====================

complaint_counter     = load_counter()
inactive_users        = load_inactive()
log_auth_tokens       = load_log_tokens()
processed_log_messages = set()

# ===================== BOT =====================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== REPORT SYSTEM =====================

class ReportModal(discord.ui.Modal, title="Жалоба на игрока"):

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    nick     = discord.ui.TextInput(label="Ваш ник", required=True)
    offender = discord.ui.TextInput(label="Ник нарушителя", required=True)
    proof    = discord.ui.TextInput(
        label="Доказательства",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        global complaint_counter
        complaint_counter += 1
        save_counter(complaint_counter)
        complaint_id = complaint_counter

        embed = discord.Embed(
            title=f"🚨 Новая жалоба #{complaint_id}",
            color=discord.Color.red(),
        )
        embed.add_field(name="👤 Отправитель",  value=self.nick.value,     inline=False)
        embed.add_field(name="⚠ Нарушитель",    value=self.offender.value, inline=False)
        embed.add_field(name="📎 Доказательства", value=self.proof.value,  inline=False)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

        view    = ComplaintActionButtons(complaint_id, interaction.user.id, self.bot)
        channel = self.bot.get_channel(REPORT_CHANNEL_ID)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Жалоба #{complaint_id} отправлена!", ephemeral=True
        )


class VerdictModal(discord.ui.Modal, title="Вердикт по жалобе"):

    def __init__(self, complaint_id, sender_id, bot, message):
        super().__init__()
        self.complaint_id = complaint_id
        self.sender_id    = sender_id
        self.bot          = bot
        self.message      = message

    verdict = discord.ui.TextInput(
        label="Введите вердикт",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed       = self.message.embeds[0]
        sender_user = await self.bot.fetch_user(self.sender_id)

        embed.color = discord.Color.green()
        embed.add_field(
            name="📋 Вердикт администрации",
            value=f"{self.verdict.value}\n\nАдминистратор: {interaction.user.mention}",
            inline=False,
        )

        view = ComplaintActionButtons(self.complaint_id, self.sender_id, self.bot)
        view.disable_buttons()
        await self.message.edit(embed=embed, view=view)

        await interaction.response.send_message("✅ Жалоба закрыта.", ephemeral=True)

        try:
            await sender_user.send(
                f"📢 Ваша жалоба #{self.complaint_id} рассмотрена.\n\nВердикт:\n{self.verdict.value}"
            )
        except Exception:
            pass


class RejectModal(discord.ui.Modal, title="Причина отказа"):

    def __init__(self, complaint_id, sender_id, bot, message):
        super().__init__()
        self.complaint_id = complaint_id
        self.sender_id    = sender_id
        self.bot          = bot
        self.message      = message

    reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed       = self.message.embeds[0]
        sender_user = await self.bot.fetch_user(self.sender_id)

        embed.color = discord.Color.dark_red()
        embed.add_field(
            name="❌ Жалоба отклонена",
            value=f"{self.reason.value}\n\nАдминистратор: {interaction.user.mention}",
            inline=False,
        )

        view = ComplaintActionButtons(self.complaint_id, self.sender_id, self.bot)
        view.disable_buttons()
        await self.message.edit(embed=embed, view=view)

        await interaction.response.send_message("❌ Жалоба отклонена.", ephemeral=True)

        try:
            await sender_user.send(
                f"📢 Ваша жалоба #{self.complaint_id} отклонена.\n\nПричина:\n{self.reason.value}"
            )
        except Exception:
            pass


class ComplaintActionButtons(discord.ui.View):

    def __init__(self, complaint_id, sender_id, bot):
        super().__init__(timeout=None)
        self.complaint_id = complaint_id
        self.sender_id    = sender_id
        self.bot          = bot

    def disable_buttons(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction):
        user_roles = [r.id for r in interaction.user.roles]
        if any(r in REPORT_MODERATOR_ROLES for r in user_roles):
            return True
        await interaction.response.send_message(
            "❌ У вас нет роли для обработки жалоб.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            VerdictModal(self.complaint_id, self.sender_id, self.bot, interaction.message)
        )

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            RejectModal(self.complaint_id, self.sender_id, self.bot, interaction.message)
        )


class ReportButton(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Подать жалобу",
        style=discord.ButtonStyle.red,
        custom_id="report_button",
    )
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(self.bot))

# ===================== INACTIVE SYSTEM =====================

class InactiveModal(discord.ui.Modal, title="Заявление на неактив"):

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    nick       = discord.ui.TextInput(label="Ваш ник", required=True)
    start_date = discord.ui.TextInput(
        label="Дата начала неактива",
        placeholder="Например: 12.03.2026",
        required=True,
    )
    end_date   = discord.ui.TextInput(
        label="Дата окончания неактива",
        placeholder="Например: 20.03.2026",
        required=True,
    )
    reason     = discord.ui.TextInput(
        label="Причина неактива",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) in inactive_users:
            await interaction.response.send_message(
                "У вас уже есть активный неактив.", ephemeral=True
            )
            return

        embed = discord.Embed(title="📅 Новое заявление на неактив", color=discord.Color.orange())
        embed.add_field(name="👤 Ник",       value=self.nick.value,       inline=False)
        embed.add_field(name="📅 Начало",    value=self.start_date.value, inline=False)
        embed.add_field(name="📅 Конец",     value=self.end_date.value,   inline=False)
        embed.add_field(name="📄 Причина",   value=self.reason.value,     inline=False)
        embed.set_footer(text=f"Discord ID: {interaction.user.id}")

        view    = InactiveActionButtons(interaction.user.id, self.end_date.value, self.bot)
        channel = self.bot.get_channel(INACTIVE_RESULT_CHANNEL_ID)
        await channel.send(
            f"<@&{INACTIVE_ADMIN_ROLE}> новая заявка на неактив",
            embed=embed,
            view=view,
        )

        await interaction.response.send_message("✅ Заявка отправлена.", ephemeral=True)


class InactiveButton(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Подать неактив",
        style=discord.ButtonStyle.blurple,
        custom_id="inactive_button",
    )
    async def inactive(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InactiveModal(self.bot))


class InactiveActionButtons(discord.ui.View):

    def __init__(self, requester_id, end_date, bot):
        super().__init__(timeout=None)
        self.requester_id = requester_id
        self.end_date     = end_date
        self.bot          = bot

    def disable_buttons(self):
        for item in self.children:
            item.disabled = True

    def format_nick(self, nick: str) -> str:
        if "| неактив" in nick:
            nick = nick.split("| неактив")[0].strip()
        return f"{nick} | неактив {self.end_date}"

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.requester_id)

        if member:
            old_nick = member.display_name
            new_nick = self.format_nick(old_nick)

            try:
                await member.edit(nick=new_nick)
            except Exception:
                old_nick = member.display_name  # fallback

            inactive_users[str(member.id)] = {
                "end_date": self.end_date,
                "old_nick": old_nick,
            }
            save_inactive(inactive_users)

            try:
                await member.send(
                    f"✅ Ваш неактив одобрен администратором {interaction.user.name}"
                )
            except Exception:
                pass

        embed = interaction.message.embeds[0]
        embed.add_field(
            name="✅ Решение",
            value=f"Одобрено {interaction.user.mention}",
            inline=False,
        )
        self.disable_buttons()
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("Неактив принят.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = await self.bot.fetch_user(self.requester_id)

        try:
            await user.send(
                f"❌ Ваш неактив отклонён администратором {interaction.user.name}"
            )
        except Exception:
            pass

        embed = interaction.message.embeds[0]
        embed.add_field(
            name="❌ Решение",
            value=f"Отклонено {interaction.user.mention}",
            inline=False,
        )
        self.disable_buttons()
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("Неактив отклонён.", ephemeral=True)

# ===================== AUTO INACTIVE CHECKER =====================

@tasks.loop(minutes=30)
async def inactive_checker():
    guild = bot.get_guild(GUILD_ID)
    now   = datetime.now()
    remove = []

    for uid, data in inactive_users.items():
        try:
            end = datetime.strptime(data["end_date"], "%d.%m.%Y")
        except ValueError:
            continue

        if now >= end:
            member = guild.get_member(int(uid))
            if member:
                try:
                    await member.edit(nick=data["old_nick"])
                except Exception:
                    pass
            remove.append(uid)

    for r in remove:
        del inactive_users[r]

    if remove:
        save_inactive(inactive_users)

# ===================== LOGS SYSTEM =====================

class InfoRequestModal(discord.ui.Modal, title="Запрос логов"):

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    requester_nick = discord.ui.TextInput(label="Ваш ник",     required=True)
    target_nick    = discord.ui.TextInput(label="Ник игрока",  required=True)
    info_type      = discord.ui.TextInput(label="Тема запроса", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        channel = self.bot.get_channel(INFO_LOG_CHANNEL_ID)

        embed = discord.Embed(title="📄 Новый запрос логов", color=discord.Color.blue())
        embed.add_field(name="👤 Запросил",             value=self.requester_nick.value, inline=False)
        embed.add_field(name="🎯 Игрок",                value=self.target_nick.value,    inline=False)
        embed.add_field(name="ℹ Необходимая информация", value=self.info_type.value,     inline=False)

        view = InfoResponseButton(interaction.user.id, self.target_nick.value, self.bot)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Запрос отправлен!", ephemeral=True)


class InfoRequestButton(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Запрос логов",
        style=discord.ButtonStyle.blurple,
        custom_id="info_request_button",
    )
    async def request_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InfoRequestModal(self.bot))


class InfoResponseButton(discord.ui.View):

    def __init__(self, requester_id, target_nick, bot):
        super().__init__(timeout=None)
        self.requester_id = requester_id
        self.target_nick  = target_nick
        self.bot          = bot

    def disable_buttons(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.message.id in processed_log_messages:
            await interaction.response.send_message(
                "ℹ Эта заявка уже обработана.", ephemeral=True
            )
            return False

        user_roles = [r.id for r in interaction.user.roles]
        if any(r in LOG_SENDER_ROLES for r in user_roles):
            return True

        await interaction.response.send_message(
            "❌ У вас нет роли для отправки логов.", ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Отправить логи",
        style=discord.ButtonStyle.green,
        custom_id="send_info_button",
    )
    async def send_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        original_message = interaction.message
        target_nick      = self.target_nick
        requester_id     = self.requester_id
        _bot             = self.bot

        class InfoInputModal(discord.ui.Modal, title=f"Логи по {target_nick}"):
            info_text = discord.ui.TextInput(
                label="Логи",
                style=discord.TextStyle.paragraph,
                required=True,
            )

            async def on_submit(modal_self, interaction_modal: discord.Interaction):
                dm_status = "✅ ЛС доставлены."
                try:
                    if not interaction_modal.response.is_done():
                        await interaction_modal.response.defer(ephemeral=True, thinking=True)

                    requester_user = await _bot.fetch_user(requester_id)
                    sender_user    = interaction_modal.user

                    try:
                        await requester_user.send(
                            f"📢 Логи по {target_nick}:\n{modal_self.info_text.value}"
                        )
                    except discord.Forbidden:
                        dm_status = "⚠ Не удалось отправить ЛС (запрещены личные сообщения)."
                    except discord.HTTPException as e:
                        dm_status = f"⚠ Не удалось отправить ЛС (HTTP {e.status})."

                    embed = discord.Embed(title="[ОБРАБОТАНО] Логи отправлены", color=discord.Color.green())
                    embed.add_field(name="👤 Кто запросил", value=f"{requester_user} (ID: {requester_user.id})", inline=False)
                    embed.add_field(name="🧑‍💼 Кто отправил", value=f"{sender_user} (ID: {sender_user.id})",         inline=False)
                    embed.add_field(name="🎯 Игрок",         value=target_nick,                                        inline=False)
                    embed.add_field(name="💬 Логи",           value=modal_self.info_text.value,                         inline=False)
                    embed.add_field(name="✉ Статус ЛС",      value=dm_status,                                          inline=False)

                    processed_log_messages.add(original_message.id)

                    log_channel = _bot.get_channel(INFO_LOG_CHANNEL_ID)
                    target_channel = log_channel if log_channel else interaction_modal.channel
                    await target_channel.send(embed=embed)

                    await interaction_modal.followup.send(
                        "✅ Информация отправлена.", ephemeral=True
                    )

                except Exception as e:
                    print(f"[log-send-error] {e}")
                    if not interaction_modal.response.is_done():
                        await interaction_modal.response.defer(ephemeral=True)
                    await interaction_modal.followup.send(
                        f"⚠ Ошибка при отправке логов: {e}", ephemeral=True
                    )

        await interaction.response.send_modal(InfoInputModal())

# ===================== ADMIN COMMANDS =====================

@bot.command()
@commands.has_permissions(administrator=True)
async def reportticket(ctx):
    await ctx.send("Чтобы подать жалобу, нажми кнопку ниже.", view=ReportButton(bot))


@bot.command()
@commands.has_permissions(administrator=True)
async def inactiveticket(ctx):
    await ctx.send("Нажмите кнопку ниже для подачи заявления на неактив.", view=InactiveButton(bot))


@bot.command()
@commands.has_permissions(administrator=True)
async def adminlogs_command(ctx):
    await ctx.send("Нажмите кнопку ниже для запроса логов.", view=InfoRequestButton(bot))


@bot.command()
@commands.has_permissions(administrator=True)
async def inactive_list(ctx):
    if not inactive_users:
        await ctx.send("Активных неактивов нет.")
        return

    embed = discord.Embed(title="Активные неактивы", color=discord.Color.blue())
    for uid, data in inactive_users.items():
        embed.add_field(name=f"User ID {uid}", value=f"до {data['end_date']}", inline=False)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def inactive_remove(ctx, member: discord.Member):
    if str(member.id) not in inactive_users:
        await ctx.send("У пользователя нет неактива.")
        return

    old = inactive_users[str(member.id)]["old_nick"]
    try:
        await member.edit(nick=old)
    except Exception:
        pass

    del inactive_users[str(member.id)]
    save_inactive(inactive_users)
    await ctx.send("Неактив снят.")


@bot.command(name="logs_login")
async def logs_login(ctx: commands.Context):
    """Выдать пользователю ключ авторизации в логи, если у него есть нужная роль."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        await ctx.reply("⚠ Не удалось найти основной сервер по ID.", mention_author=False)
        return

    member: Optional[discord.Member] = guild.get_member(ctx.author.id)
    if member is None:
        await ctx.reply("⚠ Вы не найдены на основном сервере.", mention_author=False)
        return

    if not has_logs_access(member):
        await ctx.reply("❌ У вас нет роли для доступа к логам.", mention_author=False)
        return

    token = secrets.token_urlsafe(24)
    log_auth_tokens[str(ctx.author.id)] = token
    save_log_tokens(log_auth_tokens)

    try:
        await ctx.author.send(
            "🔐 Ваш ключ авторизации в панель логов:\n"
            f"{token}\n"
            "Храните его в секрете."
        )
        await ctx.reply("✅ Ключ авторизации отправлен вам в личные сообщения.", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(
            "⚠ Не удалось отправить ЛС. Разрешите личные сообщения от сервера.",
            mention_author=False,
        )

# ===================== READY =====================

@bot.event
async def on_ready():
    bot.add_view(ReportButton(bot))
    bot.add_view(InactiveButton(bot))
    bot.add_view(InfoRequestButton(bot))

    inactive_checker.start()

    print(f"Бот {bot.user} запущен.")


if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN is not set.")
    raise SystemExit(1)

bot.run(DISCORD_TOKEN)
