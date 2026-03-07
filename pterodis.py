import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any

import disnake
from disnake.ext import commands
from pydactyl import PterodactylClient


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pterodis")


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
    PTERODACTYL_URL = os.getenv("PTERODACTYL_URL", "")
    PTERODACTYL_API_KEY = os.getenv("PTERODACTYL_API_KEY", "")
    USER_ACCESS_FILE = Path(os.getenv("USER_ACCESS_FILE", "user_access.json"))
    USER_ACCESS_LEGACY_FILE = Path("user_access.pkl")
    SUPER_USERS = {
        value.strip()
        for value in os.getenv("SUPER_USERS", "").split(",")
        if value.strip()
    }
    SERVER_CACHE_TTL_SEC = int(os.getenv("SERVER_CACHE_TTL_SEC", "60"))


if not Config.PTERODACTYL_URL or not Config.PTERODACTYL_API_KEY:
    logger.warning(
        "PTERODACTYL_URL/PTERODACTYL_API_KEY не заданы. Укажите переменные окружения перед запуском."
    )
if not Config.DISCORD_TOKEN:
    logger.warning("DISCORD_TOKEN не задан. Бот не сможет подключиться к Discord.")


intents = disnake.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)
api = PterodactylClient(Config.PTERODACTYL_URL, Config.PTERODACTYL_API_KEY)


def load_user_access() -> dict[str, list[str]]:
    if Config.USER_ACCESS_FILE.exists():
        with Config.USER_ACCESS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                str(server): [str(user_id) for user_id in users]
                for server, users in data.items()
            }

    if Config.USER_ACCESS_LEGACY_FILE.exists():
        logger.info("Найдена legacy-база user_access.pkl, выполняю миграцию в JSON.")
        with Config.USER_ACCESS_LEGACY_FILE.open("rb") as f:
            data = pickle.load(f)
        normalized = {
            str(server): [str(user_id) for user_id in users]
            for server, users in data.items()
        }
        save_user_access(normalized)
        return normalized

    return {}


def save_user_access(access_map: dict[str, list[str]]) -> None:
    temp_file = Config.USER_ACCESS_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(access_map, f, ensure_ascii=False, indent=2)
    temp_file.replace(Config.USER_ACCESS_FILE)


user_access = load_user_access()
_server_cache: list[dict[str, Any]] = []
_server_cache_loaded_at = 0.0


def refresh_servers(force: bool = False) -> list[dict[str, Any]]:
    global _server_cache_loaded_at, _server_cache
    now = time.time()
    if force or now - _server_cache_loaded_at >= Config.SERVER_CACHE_TTL_SEC:
        _server_cache = api.client.servers.list_servers()
        _server_cache_loaded_at = now
    return _server_cache


def get_server_id(name: str) -> str | None:
    for server in refresh_servers():
        attributes = server.get("attributes", {})
        if attributes.get("name") == name:
            return attributes.get("identifier")
    return None


def get_available_servers_for_user(user_id: str) -> list[str]:
    if user_id in Config.SUPER_USERS:
        return [
            server.get("attributes", {}).get("name", "")
            for server in refresh_servers()
            if server.get("attributes", {}).get("name")
        ]
    return [server for server, users in user_access.items() if user_id in users]


def check_user_access(user_id: str, server_name: str) -> bool:
    return user_id in Config.SUPER_USERS or user_id in user_access.get(server_name, [])


def format_bytes(value: int | float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(value)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.2f} {units[idx]}"


def format_uptime(ms: int | float) -> str:
    total_seconds = int(max(ms, 0) / 1000)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days} дн., {hours} ч., {minutes} мин., {seconds} сек."


async def autocomplete_servers(inter: disnake.ApplicationCommandInteraction, string: str) -> list[str]:
    user_id = str(inter.author.id)
    servers = get_available_servers_for_user(user_id)
    return [server for server in servers if string.lower() in server.lower()][:25]


