import os
from dotenv import load_dotenv

# Подгружаем переменные из .env (локально) и из окружения (Railway)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ID основного сервера
GUILD_ID = 1439309101367562424

# Роль на сервере, дающая доступ к логам
DISCORD_LOGS_ROLE_ID = 1439339520712638586

# Каналы, как было
REPORT_CHANNEL_ID = 1479899834252132362
INFO_LOG_CHANNEL_ID = 1445530089554055348

# Локальный файл счётчика жалоб
COUNTER_FILE = "complaints.json"

REPORT_MODERATOR_ROLES = [
    1439330970129006695,
    1439339520712638586,
    1439334771913261397,
    1445186557182214184,
    1445525140506153114,
]

LOG_SENDER_ROLES = [
    1439339520712638586,
    1439334771913261397,
    1445186557182214184,
    1445525140506153114,
]

# Заготовка под будущий бэкенд логов (пока можно оставить None)
LOGS_BACKEND_URL = os.getenv("LOGS_BACKEND_URL")  # например: https://logs.yourdomain.com
LOGS_BACKEND_API_KEY = os.getenv("LOGS_BACKEND_API_KEY")