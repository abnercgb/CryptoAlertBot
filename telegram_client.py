import logging
import os
import telegram
# Importar as classes do telegram.ext
# CORRIGIDO: Filters agora é importado diretamente de telegram.ext
from telegram.ext import Application, MessageHandler, CommandHandler, filters # Use 'filters' em minúsculo para a nova API

from typing import Dict, Any, Callable, Optional, List, Union

# Importar a exceção específica do Telegram (se ainda precisar para tratamento de Conflict)
from telegram.error import Conflict # Importa a exceção Conflict

logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class TelegramClient:
    # CORRIGIDO: A inicialização na v20+ usa Application em vez de Updater
    def __init__(self, bot_token: str, message_handler_instance: Any): # message_handler_instance será a instância do seu MessageHandler
        """
        Inicializa o TelegramClient e conecta ao Telegram usando a API v20+.
        :param bot_token: O token do seu bot do Telegram.
        # CORRIGIDO: Agora passamos a instância completa do MessageHandler
        :param message_handler_instance: A instância do MessageHandler com os métodos de tratamento.
        """
        if not bot_token:
            logger.critical("❌ TELEGRAM_BOT_TOKEN is not set. Cannot initialize TelegramClient.")
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")

        # CORRIGIDO: Use Application.builder() para inicializar o bot na v20+
        self.application = Application.builder().token(bot_token).build()
        self.bot = self.application.bot # O objeto bot está acessível via application
        self.message_handler_instance = message_handler_instance # Guarda a referência da instância do MessageHandler

        # Registrar os handlers
        self._register_handlers()

        try:
            bot_info = self.bot.get_me()
            logger.info(f"Connected to Telegram bot: @{bot_info.username}")
        except telegram.error.TelegramError as e:
            logger.critical(f"❌ Failed to connect to Telegram API: {e}", exc_info=True)
            raise # Re-lança a exceção, pois a conexão é crítica


    def _register_handlers(self):
        """Registra os handlers no application do Telegram (v20+)."""
        # CORRIGIDO: Use filters.TEXT e filters.COMMAND da nova API
        # Use CommandHandler para comandos e MessageHandler para texto não comando
        # O callback agora é o método handle_message da instância message_handler_instance

        # Handler para comandos (mensagens que começam com /)
        self.application.add_handler(CommandHandler("start", self.message_handler_instance.handle_message)) # Exemplo para /start
        # Adicione outros CommandHandlers aqui para comandos específicos,
        # ou use um MessageHandler com filters.COMMAND se seu handle_message
        # lida com todos os comandos genericamente.

        # Se seu handle_message lida com TODOS os comandos, você pode usar:
        self.application.add_handler(MessageHandler(filters.COMMAND, self.message_handler_instance.handle_message))
        logger.debug("✅ Command handler registered with filter filters.COMMAND")


        # Handler para mensagens de texto que NÃO são comandos
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler_instance.handle_message))
        logger.debug("✅ Text message handler registered with filter filters.TEXT & ~filters.COMMAND")

        # TODO: Adicionar outros handlers (ex: para fotos, documentos, etc.) se necessário


    # CORRIGIDO: Não precisamos mais do método _wrapper_message_handler
    # O handle_message no MessageHandler agora recebe update e context diretamente


    # CORRIGIDO: O método send_message agora usa self.bot.send_message diretamente
    # O parse_mode padrão foi movido para a chamada real
    def send_message(self, chat_id: Union[int, str], text: str, parse_mode: Optional[str] = None) -> None:
        """
        Envia uma mensagem para um chat específico usando a API v20+.
        :param chat_id: O ID do chat.
        :param text: O texto da mensagem.
        :param parse_mode: Modo de parse (ex: 'HTML', 'MarkdownV2'). Padrão é None.
        """
        try:
            logger.debug(f"Attempting to send message to chat {chat_id}: {text[:50]}...") # Loga o início da mensagem
            # CORRIGIDO: Use self.bot.send_message diretamente
            # O parse_mode padrão pode ser definido aqui ou na chamada
            self.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            # Não logamos sucesso aqui para evitar logs excessivos, o wrapper já loga (se ainda existisse)
            # logger.debug(f"Message sent successfully to chat {chat_id}.")
        except telegram.error.TelegramError as e:
            logger.error(f"❌ Failed to send message to chat {chat_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ An unexpected error occurred while sending message to chat {chat_id}: {e}", exc_info=True)


    # CORRIGIDO: O método start_listening agora usa self.application.run_polling()
    def start_listening(self):
        """Inicia o polling para receber mensagens (v20+)."""
        logger.info("Starting Telegram listener (polling).")
        # --- Adiciona tratamento de erro para Conflict ---
        try:
            # CORRIGIDO: Use run_polling() na v20+
            # run_polling é bloqueante e mantém o bot rodando
            self.application.run_polling()
            logger.info("✅ Telegram listener started.")
            # Não precisamos de updater.idle() ou application.idle() explicitamente
            # se run_polling() for a última coisa no thread principal.
        except Conflict as e:
             logger.critical(f"❌ Conflict error during polling: {e}. Ensure only one bot instance is running with this token.", exc_info=True)
             # Aqui você pode adicionar lógica para tentar reiniciar após um tempo,
             # mas a causa raiz (multiplas instâncias) precisa ser resolvida manualmente.
             # Por enquanto, apenas logamos o erro crítico.
        except Exception as e:
             logger.critical(f"❌ An unexpected error occurred while starting Telegram listener: {e}", exc_info=True)
             raise # Re-lança para que o processo principal saiba que houve uma falha crítica

    # CORRIGIDO: Adicionar um método stop_listening se precisar parar o bot
    def stop_listening(self):
        """Para o polling (v20+)."""
        logger.info("Stopping Telegram listener.")
        self.application.stop_running()
        logger.info("Telegram listener stopped.")

