import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
from discord import Embed
import asyncio
import discord
import aiohttp
import io
import os
from discord.ext import commands
from discord.ui import Modal, TextInput
from datetime import datetime

# ============================
#   CONFIGURAÇÕES DO SERVIDOR
# ============================
GUILD_ID = 1473794022622363842


VERIFY_CHANNEL_ID = 1496017827323318433
LOG_CHANNEL_ID = 1495948374824845485

ROLE_VERIFY_ID = 1473794022622363849
ROLE_AUTOROLE_ID = 1473794022639407175
ADMIN_ROLE_ID = 1495948491586015262


PAINEL_CHANNEL_ID = 1496017847405772902


# Advertências
ID_CARGO_ADV1 = 1495945905826693171
ID_CARGO_ADV2 = 1495947682009710732
ID_CARGO_ADV3 = 1495947750532059328
ID_CARGO_BANIDO = 1473794022622363850

# Autorizados para comandos (todos os slash commands usarão estes cargos)
CARGOS_AUTORIZADOS = [
    1495948491586015262,
]

# ============================
#         BOT + INTENTS
# ============================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
TOKEN = os.getenv("TOKEN_PRF")  # Certifique-se de definir o TOKEN no .env ou variáveis de ambiente # Certifique-se de definir o TOKEN no .env ou variáveis de ambiente

# guard para não reenviar painel/verify em reconexões
bot._ready_sent = False

# ============================
#        SISTEMA DE LOGS
# ============================
async def enviar_log_embed(guild: discord.Guild, embed: discord.Embed):
    """Envia embed para o canal de logs se existir."""
    if not guild:
        return
    canal = guild.get_channel(LOG_CHANNEL_ID)
    if canal:
        try:
            await canal.send(embed=embed)
        except Exception:
            # evita crash por falta de permissões
            return

async def enviar_log(guild, titulo, descricao, cor=discord.Color.green()):
    canal = guild.get_channel(LOG_CHANNEL_ID) if guild else None
    if canal:
        embed = discord.Embed(title=titulo, description=descricao, color=cor)
        embed.set_footer(text="Sistema de Logs - PRF Virtual")
        try:
            await canal.send(embed=embed)
        except Exception:
            pass

# ============================
#  HELPERS DE PERMISSÃO
# ============================
def has_authorized_role(member: discord.Member) -> bool:
    """Checa se o membro possui pelo menos um dos cargos autorizados."""
    if not member or not hasattr(member, "roles"):
        return False
    return any(role.id in CARGOS_AUTORIZADOS for role in member.roles)

async def require_authorized(interaction: discord.Interaction) -> bool:
    """Verificação async (uso em comandos) — retorna True se autorizado."""
    if not has_authorized_role(interaction.user):
        await interaction.response.send_message("❌ Você não tem permissão (cargo inválido).", ephemeral=True)
        return False
    return True

# ============================
#        COMANDO /clearall
# ============================
@bot.tree.command(name="clearall", description="Apaga todas as mensagens do canal atual.", guild=discord.Object(id=GUILD_ID))
async def clearall(interaction: discord.Interaction):
    # validar cargo autorizado
    if not await require_authorized(interaction):
        return

    canal = interaction.channel
    guild = interaction.guild
    if canal is None or guild is None:
        return await interaction.response.send_message("❌ Contexto inválido.", ephemeral=True)

    # responder rápido
    await interaction.response.send_message(f"🧹 Limpando todas as mensagens do canal **{canal.name}**...", ephemeral=True)

    # limpa mensagens
    try:
        # limite=None as vezes falha em alguns builds, tenta em bloco
        await canal.purge(limit=None)
    except Exception:
        try:
            await canal.purge()
        except Exception:
            # se tudo falhar, informa o usuário
            pass

    # enviar confirmação no canal limpo (se permitido)
    try:
        embed_confirm = discord.Embed(
            title="🧹 Canal Limpo",
            description=f"As mensagens do canal `{canal.name}` foram apagadas com sucesso!",
            color=discord.Color.green()
        )
        await canal.send(embed=embed_confirm)
    except Exception:
        # sem permissão para enviar no canal limpo — ignora
        pass

    # preparar log detalhado e enviar para o canal de logs (LOG_CHANNEL_ID)
    embed_log = discord.Embed(
        title="🧹 Log - Canal Limpo",
        description=(
            f"**Usuário:** {interaction.user.mention}\n"
            f"**ID do usuário:** `{interaction.user.id}`\n"
            f"**Canal limpo:** {canal.mention}\n"
            f"**Servidor:** `{guild.name}`"
        ),
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow()
    )
    embed_log.set_footer(text=f"Ação: clearall")

    await enviar_log_embed(guild, embed_log)

