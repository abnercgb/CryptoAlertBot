import os
import logging
# Removendo importação de threading e Flask, pois não rodaremos Flask em thread
# import threading
# from flask import Flask # Remover Flask se não for essencial para health check/outro propósito

# Importar as classes do seu bot
from database_manager import DatabaseManager
from telegram_client import TelegramClient
from coingecko_client import CoinGeckoClient
from message_handler import MessageHandler
# Importar PriceMonitor
from price_monitor import PriceMonitor # Importar PriceMonitor


# --- Configuração Centralizada de Logging ---
# Configura o logger raiz para o nível INFO, que inclui INFO, WARNING, ERROR, CRITICAL
# Isso reduz a verbosidade de bibliotecas que logam muito em DEBUG
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Opcional: Manter o nível DEBUG para os seus módulos específicos se desejar logs detalhados deles
logging.getLogger('database_manager').setLevel(logging.DEBUG)
logging.getLogger('telegram_client').setLevel(logging.DEBUG)
logging.getLogger('coingecko_client').setLevel(logging.DEBUG)
logging.getLogger('message_handler').setLevel(logging.DEBUG)
logging.getLogger('price_monitor').setLevel(logging.DEBUG)

# Configura o logger da biblioteca telegram.bot para INFO ou superior
# Isso vai ocultar as mensagens DEBUG "Entering/Exiting: get_updates"
logging.getLogger('telegram.bot').setLevel(logging.INFO)
logging.getLogger('telegram.ext.updater').setLevel(logging.INFO) # Opcional: também reduzir logs do updater
logging.getLogger('telegram.ext.dispatcher').setLevel(logging.INFO) # Opcional: também reduzir logs do dispatcher
# Na v20+, pode haver outros loggers como telegram.ext.Application, ajustar se necessário

logger = logging.getLogger(__name__)
# --- Fim da Configuração Centralizada de Logging ---


# Obter variáveis de ambiente
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') # Usado para alertas gerais ou logs
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./database.db') # Padrão para SQLite local
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') # Se estiver usando OpenAI

# Verificar se o token do bot está configurado
if not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
    exit(1) # Sai do script se o token não estiver configurado

# --- Inicialização das Classes ---
try:
    db_manager = DatabaseManager(db_url=DATABASE_URL)
    logger.info("✅ DatabaseManager instance initialized.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize DatabaseManager: {e}", exc_info=True)
    exit(1) # Sai do script se o DB falhar

# Inicializar o cliente CoinGecko
price_client = CoinGeckoClient()
logger.info("✅ CoinGeckoAPI client initialized.")
if not price_client.is_ready():
     logger.warning("CoinGeckoClient might not be fully ready.")
logger.info("✅ CoinGeckoClient instance initialized and ready.")


# Inicializar o MessageHandler (passando as instâncias reais)
# O MessageHandler precisa da referência da função send_message do TelegramClient
# Inicializamos TelegramClient primeiro e depois passamos a instância do MessageHandler.

# Inicialização do TelegramClient (passando None temporariamente para message_handler_instance)
# CORRIGIDO: Usando o nome de argumento correto 'bot_token'
telegram_client = TelegramClient(bot_token=TELEGRAM_BOT_TOKEN, message_handler_instance=None)
logger.info("✅ TelegramClient instance initialized.")


# Inicializar o MessageHandler (passando as instâncias reais)
message_handler = MessageHandler(db_manager=db_manager, price_client=price_client, telegram_client=telegram_client)
logger.info("✅ MessageHandler instance created.")

# Agora que message_handler foi criado, define a referência real no telegram_client
# CORRIGIDO: Passando a instância completa do message_handler
telegram_client.message_handler_instance = message_handler
logger.info("✅ MessageHandler instance registered with TelegramClient.")


# Inicializar o PriceMonitor (passando as instâncias reais)
# O PriceMonitor precisará do db_manager e do telegram_client para enviar alertas
# CORRIGIDO: Passando TELEGRAM_CHAT_ID para o PriceMonitor
price_monitor = PriceMonitor(db_manager=db_manager, price_client=price_client, telegram_client=telegram_client, chat_id_for_alerts=TELEGRAM_CHAT_ID)
logger.info("✅ PriceMonitor instance created.")


# --- Configuração e Início do Bot ---
logger.info("Bot application starting...")

# Iniciar o scheduler do PriceMonitor
# CORRIGIDO: Chamando o método start() do PriceMonitor
price_monitor.start()
logger.info("✅ Price monitoring service started.")


# Iniciar o listener do Telegram (polling)
# Esta chamada é bloqueante e mantém o script rodando para um Background Worker.
# O tratamento de erro para Conflict já está dentro de start_listening no TelegramClient.
# CORRIGIDO: Chamando o método start_listening() do TelegramClient
telegram_client.start_listening()


# O código abaixo só será alcançado se start_listening() for interrompido.
logger.info("Telegram listener stopped. Bot application shutting down.")

# Opcional: Adicionar lógica de cleanup aqui se necessário antes de sair
# price_monitor.stop_scheduler() # Parar o scheduler se ele ainda estiver rodando
# db_manager.close_all_sessions() # Fechar todas as sessões do DB se necessário
