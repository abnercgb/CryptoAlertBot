import os
import logging
from dotenv import load_dotenv
from telegram_client import TelegramClient
from database_manager import DatabaseManager
from message_handler import MessageHandler
# Importe CoinGeckoClient aqui, pois é a implementação de price_client que usaremos
from coingecko_client import CoinGeckoClient
# Importa a nova classe PriceMonitor
from price_monitor import PriceMonitor
import time # <-- ADICIONADO: Importa o módulo time

# TODO: Implementar IntentRecognizer e OpenAIClient se necessário
# from intent_recognizer import IntentRecognizer
# from openai_client import OpenAIClient

# Configuração básica de logging
# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Obter o token do bot do Telegram e a URL do banco de dados das variáveis de ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Verificações Iniciais Críticas ---
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_TOKEN not found in environment variables. Please set it in the .env file.")
    exit() # Sai do programa se o token não estiver definido

if not DATABASE_URL:
    logger.critical("❌ DATABASE_URL not found in environment variables. Please set it (e.g., sqlite:///./database.db) in the .env file.")
    exit() # Sai do programa se a URL do DB não estiver definida

# --- Inicialização das Dependências ---

# Inicializa o DatabaseManager
db_manager = None
try:
    # Passa a URL do banco de dados para o DatabaseManager
    db_manager = DatabaseManager(db_url=DATABASE_URL)
    # O DatabaseManager já tenta criar tabelas na inicialização (se descomentado)
    logger.info("✅ DatabaseManager instance initialized.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize DatabaseManager: {e}", exc_info=True)
    # O bot não pode operar sem DB, então podemos sair ou tentar continuar com funcionalidade limitada
    # Por enquanto, vamos parar se o DB falhar na inicialização crítica
    exit()


# Inicializa o TelegramClient
telegram_client = None
try:
    # Passa o token do Telegram para o TelegramClient
    telegram_client = TelegramClient(token=TELEGRAM_TOKEN)
    logger.info("✅ TelegramClient instance initialized.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize TelegramClient: {e}", exc_info=True)
    # O bot não pode operar sem Telegram, então saímos
    exit()

# Inicializa o Price Client (usando CoinGeckoClient)
price_client = None
try:
    price_client = CoinGeckoClient() # Instancia o CoinGeckoClient
    if price_client.is_ready():
        logger.info("✅ CoinGeckoClient instance initialized and ready.")
    else:
         logger.warning("🟡 CoinGeckoClient initialized but not ready.")
except Exception as e:
    logger.error(f"❌ Failed to initialize CoinGeckoClient: {e}", exc_info=True)
    price_client = None # Garante que price_client é None se a inicialização falhar


# TODO: Inicializar IntentRecognizer e OpenAIClient se necessário
# intent_recognizer = IntentRecognizer(...)
# openai_client = OpenAIClient(...)


# Inicializa o MessageHandler com as dependências
message_handler = None
try:
    # Passa as instâncias criadas para o MessageHandler
    message_handler = MessageHandler(
        telegram_client=telegram_client,
        db_manager=db_manager,
        price_client=price_client, # Passa a instância do price_client (CoinGecko)
        # openai_client=openai_client, # Passa instância opcional
        # intent_recognizer=intent_recognizer # Passa instância opcional
    )
    logger.info("✅ MessageHandler instance created.")
except Exception as e:
    logger.critical(f"❌ Failed to create MessageHandler instance: {e}", exc_info=True)
    # O bot não pode processar mensagens sem o MessageHandler, saímos.
    exit()

# --- Inicializa o PriceMonitor ---
price_monitor = None
# Apenas inicializa o monitor se todas as dependências críticas estiverem prontas
if db_manager and price_client and telegram_client:
    try:
        # Passa as instâncias necessárias para o PriceMonitor
        price_monitor = PriceMonitor(
            db_manager=db_manager,
            price_client=price_client,
            telegram_client=telegram_client
        )
        logger.info("✅ PriceMonitor instance created.")
    except Exception as e:
        logger.error(f"❌ Failed to create PriceMonitor instance: {e}", exc_info=True)
        price_monitor = None
else:
     logger.warning("🟡 Could not create PriceMonitor instance due to missing dependencies. Price monitoring will not be available.")


