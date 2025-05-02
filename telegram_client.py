import logging
from telegram.ext import Updater, MessageHandler, Filters
from typing import Callable, Dict, Any, List, Optional, Union # <--- Optional e Union adicionados aqui

logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

class TelegramClient:
    def __init__(self, token: str):
        """
        Inicializa o cliente Telegram com o token do bot.
        :param token: O token HTTP API do seu bot Telegram.
        """
        if not token:
            logger.critical("❌ Telegram token is required for TelegramClient initialization.")
            # Levantar exceção fatal se o token não for fornecido
            raise ValueError("Telegram token is missing")

        self.updater = None
        self.dispatcher = None
        try:
            # Cria um objeto Updater para receber atualizações do Telegram
            self.updater = Updater(token)

            # Obtém o Dispatcher para registrar handlers
            self.dispatcher = self.updater.dispatcher

            # Opcional: Logar informações do bot
            bot_info = self.updater.bot.get_me()
            logger.info(f"Connected to Telegram bot: @{bot_info.username}")

        except Exception as e:
            logger.critical(f"❌ Failed to initialize TelegramClient Updater or get bot info: {e}", exc_info=True)
            self.updater = None
            self.dispatcher = None
            # Propaga a exceção para que o main.py saiba que a inicialização falhou
            raise


    def start_polling(self, handler_func: Callable[[Dict[str, Any], List[Dict[str, str]]], Optional[str]]):
        """
        Inicia o polling para receber mensagens do Telegram.
        Registra um handler_func que será chamado para cada mensagem de texto.
        :param handler_func: Uma função que recebe um dict da mensagem e histórico, e retorna uma string de resposta ou None.
        """
        if self.dispatcher is None:
            logger.error("Telegram Dispatcher is not initialized. Cannot start polling.")
            return # Não pode iniciar sem o dispatcher

        # Wrapper para converter o objeto Update/CallbackContext para um dict simples
        # e lidar com o envio da resposta retornada pelo handler_func
        def wrapper_handler(update, context):
            # Verifica se a atualização contém uma mensagem de texto
            if update.message and update.message.text:
                message = update.message
                message_text = message.text
                chat_id = str(message.chat_id)
                user_id = str(message.from_user.id) # Usamos str() para consistência com o DB

                logger.debug(f"Received message from chat {chat_id}: {message_text[:50]}...")

                # Constrói um dicionário simplificado da mensagem para passar para o handler
                message_dict = {
                    "text": message_text,
                    "chat": {"id": chat_id},
                    "from": {
                        "id": user_id,
                        "username": getattr(message.from_user, 'username', None), # Usa getattr com default None caso username não exista
                        "first_name": getattr(message.from_user, 'first_name', None),
                        "last_name": getattr(message.from_user, 'last_name', None)
                    },
                    "message_id": message.message_id # Adiciona o message_id
                    # Adicionar outros campos importantes se necessário
                }

                # TODO: Buscar histórico de chat relevante do DB usando db_manager (opcional para o handler básico)
                # Por enquanto, passa uma lista vazia como placeholder
                chat_history: List[Dict[str, str]] = [] # Placeholder

                try:
                    # Chama a função handler_func (message_handler.handle_message)
                    response_text = handler_func(message_dict, chat_history)

                    # Se o handler_func retornou uma string (e não None), envia a resposta
                    if response_text is not None:
                        logger.debug(f"Wrapper sending response to chat {chat_id}: {response_text[:50]}...")
                        # Usa context.bot para enviar a mensagem, é mais robusto dentro de handlers
                        # Usa parse_mode='HTML' por padrão se a resposta não for None (pode ser alterado)
                        try:
                            context.bot.send_message(chat_id=chat_id, text=response_text, parse_mode='HTML') # Default para HTML
                            logger.debug(f"Response sent successfully to chat {chat_id}.")
                        except Exception as e:
                             # Captura erros ao tentar enviar a mensagem de resposta
                             logger.error(f"❌ Failed to send response message to chat {chat_id}: {e}", exc_info=True)
                             # Tenta enviar uma mensagem de erro genérica se a original falhou
                             try:
                                 context.bot.send_message(chat_id=chat_id, text="Sorry, could not send the full response.", parse_mode=None)
                             except Exception as e_fallback:
                                 logger.error(f"❌ Failed to send fallback error message to chat {chat_id}: {e_fallback}", exc_info=True)


                    else:
                        # Se handler_func retornou None, assume que a resposta já foi enviada diretamente
                        logger.debug(f"Handler returned None. Assuming response was sent directly by message handler for chat {chat_id}.")

                except Exception as e:
                    # Captura exceções que ocorrem DENTRO do handler_func (message_handler.handle_message)
                    logger.error(f"❌ Error processing message with handler_func: {e}", exc_info=True)
                    # Envia uma mensagem de erro genérica para o usuário
                    try:
                        context.bot.send_message(chat_id=chat_id, text="Sorry, an internal error occurred while processing your message.", parse_mode=None)
                    except Exception as e_fallback:
                         logger.error(f"❌ Failed to send error message to chat {chat_id} after handler failure: {e_fallback}", exc_info=True)

            # Ignora outros tipos de updates (não text messages)
            # else:
            #     logger.debug("Received non-text update, ignoring.")


        # Registra o wrapper_handler para lidar com mensagens de texto
        # MessageHandler usa Filters.text para filtrar apenas mensagens de texto
        # O objeto MessageHandler do python-telegram-bot chama a callback function (wrapper_handler)
        text_message_handler = MessageHandler(Filters.text & ~Filters.command, wrapper_handler) # Lida com texto que NÃO é comando
        command_handler = MessageHandler(Filters.command, wrapper_handler) # Lida com comandos (mensagens que começam com /)

        # Adiciona os handlers ao dispatcher
        # A ordem importa: comandos antes de texto geral, se houver sobreposição.
        # Nosso wrapper já lida com comandos vs texto, então Filters.command
        # garante que só mensagens / chegam ao nosso wrapper com Filters.command=True
        # e o resto com Filters.text.
        # A ordem de registro no dispatcher determina qual handler é tentado primeiro.
        # Vamos registrar o handler geral de texto/comandos primeiro, pois nosso wrapper
        # já contém a lógica de roteamento baseada em text.startswith('/').
        self.dispatcher.add_handler(MessageHandler(Filters.text, wrapper_handler)) # Registra o wrapper para TODAS as mensagens de texto


        logger.debug("✅ Main message handler registered: wrapper_handler with filter filters.Filters.text")


        # Inicia o polling. O idle() faz o bot ficar rodando até ser interrompido (ex: CTRL+C)
        # run_polling já inicia o thread e bloqueia.
        self.updater.start_polling()
        # Opcional: self.updater.idle() # Mantém o bot rodando

    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None:
        """
        Envia uma mensagem para um chat específico.
        :param chat_id: O ID do chat de destino (string).
        :param text: O texto da mensagem a ser enviado.
        :param parse_mode: O modo de parse (ex: 'HTML', 'MarkdownV2', None). Padrão 'HTML'.
        """
        if self.updater is None or self.updater.bot is None:
            logger.error("Telegram bot is not initialized. Cannot send message.")
            return # Não pode enviar se o bot não está pronto

        try:
            logger.debug(f"Attempting to send message to chat {chat_id}: {text[:50]}...")
            self.updater.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            logger.debug(f"Message sent successfully to chat {chat_id}.")
        except Exception as e:
            # Loga o erro ao enviar a mensagem
            logger.error(f"❌ Failed to send message to chat {chat_id}: {e}", exc_info=True)
            # Note: Não tentamos enviar uma mensagem de erro de fallback aqui para evitar loops de erro.

    # TODO: Adicionar outros métodos úteis, como send_photo, send_document, etc.
    # TODO: Implementar métodos stop_polling() ou is_running() se necessário para o main loop.