# ============================
#         MODAL /mensagem
# ============================
class MensagemModal(Modal, title="📢 Enviar Mensagem"):
    conteudo = TextInput(
        label="Conteúdo da mensagem",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        # checar autorização rapidamente
        if not has_authorized_role(interaction.user):
            # interação ainda pode ser respondida
            await interaction.response.send_message("❌ Você não tem permissão para usar este modal.", ephemeral=True)
            return

        await interaction.response.send_message("⏳ Enviando...", ephemeral=True)

        try:
            msg_inicial = await interaction.channel.send(self.conteudo.value)
        except Exception:
            await interaction.followup.send("❌ Não consegui enviar a mensagem inicial (permissão).", ephemeral=True)
            return

        await interaction.followup.send(
            "📎 Responda aquela mensagem com anexos em até 5 minutos.",
            ephemeral=True
        )

        def check(m: discord.Message):
            return (
                m.reference and
                m.reference.message_id == msg_inicial.id and
                m.author == interaction.user and
                m.channel == interaction.channel
            )

        try:
            reply = await bot.wait_for("message", timeout=300.0, check=check)
            files = []
            async with aiohttp.ClientSession() as session:
                for a in reply.attachments:
                    try:
                        async with session.get(a.url) as resp:
                            dados = await resp.read()
                            files.append(discord.File(io.BytesIO(dados), filename=a.filename))
                    except Exception:
                        continue

            # tenta deletar mensagens do usuário e a de confirmação
            try:
                await msg_inicial.delete()
                await reply.delete()
            except Exception:
                pass

            try:
                await interaction.channel.send(content=self.conteudo.value, files=files)
            except Exception:
                await interaction.followup.send("❌ Não consegui reenviar a mensagem (permissão).", ephemeral=True)

        except asyncio.TimeoutError:
            # tempo esgotado — só ignora
            try:
                await interaction.followup.send("⏰ Tempo esgotado. Nenhum anexo recebido.", ephemeral=True)
            except Exception:
                pass

@bot.tree.command(name="mensagem", description="Enviar mensagem como o bot.", guild=discord.Object(id=GUILD_ID))
async def mensagem(interaction: discord.Interaction):
    if not await require_authorized(interaction):
        return
    # abrir modal
    await interaction.response.send_modal(MensagemModal())

# ============================
#      SISTEMA DE ADVs
# ============================
@bot.tree.command(name="adv", description="Aplica advertência.", guild=discord.Object(id=GUILD_ID))
async def adv(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    if not await require_authorized(interaction):
        return

    # mantém checagem extra: só membros com permissão de kick podem aplicar adv (opcional)
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("❌ Você precisa de permissão para expulsar (kick) para aplicar advertências.", ephemeral=True)

    adv1 = interaction.guild.get_role(ID_CARGO_ADV1)
    adv2 = interaction.guild.get_role(ID_CARGO_ADV2)
    adv3 = interaction.guild.get_role(ID_CARGO_ADV3)
    banido = interaction.guild.get_role(ID_CARGO_BANIDO)

    if banido in membro.roles:
        return await interaction.response.send_message("⚠ Esse membro já está banido.", ephemeral=True)

    if adv3 in membro.roles:
        try:
            await membro.remove_roles(adv3)
            await membro.add_roles(banido)
            msg = "🚫 4ª advertência → DEMITIDO"
        except Exception:
            return await interaction.response.send_message("❌ Erro ao atualizar cargos.", ephemeral=True)
    elif adv2 in membro.roles:
        await membro.remove_roles(adv2)
        await membro.add_roles(adv3)
        msg = "⚠ 3ª advertência aplicada!"
    elif adv1 in membro.roles:
        await membro.remove_roles(adv1)
        await membro.add_roles(adv2)
        msg = "⚠ 2ª advertência aplicada!"
    else:
        await membro.add_roles(adv1)
        msg = "⚠ 1ª advertência aplicada!"

    await interaction.response.send_message(msg, ephemeral=True)

    # log
    embed = discord.Embed(
        title="⚠ Advertência aplicada",
        description=f"**Membro:** {membro.mention}\n\n**Motivo:** {motivo}\n\n**Aplicada por:** {interaction.user.mention}",
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow()
    )

    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495965745400516708/PRF.png?ex=69e82a2b&is=69e6d8ab&hm=4874fa132517e00dc46de34d3c751c5bd6cf273b072f26d39a2ac2b97f346f6f&\n")


    embed.set_image(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495987937299533824/PRF_FAIXA_2.png?ex=69e83ed6&is=69e6ed56&hm=83ee4ba1543022157934325da3557a8339ed385de55c1a2344e9f54f8f26584a&")
    embed.set_footer(text="Batalhão PRF Virtual® Todos direitos reservados.")
        
    await enviar_log_embed(interaction.guild, embed)   
    
         

# ============================
#            BAN
# ============================
@bot.tree.command(name="ban", description="Bane um membro.", guild=discord.Object(id=GUILD_ID))
async def ban(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    if not await require_authorized(interaction):
        return

    # checar permissão de ban
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("❌ Você precisa da permissão de banir.", ephemeral=True)

    try:
        await membro.ban(reason=motivo)
        await interaction.response.send_message(f"🔨 {membro.mention} banido!", ephemeral=True)
    except discord.Forbidden:
        return await interaction.response.send_message("❌ O bot não pode banir esse usuário.", ephemeral=True)

    embed = discord.Embed(
        title="🚫 Membro Banido",
        description=f"**Membro:** {membro.mention}\n**Por:** {interaction.user.mention}\n**Motivo:** {motivo}",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    await enviar_log_embed(interaction.guild, embed)    

# ================= CONFIG =================


CANALETA_SOLICITAR_SET_ID = 1473794023343915085
CARGO_NOVATO_ID = 1473794022622363849   
CATEGORIA_TICKET_ID = 1473794023343915082

# Canal de logs exclusivo ROTA
CANAL_LOGS_ROTA = 1495945742290911302

# Cargo da companhia ROTA
CARGO_ROTA_ID = 1473794022639407175

CARGO_1CIA_ID = 1495526378601189456
CARGO_2CIA_ID = 1495526435656437861

# ================= PATENTES ROTA =================

PATENTES_ROTA = {
    "AGENTE 3° CLASSE": {
        "roles": [1473794022651986023,]
        
    },
    "AGENTE 2° CLASSE": {
        "roles": [1473794022651986024,]

    },
    "AGENTE 1° CLASSE": {
        "roles": [1473794022651986025,]
        
    },
    "AGENTE ESPECIAL": {
        "roles": [1473794022651986026,]
        
    },
    "INSPETOR / SUPERVISOR OPERCIONAL": {
        "roles": [1473794022651986027,]
        
    },
    "COORDENADOR OPERACIONAL": {
        "roles": [1473794022651986028,]
        
    },
    "CORREGEDOR(A)": {
        "roles": [1473794022651986031,]
        
    },
    "SUPERVISOR REGIONAL": {
        "roles": [1473794022651986030,]
        
    },
    "SUBDIRETOR": {
        "roles": [1473794022651986032,]
        
    },

    "DIRETOR DE DEPARTAMENTO": {
        "roles": [1473794022664306771,]
        
    },

    "DIRETOR ADJUNTO": {
        "roles": [1473794022664306772,]
       
    },

    "DIRETOR GERAL": {
        "roles": [1473794022664306773,]
        
    },


}

solicitacoes_abertas = {}

# ================= TICKET =================

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)  # 🔥 ESSENCIAL

    @discord.ui.button(
        label="Solicitar Funcional", 
        style=discord.ButtonStyle.secondary,
        emoji="<:AMARELO:1495480160319836412>",
        custom_id="ticket_abrir"
    )
    async def abrir_ticket(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id in solicitacoes_abertas:
            await interaction.response.send_message("⚠️ Você já possui um ticket aberto.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        category = guild.get_channel(CATEGORIA_TICKET_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        canal = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            category=category,
            overwrites=overwrites
        )

        solicitacoes_abertas[user.id] = {"canal_id": canal.id}

        # select de patente
        view = View()
        view.add_item(SelectPatente(user.id))

        # botão de ir ao ticket
        view_botao = View()
        view_botao.add_item(
            Button(
                label="Acessar Ticket",
                url=canal.jump_url,
                style=discord.ButtonStyle.link,
                emoji="<:AMARELO:1495480160319836412>"
            )
        )

        # embed bonito
        embed = discord.Embed(
            title="Ticket Criado com Sucesso 🎫",
            description=(
                f"Seu ticket foi criado!\n"   
                f"**Clique no botão abaixo** para ir até seu _ticket_."
            ),
            color=discord.Color.yellow()
        )

        embed.set_footer(text="• Batalhão PRF Virtual® Todos direitos reservados.")

        # mensagem dentro do ticket
        await canal.send(
            f"{user.mention}, Abaixo você poderá selecionar sua patente:",
            view=view
        )

        # resposta privada
        await interaction.response.send_message(
            embed=embed,
            view=view_botao,
            ephemeral=True
        )

# ================= SELECT PATENTE =================

class SelectPatente(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []

        for nome, dados in PATENTES_ROTA.items():
            options.append(
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    
                )
            )
        super().__init__(placeholder="selecione sua divisão de atuação", options=options)

    async def callback(self, interaction: discord.Interaction):
        patente_nome = self.values[0]
        dados = PATENTES_ROTA[patente_nome]
        patente_ids = dados["roles"]

        view = View()
        view.add_item(SelectCIA(self.user_id, patente_nome, patente_ids))

        await interaction.response.send_message(
            "Abra o próximo menu para escolher sua patente:",
            view=view,
            ephemeral=True
        )       

# ================= CIA =================

class SelectCIA(Select):
    def __init__(self, user_id, patente_nome, patente_ids):
        self.user_id = user_id
        self.patente_nome = patente_nome
        self.patente_ids = patente_ids

        options = [
            discord.SelectOption(label="POLICIA RODOVIÁRIA FEDERAL - PRF", value="PRF", emoji="<:PRF:1495964314539130980>"),
            discord.SelectOption(label="NÚCLEO DE OPERAÇÕES ESPECIAIS - NOE", value="NOE", emoji="<:NOE:1495964410261405818>"),
            discord.SelectOption(label="GRUPO DE PATRULHAMENTO MOTOCICLETA - GPM", value="GPM", emoji="<:GTM1:1495964467710787756>"),
            discord.SelectOption(label="GRUPO DE PATRULHAMENTO TÁTICO - GPT", value="GPT", emoji="<:GPT:1495964368238542909>"),
            discord.SelectOption(label="GRUPO DE RESPOSTA RÁPIDA - GRR", value="GRR", emoji="<:GRR:1495964391487836232>"),
            discord.SelectOption(label="DIVISÃO DE OPERAÇÕES AÉREAS - DOA", value="DOA", emoji="<:DOA:1495959857960980531>"),
        ]

        super().__init__(
            placeholder="Escolha sua divisão de atuação",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        cia = self.values[0]

        # abre o modal depois da CIA
        await interaction.response.send_modal(
            DadosPessoaisModal(
                self.user_id,
                self.patente_nome,
                self.patente_ids,
                cia
            )
        )     

# ================= MODAL =================

class DadosPessoaisModal(Modal, title="Registro do Policial"):
    nome = TextInput(label="Nome Completo", required=True, max_length=80)
    passaporte = TextInput(label="Passaporte", required=True, max_length=20)

    def __init__(self, user_id, patente_nome, patente_id, cia):
        super().__init__()
        self.user_id = user_id
        self.patente_nome = patente_nome
        self.patente_id = patente_id
        self.cia = cia

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True)

        nome = self.nome.value.strip()
        passaporte = self.passaporte.value.strip()

        solicitacoes_abertas[self.user_id].update({
            "patente_id": self.patente_id,
            "nome": nome,
            "passaporte": passaporte,
            "cia": self.cia
        })

        embed = Embed(
            title="Solicitação de Funcional",
            description=(
                f"**Solicitante:** {interaction.user.mention}\n"
                f"**Nome:** {nome}\n"
                f"**R.E:** {passaporte}\n"
                f"**Companhia:** {self.cia}\n"
                f"**Patente:**  {self.patente_nome}"
            ),
            color=discord.Color.yellow()
        )

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495965745400516708/PRF.png?ex=69e82a2b&is=69e6d8ab&hm=4874fa132517e00dc46de34d3c751c5bd6cf273b072f26d39a2ac2b97f346f6f&\n")


        embed.set_image(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495987937299533824/PRF_FAIXA_2.png?ex=69e83ed6&is=69e6ed56&hm=83ee4ba1543022157934325da3557a8339ed385de55c1a2344e9f54f8f26584a&")
        embed.set_footer(text="Batalhão PRF Virtual® Todos direitos reservados.")

        canal_logs = await interaction.client.fetch_channel(CANAL_LOGS_ROTA)
        await canal_logs.send(embed=embed, view=ConfirmarOuFecharView(self.user_id))

        await interaction.followup.send("✅ Solicitação enviada para avaliação.", ephemeral=True)


# ================= CONFIRMAR =================

class ConfirmarOuFecharView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(
            label="Aceitar Funcional", 
            style=discord.ButtonStyle.gray, 
            emoji="<:AMARELO:1495480160319836412> ",
            custom_id="confirmar_set"
            )
    async def confirmar(self, interaction: discord.Interaction, button: Button):

        dados = solicitacoes_abertas.pop(self.user_id, None)
        if not dados:
            await interaction.response.send_message("❌ Solicitação não encontrada.", ephemeral=True)
            return

        membro = interaction.guild.get_member(self.user_id)

        novo_apelido = f"{dados['cia']} | {dados['nome']} - {dados['passaporte']}"

        try:
            await membro.edit(nick=novo_apelido)
        except:
            pass

        novato = interaction.guild.get_role(CARGO_NOVATO_ID)
        if novato in membro.roles:
            await membro.remove_roles(novato)

        cargos_ids = dados['patente_id']

        cargos = []
        for role_id in cargos_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                cargos.append(role)

        cargo_rota = interaction.guild.get_role(CARGO_ROTA_ID)
        if cargo_rota:
            cargos.append(cargo_rota)

        if not cargos:
            return await interaction.response.send_message(
                "❌ Nenhum cargo válido encontrado.",
                ephemeral=True
            )

        await membro.add_roles(*cargos)

        agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.description += (
            f"\n\n**Aprovado por:** {interaction.user.mention}"
            f"\n**ID do aprovador:** `{interaction.user.id}`"
            f"\n**Data:** {agora}"
        )

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("✅ SET confirmado.", ephemeral=True)

        canal = interaction.guild.get_channel(dados["canal_id"])
        if canal:
            await asyncio.sleep(5)
            await canal.delete()


    @discord.ui.button(
            label="Recusar Funcional", 
            style=discord.ButtonStyle.gray, 
            emoji="<:x1:1495508233647952062>",
            custom_id="recusar_set"
            )
    async def cancelar(self, interaction: discord.Interaction, button: Button):

        dados = solicitacoes_abertas.pop(self.user_id, None)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.description += f"\n\n❌ **Cancelado por:** {interaction.user.mention}"

        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message("🗑️ Solicitação cancelada.", ephemeral=True)

        if dados:
            canal = interaction.guild.get_channel(dados["canal_id"])
            if canal:
                await asyncio.sleep(5)
                await canal.delete()

                

# ================= READY =================

@bot.event
async def on_ready():
    print(f"🔥 Bot conectado como {bot.user}")

    bot.add_view(TicketView())
    bot.add_view(ConfirmarOuFecharView(user_id=0))  # user_id dummy    

    print("📡 Guilds que o bot está:")
    for g in bot.guilds:
        print(f"- {g.name} | ID: {g.id}")

    guild = discord.utils.get(bot.guilds, id=GUILD_ID)

    if not guild:
        print(f"❌ Guild {GUILD_ID} NÃO encontrada.")
        return

    print(f"✅ Guild encontrada: {guild.name}")

    # ================= PAINEL SET =================

    try:
        canal = guild.get_channel(CANALETA_SOLICITAR_SET_ID)

        if canal:
            # Apaga mensagens antigas do bot
            async for msg in canal.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()

        # 1️⃣ Criar
        embed = discord.Embed(
            title=" Sistema de Funcional",
            description=("Clique no botão abaixo para iniciar sua solicitação.\n\n"
            "Clique no botão abaixo para alterar **Solicitar sua Funcional**.\n\n"
            "Regras:\n"
            "• Apenas nomes **REGISTRAVEIS**\n"
            "• Após a solicitação **AGUARDE**\n"            
            "• Apenas maiores de 18 anos\n"
            "• Todas as alterações são **registradas**\n\n"
            "• Caso tenha duvidas <#1495953861406363799>\n\n"                       
                         ),
            color=discord.Color.yellow()
        )

        # 2️⃣ Configurar
        embed.set_image(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495987937299533824/PRF_FAIXA_2.png?ex=69e83ed6&is=69e6ed56&hm=83ee4ba1543022157934325da3557a8339ed385de55c1a2344e9f54f8f26584a&") # IMAGEM RETANGULAR ABAIXO
        

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1444735189765849320/1495965745400516708/PRF.png?ex=69e82a2b&is=69e6d8ab&hm=4874fa132517e00dc46de34d3c751c5bd6cf273b072f26d39a2ac2b97f346f6f&\n") # IMAGEM QUADRADA A DIREITA


        embed.set_footer(text="Batalhão PRF Virtual® Todos direitos reservados.")
        

        # 3️⃣ Enviar
        await canal.send(embed=embed, view=TicketView())



    except Exception as e:  
        print(f"Erro ao enviar painel SET: {e}")
    

    # ================= SYNC SLASH =================

    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔧 Slash Commands sincronizados: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

    # ================= LOG DE START =================

    await enviar_log(guild, "🚀 Bot iniciado", "Sistema de SET e Slash Commands ativos.")


# ================= RUN =================

if not TOKEN:
    print("ERRO: TOKEN não definido. Coloque TOKEN no .env ou variáveis de ambiente.")
else:
    bot.run(TOKEN)
