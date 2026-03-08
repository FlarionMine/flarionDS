import discord
from discord.ext import commands
import json
import os
import secrets
from typing import Optional

# ===================== КОНФИГ =====================
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

LOG_AUTH_FILE = "log_auth_tokens.json"

#==============================================

def load_counter():
	if not os.path.exists(COUNTER_FILE):
		with open(COUNTER_FILE, "w") as f:
			json.dump({"counter": 0}, f)

	with open(COUNTER_FILE, "r") as f:
		data = json.load(f)

	return data["counter"]

def save_counter(value):
	with open(COUNTER_FILE, "w") as f:
		json.dump({"counter": value}, f)

complaint_counter = load_counter()

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


log_auth_tokens = load_log_tokens()


def has_logs_access(member: discord.Member) -> bool:
    """Проверка, есть ли у пользователя дискорд‑роль доступа к логам."""
    return any(role.id == DISCORD_LOGS_ROLE_ID for role in member.roles)

# ===================== BOT =====================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== REPORT MODAL =====================

class ReportModal(discord.ui.Modal, title="Жалоба на игрока"):

	def __init__(self, bot):
		super().__init__()
		self.bot = bot

	nick = discord.ui.TextInput(label="Ваш ник", required=True)
	offender = discord.ui.TextInput(label="Ник нарушителя", required=True)

	proof = discord.ui.TextInput(
		label="Доказательства",
		style=discord.TextStyle.paragraph,
		required=True
	)

	async def on_submit(self, interaction: discord.Interaction):

		global complaint_counter

		complaint_counter += 1
		save_counter(complaint_counter)

		complaint_id = complaint_counter

		channel = self.bot.get_channel(REPORT_CHANNEL_ID)

		embed = discord.Embed(
			title=f"🚨 Новая жалоба #{complaint_id}",
			color=discord.Color.red()
		)

		embed.add_field(name="👤 Отправитель", value=self.nick.value, inline=False)
		embed.add_field(name="⚠ Нарушитель", value=self.offender.value, inline=False)
		embed.add_field(name="📎 Доказательства", value=self.proof.value, inline=False)

		embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

		view = ComplaintActionButtons(complaint_id, interaction.user.id, self.bot)

		await channel.send(embed=embed, view=view)

		await interaction.response.send_message(
			f"✅ Жалоба #{complaint_id} отправлена!",
			ephemeral=True
		)

# ===================== АВТОРИЗАЦИЯ В ЛОГИ СЕКРЕТ КЛЮЧ =====================

@bot.command(name="logs_login")
async def logs_login(ctx: commands.Context):
    """Выдать пользователю ключ авторизации в логи, если у него есть нужная роль на сервере."""
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

    # Генерируем одноразовый токен для входа в панель (подготовка к интеграции)
    token = secrets.token_urlsafe(24)
    log_auth_tokens[str(ctx.author.id)] = token
    save_log_tokens(log_auth_tokens)

    try:
        await ctx.author.send(
            "🔐 Ваш ключ авторизации в панель логов:\n"
            f"{token} \n"
			"Храните его в секрете. Позже панель логов будет уметь входить по этому ключу."
        )
        await ctx.reply("✅ Ключ авторизации отправлен вам в личные сообщения.", mention_author=False)
    except discord.Forbidden:
        await ctx.reply("⚠ Не удалось отправить ЛС. Разрешите личные сообщения от сервера.", mention_author=False)

# ===================== ВЕРДИКТ =====================

class VerdictModal(discord.ui.Modal, title="Вердикт по жалобе"):

	def __init__(self, complaint_id, sender_id, bot, message):
		super().__init__()
		self.complaint_id = complaint_id
		self.sender_id = sender_id
		self.bot = bot
		self.message = message

	verdict = discord.ui.TextInput(
		label="Введите вердикт",
		style=discord.TextStyle.paragraph,
		required=True
	)

	async def on_submit(self, interaction: discord.Interaction):

		embed = self.message.embeds[0]
		sender_user = await self.bot.fetch_user(self.sender_id)

		embed.color = discord.Color.green()

		embed.add_field(
			name="📋 Вердикт администрации",
			value=f"{self.verdict.value}\n\nАдминистратор: {interaction.user.mention}",
			inline=False
		)

		view = ComplaintActionButtons(self.complaint_id, self.sender_id, self.bot)
		view.disable_buttons()

		await self.message.edit(embed=embed, view=view)

		await interaction.response.send_message(
			"✅ Жалоба закрыта.",
			ephemeral=True
		)

		try:
			await sender_user.send(
				f"📢 Ваша жалоба #{self.complaint_id} рассмотрена.\n\n"
				f"Вердикт:\n{self.verdict.value}"
			)
		except:
			pass

