import logging
from typing import Dict, Any, Optional, List, Callable, Tuple, Union # Importa Union
import re # Importa o módulo re para usar expressões regulares
import os # Importa o módulo os para acessar variáveis de ambiente
import time # Importa time para usar sleep
# CORRIGIDO: Importa datetime para usar na anotação de tipo
from datetime import datetime


# Importar as classes dependentes para type hinting
# from database_manager import DatabaseManager # Não precisamos importar a classe real aqui para type hinting
# from telegram_client import TelegramClient   # Não precisamos importar a classe real aqui para type hinting
# from coingecko_client import CoinGeckoClient # Não precisamos importar a classe real aqui para type hinting

# Adiciona classes dummy para type hinting, conforme a estrutura esperada
class DatabaseManager:
    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None): pass
    def log_message(self, telegram_id: str, role: str, content: str, chat_id: str, message_telegram_id: Optional[int] = None) -> None: pass
    def add_or_update_preference(self, telegram_id: str, symbol: str, is_favorite: Optional[bool] = None, high_alert: Optional[float] = None, low_alert: Optional[float] = None): pass
    def get_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, is_favorite: Optional[bool] = None, with_alerts: bool = False) -> List[Any]: pass
    def clear_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, clear_favorites: bool = True, clear_alerts: bool = True) -> bool: pass
    def get_all_user_preferences_for_monitoring(self) -> List[Any]: pass # Método usado pelo PriceMonitor
    # CORRIGIDO: datetime agora está importado, então a anotação de tipo funciona
    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool: pass
    # Adiciona type hint para o novo método
    def get_all_user_telegram_ids(self) -> List[str]: pass


class TelegramClient:
    # Note: send_message na classe dummy não precisa ser idêntico ao real
    # A implementação real está em telegram_client.py e lida com parse_mode
    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None: pass

class PriceClientInterface:
    def is_ready(self) -> bool: pass
    def is_valid_symbol(self, symbol: str) -> bool: pass
    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]: pass
    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]: pass
    # Adiciona type hint para o novo método
    def get_coins_list_with_price(self, vs_currency: str = 'usd', order: str = 'market_cap_desc', per_page: int = 100, page: int = 1) -> Optional[List[Dict[str, Any]]]: pass


logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class MessageHandler:
    # Ajustado type hints para usar as classes dummy definidas acima
    def __init__(self, db_manager: DatabaseManager, price_client: PriceClientInterface, telegram_client: TelegramClient):
        """
        Inicializa o MessageHandler com as dependências.
        :param db_manager: Instância do DatabaseManager.
        :param price_client: Instância do PriceClient (ex: CoinGeckoClient).
        :param telegram_client: Instância do TelegramClient.
        """
        if db_manager is None or price_client is None or telegram_client is None:
             logger.critical("❌ MessageHandler requires valid instances of DatabaseManager, PriceClient, and TelegramClient.")
             raise ValueError("Missing critical dependencies for MessageHandler")

        # Guarda as instâncias REAIS passadas de main.py
        self.db_manager: DatabaseManager = db_manager
        self.price_client: PriceClientInterface = price_client
        self.telegram_client: TelegramClient = telegram_client

        # Obter o ID do administrador do Telegram das variáveis de ambiente
        # Usaremos este ID para verificar quem pode enviar broadcasts
        self.admin_telegram_id = os.getenv('TELEGRAM_ADMIN_ID')
        if not self.admin_telegram_id:
             logger.warning("⚠️ TELEGRAM_ADMIN_ID environment variable not set. Broadcast command will be disabled.")
        else:
             logger.info(f"Admin Telegram ID set: {self.admin_telegram_id}")


        # Mapeamento de comandos e seus aliases para os métodos de tratamento
        # Chave: comando interno, Valor: (função de tratamento, [aliases])
        self.commands: Dict[str, Tuple[Callable, List[str]]] = {
            "start": (self.handle_start, ["iniciar", "começar"]),
            "help": (self.handle_help, ["ajuda", "comandos"]),
            "price": (self.handle_price, ["preço", "cotacao"]),
            "favorite": (self.handle_favorite, ["favoritar", "fav"]), # Novo comando para favoritar
            "unfavorite": (self.handle_unfavorite, ["desfavoritar", "unfav"]), # Novo comando para desfavoritar
            "myfavorites": (self.handle_my_favorites, ["meusfavoritos", "favs"]), # Novo comando para listar favoritos
            "alert": (self.handle_alert, ["alerta"]), # Comando para definir alerta de preço
            "myalerts": (self.handle_my_alerts, ["meusalertas"]), # Comando para listar alertas
            "clearalerts": (self.handle_clear_alerts, ["limparalertas"]), # Comando para limpar alertas
            # --- NOVO COMANDO: Listar moedas ---
            "listcoins": (self.handle_list_coins, ["listar", "topmoedas", "moedas"]), # Comando para listar moedas
            # --- NOVO COMANDO: Broadcast (apenas para admin) ---
            "broadcast": (self.handle_broadcast, ["transmitir", "enviartodos"]), # Comando para broadcast
        }

        # Mapeamento reverso de aliases para comandos internos (para roteamento rápido)
        self._alias_to_command: Dict[str, str] = {}
        for command, (_, aliases) in self.commands.items():
            # Adiciona o comando interno como um alias de si mesmo
            self._alias_to_command[command.lower()] = command
            for alias in aliases:
                self._alias_to_command[alias.lower()] = command


    def handle_message(self, update: Any, context: Any) -> None: # Assinatura do handler na v20+
        """
        Processa uma mensagem recebida do Telegram (v20+).
        Identifica comandos, registra a mensagem e roteia para o handler apropriado.
        Não retorna string, handlers enviam respostas diretamente.
        """
        # Na v20+, update e context são passados diretamente para o handler
        message = update.effective_message
        if not message:
            logger.warning("Received update without an effective message.")
            return # Ignora updates sem mensagem efetiva

        message_text = message.text
        user_id = str(message.from_user.id) # Garante que user_id é string
        chat_id = str(message.chat_id)     # Garante que chat_id é string
        message_telegram_id = message.message_id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name


        logger.debug(f"handle_message received - message_text: '{message_text}' (Type: {type(message_text)}) from user {user_id} in chat {chat_id}")

        if not message_text:
            logger.warning("Received message with empty text. Ignoring.")
            return None # Ignora mensagens sem texto

        # Loga a mensagem recebida no banco de dados (opcional, dependendo da implementação de log)
        # Garante que o usuário existe antes de tentar logar a mensagem
        try:
             # get_or_create_user agora lida com a sessão internamente
             user = self.db_manager.get_or_create_user(telegram_id=user_id, username=username, first_name=first_name, last_name=last_name)
             if user:
                  # TODO: Implementar log_message para salvar no DB se a tabela existir
                  # self.db_manager.log_message(user_id, "user", message_text, chat_id, message_telegram_id)
                  logger.debug(f"Logged user message for user {user_id} in chat {chat_id}.")
             else:
                  logger.error(f"Could not get or create user {user_id}. Cannot log message.")

        except Exception as e:
             logger.error(f"Error during user get/create or message logging for user {user_id}: {e}", exc_info=True)
             # Continua processando a mensagem mesmo que o log falhe


        # Verifica se a mensagem é um comando (começa com '/')
        logger.debug(f"handle_message received - message_text starts with '/': {message_text.startswith('/')}")
        if message_text.startswith('/'):
            # Remove a barra inicial e divide o comando e argumentos
            parts = message_text[1:].split(maxsplit=1)
            command_alias = parts[0].lower() # Comando/alias em minúsculas
            command_args = parts[1] if len(parts) > 1 else "" # Argumentos como uma única string

            logger.info(f"Received command alias: /{command_alias} with args: '{command_args}' from user {user_id} in chat {chat_id}")

            # Roteia o comando para a função apropriada
            # Passa update e context para os handlers na v20+
            self.route_command(command_alias, command_args, user_id, chat_id, update, context) # Passa update e context

        else:
            # Mensagem não é um comando, pode ser tratada como texto livre (se necessário)
            # Por enquanto, apenas ignora ou responde com mensagem padrão
            logger.info(f"Received non-command message from user {user_id} in chat {chat_id}. Ignoring text: '{message_text}'")
            # Não retorna resposta para texto livre por padrão
            # self.telegram_client.send_message(chat_id, "Desculpe, eu só respondo a comandos que começam com '/'. Digite /ajuda para ver a lista de comandos.")
            pass # Não envia resposta para texto livre


    def route_command(self, command_alias: str, command_args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None: # Assinatura do router na v20+
        """
        Roteia um alias de comando para a função de tratamento interna correspondente (v20+).
        Handlers enviam respostas diretamente.
        """
        logger.debug(f"Normalized command alias '{command_alias}' to '{self._alias_to_command.get(command_alias, command_alias)}'.")
        internal_command = self._alias_to_command.get(command_alias, command_alias) # Busca o comando interno pelo alias

        handler_tuple = self.commands.get(internal_command)

        logger.debug(f"Route: {internal_command}")

        if handler_tuple:
            handler_func, _ = handler_tuple
            try:
                # Executa a função de tratamento do comando
                # Passa args, user_id, chat_id, update, context para os handlers na v20+
                # CORRIGIDO: Passando update e context para os handlers
                handler_func(command_args, user_id, chat_id, update, context)

                logger.debug(f"Route: {internal_command} -> Handler executed successfully.")

            except Exception as e:
                logger.error(f"❌ Error processing command /{command_alias} with args '{command_args}' for user {user_id} in chat {chat_id}: {e}", exc_info=True)
                # Em caso de erro no handler, envia uma mensagem de erro para o usuário
                # Usa a instância do telegram_client para enviar a mensagem
                self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro interno ao executar este comando.")

        else:
            # Comando não reconhecido
            logger.warning(f"Unknown command alias received: /{command_alias} from user {user_id} in chat {chat_id}.")
            # Usa a instância do telegram_client para enviar a mensagem
            self.telegram_client.send_message(chat_id, f"Comando não reconhecido: /{command_alias}. Digite /ajuda para ver os comandos disponíveis.")

    # --- Função auxiliar para escapar caracteres MarkdownV2 ---
    def escape_markdownv2_response(self, text: Union[str, float, int]) -> str:
        """Escapa caracteres especiais para MarkdownV2 em strings de resposta."""
        text_str = str(text)
        # Caracteres especiais em MarkdownV2 que precisam ser escapados na resposta
        # Nota: A lista de caracteres pode variar ligeiramente dependendo de onde são usados.
        # Para texto geral de resposta, focamos nos mais comuns que podem quebrar a formatação.
        # Evitamos escapar * e _ se quisermos usá-los para negrito/itálico na resposta.
        # Escapamos: [, ], (, ), ~, `, > , #, +, -, =, |, {, }, ., !
        special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
        return re.sub(special_chars, r'\\\1', text_str)


    # --- Handlers de Comandos (Assinatura atualizada para v20+) ---
    # Todos os handlers agora recebem args: str, user_id: str, chat_id: str, update: Any, context: Any
    # E não retornam string, enviam a resposta via self.telegram_client.send_message

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_start(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /start."""
        welcome_message = "Olá! Eu sou o MarianaCryptoBot, seu assistente para acompanhar o mercado de criptomoedas.\n"
        welcome_message += "Use os comandos para ver preços, definir alertas e mais.\n"
        welcome_message += "Digite /ajuda para ver a lista de comandos."
        self.telegram_client.send_message(chat_id, welcome_message)
        # Handlers na v20+ não precisam retornar nada se enviam a resposta diretamente

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_help(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /help."""
        help_message = "Comandos disponíveis:\n"
        help_message += "/preço [símbolo] - Mostra o preço atual de uma criptomoeda (ex: /preço btc)\n"
        help_message += "/alerta [símbolo] [alta/baixa] [preço] - Define um alerta de preço (ex: /alerta eth alta 2000)\n"
        help_message += "/meusalertas - Lista seus alertas configurados\n"
        help_message += "/limparalertas [símbolo] (opcional) - Limpa seus alertas (todos ou para um símbolo)\n"
        help_message += "/favoritar [símbolo] - Marca uma moeda como favorita (ex: /favoritar xrp)\n" # Ajuda para novo comando
        help_message += "/desfavoritar [símbolo] - Desmarca uma moeda como favorita (ex: /desfavoritar xrp)\n" # Ajuda para novo comando
        help_message += "/meusfavoritos - Lista suas moedas favoritas\n" # Ajuda para novo comando
        help_message += "/listar [moeda_base] [quantidade] - Lista as principais moedas por capitalização (ex: /listar usd 10)\n" # Ajuda para novo comando /listar
        # --- Ajuda para o novo comando /broadcast ---
        help_message += "/broadcast [mensagem] - Envia uma mensagem para todos os usuários (apenas para admin)\n"
        # --- Fim Ajuda /broadcast ---
        help_message += "/ajuda - Mostra esta mensagem"
        self.telegram_client.send_message(chat_id, help_message)
        # Este handler envia a resposta diretamente, então retorna None

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_price(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /price."""
        symbols = [s.strip() for s in args.split(',') if s.strip()]
        if not symbols:
            self.telegram_client.send_message(chat_id, "Por favor, especifique o símbolo da criptomoeda (ex: /preço btc) ou múltiplos símbolos separados por vírgula (ex: /preço btc,eth).")
            return

        if len(symbols) > 5:
             self.telegram_client.send_message(chat_id, "Por favor, especifique no máximo 5 símbolos por vez.")
             return


        logger.debug(f"Fetching price for symbols: {symbols} for user {user_id}")
        prices_data = self.price_client.get_multiple_prices(symbols, currency=['usd', 'brl'])

        response_lines = ["📊 **Preços Atuais:**"]

        found_price = False

        # Escapa caracteres especiais para MarkdownV2 na resposta - Função local para este handler
        def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
            text_str = str(text)
            special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
            return re.sub(special_chars, r'\\\1', text_str)


        for symbol in symbols:
            price_data = prices_data.get(symbol.upper())
            if price_data:
                found_price = True
                price_usd = price_data.get('price_usd')
                price_brl = price_data.get('price_brl')
                change_usd = price_data.get('price_change_percent_usd')

                symbol_escaped = escape_markdownv2_response_local(symbol.upper())
                price_usd_escaped = escape_markdownv2_response_local(f"{price_usd:,.2f}" if price_usd is not None else "N/A")
                price_brl_escaped = escape_markdownv2_response_local(f"{price_brl:,.2f}" if price_brl is not None else "N/A")

                line = f"- **{symbol_escaped}**: \\${price_usd_escaped}"
                if price_brl is not None:
                    line += f" \(R\\${price_brl_escaped}\)"

                if change_usd is not None:
                    change_str = f"{change_usd:+.2f}%"
                    if change_usd >= 0:
                         line += f" \(24h: {escape_markdownv2_response_local(change_str)} 🟢\\)"
                    else:
                         line += f" \(24h: {escape_markdownv2_response_local(change_str)} 🔴\\)"
                else:
                    line += " \(24h: N/A\\)"

                response_lines.append(line)

        if not found_price:
            response_lines.append("Nenhum preço encontrado para os símbolos especificados.")

        response_text = "\n".join(response_lines)

        self.telegram_client.send_message(chat_id, response_text, parse_mode='MarkdownV2')

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_favorite(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /favoritar."""
        symbols = [s.strip() for s in args.split(',') if s.strip()]
        if not symbols:
            self.telegram_client.send_message(chat_id, "Por favor, especifique o símbolo da criptomoeda para favoritar (ex: /favoritar btc).")
            return

        if len(symbols) > 5:
             self.telegram_client.send_message(chat_id, "Por favor, especifique no máximo 5 símbolos para favoritar por vez.")
             return

        results = []
        for symbol in symbols:
             if not self.price_client.is_valid_symbol(symbol):
                  results.append(f"❌ Símbolo '{symbol.upper()}' não reconhecido.")
                  continue

             try:
                  preference = self.db_manager.add_or_update_preference(str(user_id), symbol.upper(), is_favorite=True)
                  if preference:
                       results.append(f"⭐ '{symbol.upper()}' adicionado aos seus favoritos.")
                  else:
                       results.append(f"❌ Erro ao favoritar '{symbol.upper()}'.")
             except Exception as e:
                  logger.error(f"Error favoriting symbol {symbol.upper()} for user {user_id}: {e}", exc_info=True)
                  results.append(f"❌ Erro interno ao favoritar '{symbol.upper()}'.")

        self.telegram_client.send_message(chat_id, "\n".join(results))

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_unfavorite(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /desfavoritar."""
        symbols = [s.strip() for s in args.split(',') if s.strip()]
        if not symbols:
            self.telegram_client.send_message(chat_id, "Por favor, especifique o símbolo da criptomoeda para desfavoritar (ex: /desfavoritar btc).")
            return

        if len(symbols) > 5:
             self.telegram_client.send_message(chat_id, "Por favor, especifique no máximo 5 símbolos para desfavoritar por vez.")
             return

        results = []
        for symbol in symbols:
             try:
                  cleared = self.db_manager.clear_user_crypto_preferences(str(user_id), symbol.upper(), clear_favorites=True, clear_alerts=False)
                  if cleared:
                       results.append(f"💔 '{symbol.upper()}' removido dos seus favoritos.")
                  else:
                       results.append(f"ℹ️ '{symbol.upper()}' não estava nos seus favoritos.")
             except Exception as e:
                  logger.error(f"Error unfavoriting symbol {symbol.upper()} for user {user_id}: {e}", exc_info=True)
                  results.append(f"❌ Erro interno ao desfavoritar '{symbol.upper()}'.")

        self.telegram_client.send_message(chat_id, "\n".join(results))

    # CORRIGIDO: Assinatura do handler atualizada
    def handle_my_favorites(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /meusfavoritos."""
        try:
            favorite_preferences = self.db_manager.get_user_crypto_preferences(str(user_id), is_favorite=True)

            if not favorite_preferences:
                self.telegram_client.send_message(chat_id, "Você ainda não favoritou nenhuma moeda. Use /favoritar [símbolo] para adicionar.")
                return

            favorite_symbols = [pref.symbol for pref in favorite_preferences]

            prices_data = self.price_client.get_multiple_prices(favorite_symbols, currency=['usd', 'brl'])

            response_lines = ["⭐ **Suas moedas favoritas:**"]

            # Escapa caracteres especiais para MarkdownV2 na resposta - Função local para este handler
            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
                return re.sub(special_chars, r'\\\1', text_str)


            for symbol in favorite_symbols:
                 price_data = prices_data.get(symbol.upper())
                 if price_data:
                      price_usd = price_data.get('price_usd')
                      price_brl = price_data.get('price_brl')
                      change_usd = price_data.get('price_change_percent_usd')

                      symbol_escaped = escape_markdownv2_response_local(symbol.upper())
                      price_usd_escaped = escape_markdownv2_response_local(f"{price_usd:,.2f}" if price_usd is not None else "N/A")
                      price_brl_escaped = escape_markdownv2_response_local(f"{price_brl:,.2f}" if price_brl is not None else "N/A")

                      line = f"- **{symbol_escaped}**: \\${price_usd_escaped}"
                      if price_brl is not None:
                           line += f" \(R\\${price_brl_escaped}\)"

                      if change_usd is not None:
                           change_str = f"{change_usd:+.2f}%"
                           if change_usd >= 0:
                                line += f" \(24h: {escape_markdownv2_response_local(change_str)} 🟢\\)"
                           else:
                                line += f" \(24h: {escape_markdownv2_response_local(change_str)} 🔴\\)"
                      else:
                           line += " \(24h: N/A\\)"

                      response_lines.append(line)
                 else:
                      response_lines.append(f"- **{escape_markdownv2_response_local(symbol.upper())}**: Preço não disponível")


            response_text = "\n".join(response_lines)
            self.telegram_client.send_message(chat_id, response_text, parse_mode='MarkdownV2')

        except Exception as e:
            logger.error(f"Error listing favorites for user {user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro ao listar seus favoritos.")


    # CORRIGIDO: Assinatura do handler atualizada
    def handle_alert(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /alerta."""
        parts = args.split()
        if len(parts) != 3:
            self.telegram_client.send_message(chat_id, "Uso correto: /alerta [símbolo] [alta/baixa] [preço] (ex: /alerta eth alta 2000)")
            return

        symbol = parts[0].upper()
        alert_type = parts[1].lower()
        price_str = parts[2]

        if alert_type not in ['alta', 'baixa']:
            self.telegram_client.send_message(chat_id, "Tipo de alerta inválido. Use 'alta' ou 'baixa'.")
            return

        try:
            price = float(price_str)
            if price <= 0:
                 self.telegram_client.send_message(chat_id, "O preço do alerta deve ser um número positivo.")
                 return
        except ValueError:
            self.telegram_client.send_message(chat_id, "Preço inválido. Por favor, insira um número válido.")
            return

        if not self.price_client.is_valid_symbol(symbol):
             self.telegram_client.send_message(chat_id, f"Símbolo '{symbol}' não reconhecido. Por favor, use um símbolo válido (ex: BTC, ETH).")
             return


        try:
            high_alert = price if alert_type == 'alta' else None
            low_alert = price if alert_type == 'baixa' else None

            preference = self.db_manager.add_or_update_preference(str(user_id), symbol, high_alert=high_alert, low_alert=low_alert)

            if preference:
                alert_set_message = f"🔔 Alerta de {alert_type} para {symbol.upper()} definido em ${price:,.2f}."
                self.telegram_client.send_message(chat_id, alert_set_message)
            else:
                self.telegram_client.send_message(chat_id, f"❌ Erro ao definir alerta para {symbol.upper()}.")

        except Exception as e:
            logger.error(f"Error setting alert for user {user_id}, symbol {symbol}, type {alert_type}, price {price}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro interno ao definir o alerta.")


    # CORRIGIDO: Assinatura do handler atualizada
    def handle_my_alerts(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /meusalertas."""
        try:
            alert_preferences = self.db_manager.get_user_crypto_preferences(str(user_id), with_alerts=True)

            if not alert_preferences:
                self.telegram_client.send_message(chat_id, "Você ainda não configurou nenhum alerta de preço. Use /alerta [símbolo] [alta/baixa] [preço] para adicionar.")
                return

            response_lines = ["🔔 **Seus alertas de preço configurados:**"]

            # Escapa caracteres especiais para MarkdownV2 na resposta - Função local para este handler
            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
                return re.sub(special_chars, r'\\\1', text_str)


            for pref in alert_preferences:
                symbol_escaped = escape_markdownv2_response_local(pref.symbol)
                line_parts = [f"- **{symbol_escaped}**"]

                if pref.high_alert is not None:
                     high_price_escaped = escape_markdownv2_response_local(f"{pref.high_alert:,.2f}")
                     line_parts.append(f"Alta > \\${high_price_escaped}")

                if pref.low_alert is not None:
                     low_price_escaped = escape_markdownv2_response_local(f"{pref.low_alert:,.2f}")
                     line_parts.append(f"Baixa < \\${low_price_escaped}")

                response_lines.append(": ".join(line_parts))


            response_text = "\n".join(response_lines)
            self.telegram_client.send_message(chat_id, response_text, parse_mode='MarkdownV2')

        except Exception as e:
            logger.error(f"Error listing alerts for user {user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro ao listar seus alertas.")


    # CORRIGIDO: Assinatura do handler atualizada
    def handle_clear_alerts(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /limparalertas."""
        symbol_to_clear = args.strip().upper() if args.strip() else None

        if symbol_to_clear and not self.price_client.is_valid_symbol(symbol_to_clear):
             self.telegram_client.send_message(chat_id, f"Símbolo '{symbol_to_clear}' não reconhecido. Por favor, use um símbolo válido ou nenhum para limpar todos os alertas.")
             return


        try:
            cleared = self.db_manager.clear_user_crypto_preferences(str(user_id), symbol_to_clear, clear_favorites=False, clear_alerts=True)

            if cleared:
                if symbol_to_clear:
                    self.telegram_client.send_message(chat_id, f"🔔 Alertas para {symbol_to_clear} foram removidos.")
                else:
                    self.telegram_client.send_message(chat_id, "🔔 Todos os seus alertas de preço foram removidos.")
            else:
                if symbol_to_clear:
                     self.telegram_client.send_message(chat_id, f"Nenhum alerta encontrado para {symbol_to_clear}.")
                else:
                     self.telegram_client.send_message(chat_id, "Você não tem alertas de preço configurados.")

        except Exception as e:
            logger.error(f"Error clearing alerts for user {user_id}, symbol {symbol_to_clear}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro interno ao limpar os alertas.")

    # --- NOVO HANDLER DE COMANDO: Listar Moedas ---
    # CORRIGIDO: Assinatura do handler atualizada
    def handle_list_coins(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /listar.
        Espera argumentos opcionais: [moeda_base] [quantidade]
        Ex: /listar usd 10, /listar brl 20, /listar 50 (usa usd padrão)
        """
        parts = args.split()
        vs_currency = 'usd' # Moeda base padrão
        per_page = 10 # Quantidade padrão

        if len(parts) == 1:
             # Se um argumento foi fornecido, pode ser a quantidade ou a moeda
             try:
                  per_page = int(parts[0])
                  if per_page <= 0 or per_page > 250: # Limite da API
                       self.telegram_client.send_message(chat_id, "Quantidade inválida. Por favor, especifique um número entre 1 e 250.")
                       return
             except ValueError:
                  # Se não é um número, assume que é a moeda
                  vs_currency = parts[0].lower()
                  # Poderíamos adicionar uma verificação de moeda válida aqui se tivéssemos uma lista

        elif len(parts) == 2:
             # Se dois argumentos foram fornecidos, o primeiro é a moeda e o segundo é a quantidade
             vs_currency = parts[0].lower()
             try:
                  per_page = int(parts[1])
                  if per_page <= 0 or per_page > 250: # Limite da API
                       self.telegram_client.send_message(chat_id, "Quantidade inválida. Por favor, especifique um número entre 1 e 250.")
                       return
             except ValueError:
                  self.telegram_client.send_message(chat_id, "Quantidade inválida. Por favor, insira um número válido.")
                  return

        elif len(parts) > 2:
             self.telegram_client.send_message(chat_id, "Uso correto: /listar [moeda_base] [quantidade] (ex: /listar usd 10 ou /listar 20)")
             return

        logger.debug(f"Fetching list of coins for user {user_id} in {vs_currency}, {per_page} per page.")

        try:
            # Chama o novo método do price_client
            coins_list = self.price_client.get_coins_list_with_price(vs_currency=vs_currency, per_page=per_page)

            if not coins_list:
                self.telegram_client.send_message(chat_id, f"❌ Não foi possível obter a lista de moedas em {vs_currency.upper()}. Por favor, tente novamente mais tarde.")
                return

            response_lines = [f"🏆 **Top {len(coins_list)} moedas por Capitalização de Mercado em {vs_currency.upper()}:**"] # Título MarkdownV2

            # Escapa caracteres especiais para MarkdownV2 na resposta - Função local para este handler
            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
                return re.sub(special_chars, r'\\\1', text_str)


            for coin in coins_list:
                # Acessa os dados da moeda. Alguns campos podem ser None.
                rank = coin.get('market_cap_rank', 'N/A')
                symbol = coin.get('symbol', 'N/A').upper()
                name = coin.get('name', 'N/A')
                price = coin.get('current_price') # Pode ser None
                change_24h = coin.get('price_change_percentage_24h') # Pode ser None

                # Formata o preço e a variação
                price_formatted = f"{price:,.2f}" if price is not None else "N/A"
                change_formatted = f"{change_24h:+.2f}%" if change_24h is not None else "N/A"

                # Adiciona emoji para variação
                if change_24h is not None:
                     if change_24h >= 0:
                          change_formatted += " 🟢"
                     else:
                          change_formatted += " 🔴"

                # Escapa os valores para MarkdownV2
                rank_escaped = escape_markdownv2_response_local(rank)
                symbol_escaped = escape_markdownv2_response_local(symbol)
                name_escaped = escape_markdownv2_response_local(name)
                price_escaped = escape_markdownv2_response_local(price_formatted)
                change_escaped = escape_markdownv2_response_local(change_formatted)


                # Monta a linha da lista
                # Ex: 1\. **BTC** \(Bitcoin\): \$96,000\.00 \(24h: \+2\.50\% 🟢\)
                line = f"{rank_escaped}\\. **{symbol_escaped}** \({name_escaped}\): \\${price_escaped} \(24h: {change_escaped}\)" # Escapa . ( ) $

                response_lines.append(line)

            response_text = "\n".join(response_lines)

            # Envia a mensagem com MarkdownV2
            self.telegram_client.send_message(chat_id, response_text, parse_mode='MarkdownV2')

        except Exception as e:
            logger.error(f"Error handling /listcoins for user {user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro ao listar as moedas.")

        return

    # --- NOVO HANDLER DE COMANDO: Broadcast ---
    # CORRIGIDO: Assinatura do handler atualizada
    def handle_broadcast(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /broadcast.
        Envia a mensagem fornecida nos argumentos para todos os usuários registrados.
        Apenas o usuário com o ID definido em TELEGRAM_ADMIN_ID pode usar este comando.
        """
        # 1. Verificar se o remetente é o administrador
        if self.admin_telegram_id is None or str(user_id) != str(self.admin_telegram_id):
            logger.warning(f"Unauthorized attempt to use broadcast command by user {user_id} in chat {chat_id}.")
            self.telegram_client.send_message(chat_id, "❌ Comando de broadcast restrito ao administrador.")
            return # Sai da função se não for admin

        # 2. Obter a mensagem a ser transmitida dos argumentos
        broadcast_message = args.strip()
        if not broadcast_message:
            self.telegram_client.send_message(chat_id, "Por favor, forneça a mensagem a ser transmitida (ex: /broadcast Olá a todos!).")
            return # Sai se não houver mensagem

        logger.info(f"Admin user {user_id} is initiating broadcast message: '{broadcast_message[:100]}...'")

        # 3. Obter a lista de todos os IDs de usuário do banco de dados
        try:
            # Usa o novo método do DatabaseManager
            all_user_ids = self.db_manager.get_all_user_telegram_ids()
            logger.debug(f"Attempting to broadcast to {len(all_user_ids)} users.")
        except Exception as e:
            logger.error(f"Error getting all user IDs for broadcast: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "❌ Erro ao obter a lista de usuários para broadcast.")
            return # Sai se falhar ao obter usuários

        if not all_user_ids:
            self.telegram_client.send_message(chat_id, "ℹ️ Não há usuários registrados no banco de dados para enviar o broadcast.")
            return # Sai se não houver usuários

        # 4. Enviar a mensagem para cada usuário
        sent_count = 0
        failed_count = 0
        failed_users = []

        # Usando MarkdownV2 para a mensagem de broadcast
        # Escapa a mensagem de broadcast para MarkdownV2
        # Função local para este handler
        def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
            text_str = str(text)
            special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])' # Removido * e _
            return re.sub(special_chars, r'\\\1', text_str)

        broadcast_message_escaped = escape_markdownv2_response_local(broadcast_message)


        for target_user_id in all_user_ids:
            # Não envia a mensagem de broadcast de volta para o próprio admin no chat de comando
            # (A menos que o admin seja o único usuário, o que é improvável em produção)
            # Mas é mais seguro enviar para todos, incluindo o admin, para confirmar o envio.
            # Se o admin usar o comando em um chat privado, ele receberá a mensagem de broadcast.
            # Se usar em um grupo, todos no grupo (incluindo ele) receberão a mensagem de broadcast.
            # A API do Telegram lida com envios para o mesmo chat_id.

            try:
                # Usa o telegram_client para enviar a mensagem
                # Envia a mensagem de broadcast escapada com MarkdownV2
                self.telegram_client.send_message(chat_id=str(target_user_id), text=broadcast_message_escaped, parse_mode='MarkdownV2')
                sent_count += 1
                logger.debug(f"Broadcast message sent to user ID: {target_user_id}")
                # Pequena pausa para não sobrecarregar a API, especialmente com muitos usuários
                time.sleep(0.1) # Pausa de 100ms
            except Exception as e:
                failed_count += 1
                failed_users.append(target_user_id)
                logger.error(f"❌ Failed to send broadcast message to user ID {target_user_id}: {e}", exc_info=True)
                # Continua para o próximo usuário mesmo que um falhe


        # 5. Informar o administrador sobre o resultado do broadcast
        result_message = f"✅ Broadcast concluído.\n"
        result_message += f"Enviado com sucesso para {sent_count} usuários.\n"
        if failed_count > 0:
            result_message += f"❌ Falha ao enviar para {failed_count} usuários (IDs: {', '.join(failed_users[:10])}{'...' if len(failed_users) > 10 else ''})."

        # Envia a mensagem de resultado de volta para o chat onde o comando foi emitido
        self.telegram_client.send_message(chat_id, result_message)
        logger.info(f"Broadcast result reported to admin in chat {chat_id}.")

    # --- Fim NOVO HANDLER DE COMANDO: Broadcast ---

