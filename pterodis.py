import disnake
from disnake.ext import commands
from pydactyl import PterodactylClient
import pickle
import os

bot = commands.Bot(command_prefix=commands.when_mentioned)
api = PterodactylClient('https://youpanel.com', 'apikey') # URL вашей панели и API
my_servers = api.client.servers.list_servers()

if os.path.exists('user_access.pkl'):
    with open('user_access.pkl', 'rb') as f:
        user_access = pickle.load(f)
else:
    user_access = {}

super_users = ['user1', 'user2', 'user3']  #ID пользователей discord, которые имеют доступ ко всем серверам и изначальному добавлению игроков к серверам

def save_user_access():
    with open('user_access.pkl', 'wb') as f:
        pickle.dump(user_access, f)

def get_server_id(name):
    for server in my_servers:
        if 'attributes' in server and server['attributes']['name'] == name:
            return server['attributes']['identifier']
    return None

def check_user_access(user, server):
    return user in super_users or (server in user_access and user in user_access[server])

async def autocomplete_servers(inter, string: str) -> list[str]:
    user_id = str(inter.author.id)
    if user_id in super_users:
        servers = [server['attributes']['name'] for server in my_servers]
    else:
        servers = [server for server in user_access if user_id in user_access[server]]
    return [server for server in servers if string.lower() in server.lower()]

class ServerControlButtons(disnake.ui.View):
    def __init__(self, user_id: str, server_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.server_name = server_name

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        return str(interaction.user.id) == self.user_id

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @disnake.ui.button(label="Запустить", style=disnake.ButtonStyle.green)
    async def start_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, 'start')

    @disnake.ui.button(label="Перезапустить", style=disnake.ButtonStyle.blurple)
    async def restart_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, 'restart')

    @disnake.ui.button(label="Остановить", style=disnake.ButtonStyle.red)
    async def stop_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await server_power_action(interaction, self.server_name, 'stop')

async def server_power_action(interaction: disnake.MessageInteraction, server_name: str, action: str):
    server_id = get_server_id(server_name)
    if server_id:
        api.client.servers.send_power_action(server_id, action)
        await interaction.response.send_message(f"Команда '{action}' выполнена для сервера {server_name}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Сервер {server_name} не найден.", ephemeral=True)