# ===================== ОТКАЗ =====================

class RejectModal(discord.ui.Modal, title="Причина отказа"):

	def __init__(self, complaint_id, sender_id, bot, message):
		super().__init__()
		self.complaint_id = complaint_id
		self.sender_id = sender_id
		self.bot = bot
		self.message = message

	reason = discord.ui.TextInput(
		label="Причина отказа",
		style=discord.TextStyle.paragraph,
		required=True
	)

	async def on_submit(self, interaction: discord.Interaction):

		embed = self.message.embeds[0]
		sender_user = await self.bot.fetch_user(self.sender_id)

		embed.color = discord.Color.dark_red()

		embed.add_field(
			name="❌ Жалоба отклонена",
			value=f"{self.reason.value}\n\nАдминистратор: {interaction.user.mention}",
			inline=False
		)

		view = ComplaintActionButtons(self.complaint_id, self.sender_id, self.bot)
		view.disable_buttons()

		await self.message.edit(embed=embed, view=view)

		await interaction.response.send_message(
			"❌ Жалоба отклонена.",
			ephemeral=True
		)

		try:
			await sender_user.send(
				f"📢 Ваша жалоба #{self.complaint_id} отклонена.\n\n"
				f"Причина:\n{self.reason.value}"
			)
		except:
			pass

# ===================== REPORT BUTTON =====================

class ReportButton(discord.ui.View):

	def __init__(self, bot):
		super().__init__(timeout=None)
		self.bot = bot

	@discord.ui.button(label="Подать жалобу", style=discord.ButtonStyle.red, custom_id="report_button")
	async def report(self, interaction: discord.Interaction, button: discord.ui.Button):

		await interaction.response.send_modal(ReportModal(self.bot))

# ===================== ACTION BUTTONS =====================

class ComplaintActionButtons(discord.ui.View):

	def __init__(self, complaint_id, sender_id, bot):
		super().__init__(timeout=None)
		self.complaint_id = complaint_id
		self.sender_id = sender_id
		self.bot = bot

	async def interaction_check(self, interaction: discord.Interaction):

		user_roles = [role.id for role in interaction.user.roles]

		if any(role_id in REPORT_MODERATOR_ROLES for role_id in user_roles):
			return True

		await interaction.response.send_message(
			"❌ У вас нет роли для обработки жалоб.",
			ephemeral=True
		)

		return False

	def disable_buttons(self):
		for item in self.children:
			item.disabled = True

	@discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
	async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):

		modal = VerdictModal(
			self.complaint_id,
			self.sender_id,
			self.bot,
			interaction.message
		)

		await interaction.response.send_modal(modal)

	@discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
	async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

		modal = RejectModal(
			self.complaint_id,
			self.sender_id,
			self.bot,
			interaction.message
		)

		await interaction.response.send_modal(modal)

# ===================== LOGS =====================

class InfoRequestModal(discord.ui.Modal, title="Запрос логов"):

	def __init__(self, bot):
		super().__init__()
		self.bot = bot

	requester_nick = discord.ui.TextInput(label="Ваш ник", required=True)
	target_nick = discord.ui.TextInput(label="Ник игрока", required=True)

	info_type = discord.ui.TextInput(
		label="Тема запроса",
		required=True
	)

	async def on_submit(self, interaction: discord.Interaction):

		channel = self.bot.get_channel(INFO_LOG_CHANNEL_ID)

		embed = discord.Embed(
			title="📄 Новый запрос логов",
			color=discord.Color.blue()
		)

		embed.add_field(name="👤 Запросил", value=self.requester_nick.value, inline=False)
		embed.add_field(name="🎯 Игрок", value=self.target_nick.value, inline=False)
		embed.add_field(name="ℹ Тип логов", value=self.info_type.value, inline=False)

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
		custom_id="info_request_button"
	)
	async def request_info(self, interaction: discord.Interaction, button: discord.ui.Button):

		await interaction.response.send_modal(InfoRequestModal(self.bot))