# --- Funções Principais do Bot ---

# Função start_price_monitor antiga removida/substituída pela inicialização e start do PriceMonitor acima.

def run_bot():
    """
    Função principal para configurar e iniciar o bot.
    """
    logger.info("Bot application starting...")

    # Inicia o monitor de preços (thread/serviço) SE ele foi inicializado com sucesso
    if price_monitor:
         price_monitor.start()
         logger.info("✅ Price monitoring service started.")
    else:
         logger.warning("🟡 Price monitoring service not started.")


    # Configura e inicia o listener do Telegram
    logger.info("Starting Telegram listener.")
    if telegram_client and message_handler:
        try:
            # Passa o método handle_message do message_handler para o TelegramClient
            # O TelegramClient irá chamar message_handler.handle_message para cada mensagem recebida
            telegram_client.start_polling(message_handler.handle_message)
            logger.info("✅ MessageHandler registered with TelegramClient.")
            logger.info("✅ Telegram listener started.")
        except Exception as e:
            logger.critical(f"❌ Failed to start Telegram listener: {e}", exc_info=True)
            # Se o listener falhar, o bot não pode receber mensagens, saímos.
            exit()
    else:
        logger.critical("❌ TelegramClient or MessageHandler is not initialized. Cannot start listener.")
        exit()

    # --- MANTÉM O THREAD PRINCIPAL RODANDO ---
    # Isso ajuda a prevenir que o interpretador Python entre em estado de shutdown
    # inesperado, o que pode afetar threads e schedulers de background como o APScheduler.
    # O servidor Flask também ajuda, mas este loop é uma garantia adicional no thread principal.
    try:
        while True: # <-- ADICIONADO: Loop infinito para manter o thread principal ativo
            time.sleep(1) # Espera 1 segundo para não usar 100% da CPU
    except KeyboardInterrupt:
        # Permite parar o bot com CTRL+C no console
        logger.info("KeyboardInterrupt received. Stopping bot...")
    except Exception as e:
        logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
    finally:
        # TODO: Implementar shutdown elegante dos threads (polling, scheduler) aqui, se necessário
        # scheduler.shutdown() etc. - Depende de como start_polling/start são implementados para parar
        logger.info("Bot main loop finished.")


# --- Execução Principal ---
if __name__ == "__main__":
    # O servidor Flask é iniciado em um thread separado ANTES de run_bot()
    # para garantir que o Replit esteja escutando a porta 5000 imediatamente.
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.route('/')
        def home():
            # Retorna o status do scheduler, se disponível
            status = "running" if price_monitor and price_monitor.scheduler.running else "stopped/initializing"
            return f"Bot is running! Price Monitor Scheduler status: {status}" # Mensagem mais informativa

        # Usa 0.0.0.0 para ser acessível externamente no Replit
        # A porta 5000 é a padrão do Flask, mas o Replit mapeia automaticamente
        # Use thread=True para não bloquear o thread principal, embora o polling e o scheduler já rodem em outros.
        from threading import Thread
        def run_flask():
             # Desabilita o logger do Flask/Werkzeug se quiser menos output
             # logging.getLogger('werkzeug').setLevel(logging.WARNING)
             logger.info("Starting Flask web server thread.")
             # use_reloader=False é importante para não criar múltiplos processos no Replit
             app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
             logger.info("Flask web server thread finished.") # Este log só aparece se o servidor parar

        flask_thread = Thread(target=run_flask)
        flask_thread.daemon = True # Permite que o programa Python termine mesmo que a thread Flask esteja rodando
        flask_thread.start()
        logger.info("Flask web server thread started.")

    except ImportError:
        logger.warning("Flask not installed. Web server to keep Replit alive will not run.")
        logger.warning("Install Flask with: pip install Flask")
    except Exception as e:
        logger.error(f"An error occurred while starting Flask web server thread: {e}", exc_info=True)

    # Chama a função principal que inicia o polling e o scheduler
    run_bot()

    # O loop while True em run_bot() manterá o thread principal rodando aqui.
    # O código após run_bot() só seria alcançado se o loop infinito fosse quebrado
    # (ex: por um KeyboardInterrupt ou uma exceção não tratada dentro do loop).
    logger.info("Main script finished.") # Este log provavelmente nunca será alcançado em operação normal