@bot.slash_command(description="Останавливает сервер")
async def stop(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(f'У вас нет доступа к серверу {name}.', ephemeral=True)
        return
    srv_id = get_server_id(name)
    if srv_id is not None:
        api.client.servers.send_power_action(srv_id, 'stop')
        embed = disnake.Embed(title="Остановка сервера", description=f'Сервер {name} останавливается...', color=disnake.Color.red())
        await inter.response.send_message(embed=embed)
    else:
        await inter.response.send_message(f'Сервер {name} не найден.', ephemeral=True)

@bot.slash_command(description="Перезапускает сервер")
async def restart(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(f'У вас нет доступа к серверу {name}.', ephemeral=True)
        return
    srv_id = get_server_id(name)
    if srv_id is not None:
        api.client.servers.send_power_action(srv_id, 'restart')
        embed = disnake.Embed(title="Перезапуск сервера", description=f'Сервер {name} перезапускается...', color=disnake.Color.orange())
        await inter.response.send_message(embed=embed)
    else:
        await inter.response.send_message(f'Сервер {name} не найден.', ephemeral=True)

@bot.slash_command(description="Запускает сервер")
async def start(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(f'У вас нет доступа к серверу {name}.', ephemeral=True)
        return
    srv_id = get_server_id(name)
    if srv_id is not None:
        api.client.servers.send_power_action(srv_id, 'start')
        embed = disnake.Embed(title="Запуск сервера", description=f'Сервер {name} запускается...', color=disnake.Color.green())
        await inter.response.send_message(embed=embed)
    else:
        await inter.response.send_message(f'Сервер {name} не найден.', ephemeral=True)

@bot.slash_command(description="Показывает состояние сервера")
async def status(inter, name: str = commands.Param(autocomplete=autocomplete_servers)):
    if not check_user_access(str(inter.author.id), name):
        await inter.response.send_message(f'У вас нет доступа к серверу {name}.', ephemeral=True)
        return

    srv_id = get_server_id(name)
    if srv_id is None:
        await inter.response.send_message(f'Сервер {name} не найден.', ephemeral=True)
        return

    try:
        server_status = api.client.servers.get_server_utilization(srv_id)

        current_state = server_status['current_state']
        cpu_usage = server_status['resources']['cpu_absolute']
        memory_usage = server_status['resources']['memory_bytes']
        disk_usage = server_status['resources']['disk_bytes']
        network_rx = server_status['resources']['network_rx_bytes']
        network_tx = server_status['resources']['network_tx_bytes']
        uptime_milliseconds = server_status['resources']['uptime']

        if uptime_milliseconds > 0:
            uptime_seconds = uptime_milliseconds / 1000  
        else:
            uptime_seconds = 0  

        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_str = f"{int(days)} дн., {int(hours)} ч., {int(minutes)} мин., {int(seconds)} сек."

        embed_color = disnake.Color.green() if current_state == "running" else disnake.Color.red()
        embed = disnake.Embed(title=f"Состояние сервера: {name}", color=embed_color)
        embed.add_field(name="Текущее состояние", value=current_state, inline=False)
        embed.add_field(name="Использование ЦП", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="Использование памяти", value=f"{memory_usage / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="Использование диска", value=f"{disk_usage / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="Сетевой прием (RX)", value=f"{network_rx / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="Сетевая передача (TX)", value=f"{network_tx / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="Время работы", value=uptime_str, inline=True)

        if check_user_access(str(inter.author.id), name):
            view = ServerControlButtons(user_id=str(inter.author.id), server_name=name)
            await inter.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f'Произошла ошибка при получении состояния сервера: {e}', ephemeral=True)

@bot.slash_command(description="Добавляет пользователя на сервер")
async def adduser(inter, member: disnake.User, server: str = commands.Param(autocomplete=autocomplete_servers)):
    requester_id = str(inter.author.id)
    if not check_user_access(requester_id, server) and requester_id not in super_users:
        await inter.response.send_message(f'У вас нет прав на добавление пользователей на сервер {server}.', ephemeral=True)
        return

    srv_id = get_server_id(server)
    if srv_id is None:  
        await inter.response.send_message(f'Сервер {server} не найден.', ephemeral=True)
        return

    user_id = str(member.id)
    if server not in user_access:
        user_access[server] = []
    if user_id not in user_access[server]:
        user_access[server].append(user_id)
        save_user_access()
        embed = disnake.Embed(title="Добавление пользователя", description=f'Пользователь {member.mention} добавлен на сервер {server}.', color=disnake.Color.green())
        await inter.response.send_message(embed=embed)
    else:
        await inter.response.send_message(f'Пользователь {member.mention} уже имеет доступ к серверу {server}.', ephemeral=True)

@bot.slash_command(description="Удаляет пользователя с сервера")
async def deluser(inter, member: disnake.User, server: str = commands.Param(autocomplete=autocomplete_servers)):
    if str(inter.author.id) not in super_users:
        await inter.response.send_message(f'У вас нет прав на удаление пользователей с сервера {server}.', ephemeral=True)
        return
    user_id = str(member.id)
    if server in user_access and user_id in user_access[server]:
        user_access[server].remove(user_id)
        save_user_access()
        embed = disnake.Embed(title="Удаление пользователя", description=f'Пользователь {member.mention} удален с сервера {server}.', color=disnake.Color.red())
        await inter.response.send_message(embed=embed)
    else:
        await inter.response.send_message(f'Пользователь {member.mention} не имеет доступа к серверу {server}.', ephemeral=True)

@bot.slash_command(description="Показывает список доступных серверов")
async def servers(inter):
    user_id = str(inter.author.id)
    if user_id in super_users:
        servers = [server['attributes']['name'] for server in my_servers]
    else:
        servers = [server for server in user_access if user_id in user_access[server]]
    embed = disnake.Embed(title="Доступные серверы", description=f'Список доступных серверов: {", ".join(servers)}.', color=disnake.Color.blue())
    await inter.response.send_message(embed=embed)

bot.run('token') # Ваш токен