class InfoResponseButton(discord.ui.View):

	def __init__(self, requester_id, target_nick, bot):
		super().__init__(timeout=None)
		self.requester_id = requester_id
		self.target_nick = target_nick
		self.bot = bot

	async def interaction_check(self, interaction: discord.Interaction):

		user_roles = [role.id for role in interaction.user.roles]

		if any(role_id in LOG_SENDER_ROLES for role_id in user_roles):
			return True

		await interaction.response.send_message(
			"❌ У вас нет роли для отправки логов.",
			ephemeral=True
		)

		return False

	@discord.ui.button(
		label="Отправить логи",
		style=discord.ButtonStyle.green,
		custom_id="send_info_button"
	)
	async def send_info(self, interaction: discord.Interaction, button: discord.ui.Button):

		original_message = interaction.message

		class InfoInputModal(discord.ui.Modal, title=f"Логи по {self.target_nick}"):

			info_text = discord.ui.TextInput(
				label="Логи",
				style=discord.TextStyle.paragraph,
				required=True
			)

			async def on_submit(modal_self, interaction_modal: discord.Interaction):

				dm_status = "✅ ЛС доставлены."
				try:
					# Аcknowledgement to avoid "interaction failed" even при долгих операциях
					if not interaction_modal.response.is_done():
						await interaction_modal.response.defer(ephemeral=True, thinking=True)

					requester_user = await self.bot.fetch_user(self.requester_id)
					sender_user = interaction_modal.user

					# Пытаемся отправить логи в ЛС запросившему
					try:
						await requester_user.send(
							f"📢 Логи по {self.target_nick}:\n{modal_self.info_text.value}"
						)
					except discord.Forbidden:
						dm_status = "⚠ Не удалось отправить ЛС (запрещены личные сообщения)."
					except discord.HTTPException as e:
						dm_status = f"⚠ Не удалось отправить ЛС (HTTP {e.status})."

					# Формируем итоговый embed и закрываем кнопку
					embed = discord.Embed(
						title="ℹ Логи отправлены",
						color=discord.Color.green()
					)
					embed.add_field(name="👤 Кто запросил", value=f"{requester_user} (ID: {requester_user.id})", inline=False)
					embed.add_field(name="🧑‍💼 Кто отправил", value=f"{sender_user} (ID: {sender_user.id})", inline=False)
					embed.add_field(name="📢 Кому отправлена", value=f"{requester_user} (ID: {requester_user.id})", inline=False)
					embed.add_field(name="🎯 Игрок", value=f"{self.target_nick}", inline=False)
					embed.add_field(name="💬 Логи", value=f"{modal_self.info_text.value}", inline=False)
					embed.add_field(name="✉ Статус ЛС", value=dm_status, inline=False)

					self.disable_buttons()
					await original_message.edit(embed=embed, view=self)

					# Дублируем лог в служебный канал, если он есть
					log_channel = self.bot.get_channel(INFO_LOG_CHANNEL_ID)
					if log_channel:
						await log_channel.send(embed=embed)

					await interaction_modal.followup.send(
						"✅ Информация отправлена, кнопка закрыта.",
						ephemeral=True
					)

				except Exception as e:
					# Логируем в консоль и отправляем текст ошибки исполнителю
					print(f"[log-send-error] {e}")
					msg = f"⚠ Произошла ошибка при отправке логов: {e}"
					if not interaction_modal.response.is_done():
						await interaction_modal.response.defer(ephemeral=True, thinking=False)
					await interaction_modal.followup.send(msg, ephemeral=True)

		await interaction.response.send_modal(InfoInputModal())

# ===================== КОМАНДЫ =====================

@bot.command()
@commands.has_permissions(administrator=True)
async def reportticket(ctx):

	await ctx.send(
		"Чтобы подать жалобу, нажми кнопку ниже.",
		view=ReportButton(bot)
	)

@bot.command()
@commands.has_permissions(administrator=True)
async def adminlogs_command(ctx):

	await ctx.send(
		"Нажмите кнопку ниже для запроса логов.",
		view=InfoRequestButton(bot)
	)

# ===================== READY =====================

@bot.event
async def on_ready():

	bot.add_view(ReportButton(bot))
	bot.add_view(InfoRequestButton(bot))

	print(f"Бот {bot.user} запущен.")

if not DISCORD_TOKEN:
	print("ERROR: DISCORD_TOKEN is not set. Please set it in environment or .env file.")
	raise SystemExit(1)

bot.run(DISCORD_TOKEN)