class ServerControlButtons(disnake.ui.View):
    def __init__(self, user_id: str, server_name: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.server_name = server_name
        self.message: disnake.Message | None = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "Эта панель управления создана не для вас.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @disnake.ui.button(label="Запустить", style=disnake.ButtonStyle.green)
    async def start_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, "start")

    @disnake.ui.button(label="Перезапустить", style=disnake.ButtonStyle.blurple)
    async def restart_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, "restart")

    @disnake.ui.button(label="Остановить", style=disnake.ButtonStyle.red)
    async def stop_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, "stop")


async def server_power_action(
    interaction: disnake.ApplicationCommandInteraction | disnake.MessageInteraction,
    server_name: str,
    action: str,
) -> None:
    server_id = get_server_id(server_name)
    if not server_id:
        await interaction.response.send_message(
            f"Сервер {server_name} не найден.", ephemeral=True
        )
        return

    try:
        api.client.servers.send_power_action(server_id, action)
        action_label = {"start": "запускается", "stop": "останавливается", "restart": "перезапускается"}
        embed = disnake.Embed(
            title="Управление сервером",
            description=f"Сервер **{server_name}** {action_label.get(action, action)}.",
            color=disnake.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as exc:
        logger.exception("Не удалось выполнить действие %s для %s", action, server_name)
        await interaction.response.send_message(
            f"Ошибка при выполнении действия '{action}' для сервера {server_name}: {exc}",
            ephemeral=True,
        )


@bot.event
async def on_ready():
    logger.info("Бот запущен как %s (ID: %s)", bot.user, bot.user.id if bot.user else "unknown")


@bot.slash_command(description="Запускает сервер")
async def start(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(
            f"У вас нет доступа к серверу {name}.", ephemeral=True
        )
        return
    await server_power_action(inter, name, "start")


@bot.slash_command(description="Останавливает сервер")
async def stop(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(
            f"У вас нет доступа к серверу {name}.", ephemeral=True
        )
        return
    await server_power_action(inter, name, "stop")


@bot.slash_command(description="Перезапускает сервер")
async def restart(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(
            f"У вас нет доступа к серверу {name}.", ephemeral=True
        )
        return
    await server_power_action(inter, name, "restart")


@bot.slash_command(description="Показывает состояние сервера")
async def status(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    user_id = str(inter.author.id)
    if not check_user_access(user_id, name):
        await inter.response.send_message(
            f"У вас нет доступа к серверу {name}.", ephemeral=True
        )
        return

    srv_id = get_server_id(name)
    if srv_id is None:
        await inter.response.send_message(f"Сервер {name} не найден.", ephemeral=True)
        return

    try:
        server_status = api.client.servers.get_server_utilization(srv_id)
        current_state = server_status.get("current_state", "unknown")
        resources = server_status.get("resources", {})

        embed_color = (
            disnake.Color.green() if current_state == "running" else disnake.Color.red()
        )
        embed = disnake.Embed(title=f"Состояние сервера: {name}", color=embed_color)
        embed.add_field(name="Текущее состояние", value=current_state, inline=False)
        embed.add_field(
            name="Использование CPU",
            value=f"{resources.get('cpu_absolute', 0)}%",
            inline=True,
        )
        embed.add_field(
            name="Использование памяти",
            value=format_bytes(resources.get("memory_bytes", 0)),
            inline=True,
        )
        embed.add_field(
            name="Использование диска",
            value=format_bytes(resources.get("disk_bytes", 0)),
            inline=True,
        )
        embed.add_field(
            name="Сетевой прием (RX)",
            value=format_bytes(resources.get("network_rx_bytes", 0)),
            inline=True,
        )
        embed.add_field(
            name="Сетевая передача (TX)",
            value=format_bytes(resources.get("network_tx_bytes", 0)),
            inline=True,
        )
        embed.add_field(
            name="Время работы",
            value=format_uptime(resources.get("uptime", 0)),
            inline=True,
        )

        view = ServerControlButtons(user_id=user_id, server_name=name)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await inter.original_response()
    except Exception as exc:
        logger.exception("Ошибка получения статуса сервера %s", name)
        await inter.response.send_message(
            f"Произошла ошибка при получении состояния сервера: {exc}",
            ephemeral=True,
        )


@bot.slash_command(description="Показывает список доступных серверов")
async def servers(inter):
    user_id = str(inter.author.id)
    available = get_available_servers_for_user(user_id)
    if not available:
        await inter.response.send_message(
            "У вас нет доступных серверов.", ephemeral=True
        )
        return

    embed = disnake.Embed(
        title="Доступные серверы",
        description="\n".join(f"• {server}" for server in available),
        color=disnake.Color.blue(),
    )
    await inter.response.send_message(embed=embed, ephemeral=True)


@bot.slash_command(description="Показывает, к каким серверам у пользователя есть доступ")
async def myaccess(inter):
    user_id = str(inter.author.id)
    available = get_available_servers_for_user(user_id)

    embed = disnake.Embed(
        title="Ваши права доступа",
        color=disnake.Color.dark_blue(),
        description=("\n".join(f"• {server}" for server in available) if available else "Нет назначенных серверов."),
    )
    if user_id in Config.SUPER_USERS:
        embed.set_footer(text="У вас права супер-пользователя.")

    await inter.response.send_message(embed=embed, ephemeral=True)


@bot.slash_command(description="Добавляет пользователя на сервер")
async def adduser(
    inter,
    member: disnake.User,
    server: str = commands.Param(autocomplete=autocomplete_servers),
):
    requester_id = str(inter.author.id)
    if requester_id not in Config.SUPER_USERS and not check_user_access(
        requester_id, server
    ):
        await inter.response.send_message(
            f"У вас нет прав на добавление пользователей на сервер {server}.",
            ephemeral=True,
        )
        return

    if get_server_id(server) is None:
        await inter.response.send_message(f"Сервер {server} не найден.", ephemeral=True)
        return

    user_id = str(member.id)
    user_access.setdefault(server, [])
    if user_id in user_access[server]:
        await inter.response.send_message(
            f"Пользователь {member.mention} уже имеет доступ к серверу {server}.",
            ephemeral=True,
        )
        return

    user_access[server].append(user_id)
    save_user_access(user_access)
    embed = disnake.Embed(
        title="Добавление пользователя",
        description=f"Пользователь {member.mention} добавлен на сервер {server}.",
        color=disnake.Color.green(),
    )
    await inter.response.send_message(embed=embed, ephemeral=True)


@bot.slash_command(description="Удаляет пользователя с сервера")
async def deluser(
    inter,
    member: disnake.User,
    server: str = commands.Param(autocomplete=autocomplete_servers),
):
    requester_id = str(inter.author.id)
    if requester_id not in Config.SUPER_USERS:
        await inter.response.send_message(
            f"У вас нет прав на удаление пользователей с сервера {server}.",
            ephemeral=True,
        )
        return

    user_id = str(member.id)
    if user_id not in user_access.get(server, []):
        await inter.response.send_message(
            f"Пользователь {member.mention} не имеет доступа к серверу {server}.",
            ephemeral=True,
        )
        return

    user_access[server].remove(user_id)
    if not user_access[server]:
        user_access.pop(server, None)
    save_user_access(user_access)
    embed = disnake.Embed(
        title="Удаление пользователя",
        description=f"Пользователь {member.mention} удален с сервера {server}.",
        color=disnake.Color.red(),
    )
    await inter.response.send_message(embed=embed, ephemeral=True)


@bot.slash_command(description="Принудительно обновляет список серверов из панели")
async def syncservers(inter):
    if str(inter.author.id) not in Config.SUPER_USERS:
        await inter.response.send_message(
            "Только супер-пользователь может обновлять кэш серверов.",
            ephemeral=True,
        )
        return

    try:
        servers = refresh_servers(force=True)
        await inter.response.send_message(
            f"Кэш серверов обновлен. Найдено серверов: {len(servers)}.",
            ephemeral=True,
        )
    except Exception as exc:
        logger.exception("Ошибка обновления кэша серверов")
        await inter.response.send_message(
            f"Не удалось обновить список серверов: {exc}",
            ephemeral=True,
        )


if __name__ == "__main__":
    bot.run(Config.DISCORD_TOKEN)
