import logging
from typing import Dict, Any, Optional, List, Callable, Tuple, Union
import re
import os # Importa o módulo os para acessar variáveis de ambiente
import time
from datetime import datetime # Importa datetime para anotação de tipo

# Adiciona classes dummy para type hinting, conforme a estrutura esperada
class DatabaseManager:
    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None): pass
    def log_message(self, telegram_id: str, role: str, content: str, chat_id: str, message_telegram_id: Optional[int] = None) -> None: pass
    def add_or_update_preference(self, telegram_id: str, symbol: str, is_favorite: Optional[bool] = None, high_alert: Optional[float] = None, low_alert: Optional[float] = None): pass
    def get_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, is_favorite: Optional[bool] = None, with_alerts: bool = False) -> List[Any]: pass
    def clear_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, clear_favorites: bool = True, clear_alerts: bool = True) -> bool: pass
    def get_all_user_preferences_for_monitoring(self) -> List[Any]: pass
    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool: pass
    def get_all_user_telegram_ids(self) -> List[str]: pass
    # Mantém type hints para os métodos de admin do DB
    def is_user_admin(self, telegram_id: str) -> bool: pass
    def set_user_admin_status(self, telegram_id: str, is_admin: bool) -> bool: pass
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[Any]: pass # Adiciona um método para buscar usuário por ID

class TelegramClient:
    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None: pass
    # Adiciona type hint para get_chat_member para o comando /addadmin
    def get_chat_member(self, chat_id: Union[int, str], user_id: Union[int, str]) -> Optional[Any]: pass # Retorna objeto ChatMember ou None

class PriceClientInterface:
    def is_ready(self) -> bool: pass
    def is_valid_symbol(self, symbol: str) -> bool: pass
    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]: pass
    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]: pass
    def get_coins_list_with_price(self, vs_currency: str = 'usd', order: str = 'market_cap_desc', per_page: int = 100, page: int = 1) -> Optional[List[Dict[str, Any]]]: pass


logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db_manager: DatabaseManager, price_client: PriceClientInterface, telegram_client: TelegramClient):
        if db_manager is None or price_client is None or telegram_client is None:
             logger.critical("❌ MessageHandler requires valid instances of DatabaseManager, PriceClient, and TelegramClient.")
             raise ValueError("Missing critical dependencies for MessageHandler")

        self.db_manager: DatabaseManager = db_manager
        self.price_client: PriceClientInterface = price_client
        self.telegram_client: TelegramClient = telegram_client

        # REINTRODUZIDO: Obter o ID do administrador principal da variável de ambiente
        self.primary_admin_telegram_id = os.getenv('TELEGRAM_ADMIN_ID')
        if not self.primary_admin_telegram_id:
             logger.warning("⚠️ TELEGRAM_ADMIN_ID environment variable not set. Primary admin functionality via env var will be disabled.")
        else:
             logger.info(f"Primary Admin Telegram ID from env var: {self.primary_admin_telegram_id}")


        self.commands: Dict[str, Tuple[Callable, List[str]]] = {
            "start": (self.handle_start, ["iniciar", "começar"]),
            "help": (self.handle_help, ["ajuda", "comandos"]),
            "price": (self.handle_price, ["preço", "cotacao"]),
            "favorite": (self.handle_favorite, ["favoritar", "fav"]),
            "unfavorite": (self.handle_unfavorite, ["desfavoritar", "unfav"]),
            "myfavorites": (self.handle_my_favorites, ["meusfavoritos", "favs"]),
            "alert": (self.handle_alert, ["alerta"]),
            "myalerts": (self.handle_my_alerts, ["meusalertas"]),
            "clearalerts": (self.handle_clear_alerts, ["limparalertas"]),
            "listcoins": (self.handle_list_coins, ["listar", "topmoedas", "moedas"]),
            "broadcast": (self.handle_broadcast, ["transmitir", "enviartodos"]),
            # Comandos de Admin
            "addadmin": (self.handle_add_admin, ["promoveradmin"]),
            "removeadmin": (self.handle_remove_admin, ["rebaixaradmin"]),
            "isadmin": (self.handle_is_admin, ["checaradmin"]),
        }

        self._alias_to_command: Dict[str, str] = {}
        for command, (_, aliases) in self.commands.items():
            self._alias_to_command[command.lower()] = command
            for alias in aliases:
                self._alias_to_command[alias.lower()] = command


    # NOVO MÉTODO: Lógica combinada para verificar se um usuário é administrador
    def _is_user_allowed_admin_command(self, user_id: str) -> bool:
        """
        Verifica se um usuário tem permissão para executar comandos de administração.
        Um usuário é admin se:
        1. Seu telegram_id coincide com o TELEGRAM_ADMIN_ID da variável de ambiente.
        OU
        2. Seu campo is_admin no banco de dados é True.
        """
        # Verifica a variável de ambiente primeiro
        if self.primary_admin_telegram_id and str(user_id) == str(self.primary_admin_telegram_id):
            logger.debug(f"User {user_id} is primary admin (env var).")
            return True

        # Se não for o admin primário, verifica o status no banco de dados
        try:
            is_db_admin = self.db_manager.is_user_admin(user_id)
            if is_db_admin:
                 logger.debug(f"User {user_id} is admin (DB status).")
            else:
                 logger.debug(f"User {user_id} is not admin.")
            return is_db_admin
        except Exception as e:
            logger.error(f"Error checking DB admin status for user {user_id}: {e}", exc_info=True)
            return False # Assume que não é admin em caso de erro


    def handle_message(self, update: Any, context: Any) -> None:
        message = update.effective_message
        if not message:
            logger.warning("Received update without an effective message.")
            return

        message_text = message.text
        user_id = str(message.from_user.id)
        chat_id = str(message.chat_id)
        message_telegram_id = message.message_id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name

        logger.debug(f"handle_message received - message_text: '{message_text}' (Type: {type(message_text)}) from user {user_id} in chat {chat_id}")

        if not message_text:
            logger.warning("Received message with empty text. Ignoring.")
            return None

        try:
             # Garante que o usuário existe no DB (e cria se não existir)
             # get_or_create_user agora lida com a sessão internamente
             user = self.db_manager.get_or_create_user(telegram_id=user_id, username=username, first_name=first_name, last_name=last_name)
             if user:
                  # TODO: Implementar log_message para salvar no DB se a tabela existir
                  logger.debug(f"Logged user message for user {user_id} in chat {chat_id}.")
             else:
                  logger.error(f"Could not get or create user {user_id}. Cannot log message.")

        except Exception as e:
             logger.error(f"Error during user get/create or message logging for user {user_id}: {e}", exc_info=True)
             pass


        if message_text.startswith('/'):
            parts = message_text[1:].split(maxsplit=1)
            command_alias = parts[0].lower()
            command_args = parts[1] if len(parts) > 1 else ""

            logger.info(f"Received command alias: /{command_alias} with args: '{command_args}' from user {user_id} in chat {chat_id}")

            # Passa update e context para route_command
            self.route_command(command_alias, command_args, user_id, chat_id, update, context)

        else:
            logger.info(f"Received non-command message from user {user_id} in chat {chat_id}. Ignoring text: '{message_text}'")
            pass


    # Adiciona update e context aos parâmetros
    def route_command(self, command_alias: str, command_args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        logger.debug(f"Normalized command alias '{command_alias}' to '{self._alias_to_command.get(command_alias, command_alias)}'.")
        internal_command = self._alias_to_command.get(command_alias, command_alias)

        handler_tuple = self.commands.get(internal_command)

        logger.debug(f"Route: {internal_command}")

        if handler_tuple:
            handler_func, _ = handler_tuple
            try:
                # Executa a função de tratamento do comando
                # Passa args, user_id, chat_id, update, context para os handlers
                handler_func(command_args, user_id, chat_id, update, context)

                logger.debug(f"Route: {internal_command} -> Handler executed successfully.")

            except Exception as e:
                logger.error(f"❌ Error processing command /{command_alias} with args '{command_args}' for user {user_id} in chat {chat_id}: {e}", exc_info=True)
                self.telegram_client.send_message(chat_id, "Desculpe, ocorreu um erro interno ao executar este comando.")

        else:
            logger.warning(f"Unknown command alias received: /{command_alias} from user {user_id} in chat {chat_id}.")
            self.telegram_client.send_message(chat_id, f"Comando não reconhecido: /{command_alias}. Digite /ajuda para ver os comandos disponíveis.")

    # --- Função auxiliar para escapar caracteres MarkdownV2 ---
    def escape_markdownv2_response(self, text: Union[str, float, int]) -> str:
        text_str = str(text)
        special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
        return re.sub(special_chars, r'\\\1', text_str)


    # --- Handlers de Comandos (Assinatura v20+: args, user_id, chat_id, update, context) ---

    def handle_start(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /start."""
        welcome_message = "Olá! Eu sou o MarianaCryptoBot, seu assistente para acompanhar o mercado de criptomoedas.\n"
        welcome_message += "Use os comandos para ver preços, definir alertas e mais.\n"
        welcome_message += "Digite /ajuda para ver a lista de comandos."
        self.telegram_client.send_message(chat_id, welcome_message)

    def handle_help(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /help."""
        help_message = "Comandos disponíveis:\n"
        help_message += "/preço [símbolo] - Mostra o preço atual de uma criptomoeda (ex: /preço btc)\n"
        help_message += "/alerta [símbolo] [alta/baixa] [preço] - Define um alerta de preço (ex: /alerta eth alta 2000)\n"
        help_message += "/meusalertas - Lista seus alertas configurados\n"
        help_message += "/limparalertas [símbolo] (opcional) - Limpa seus alertas (todos ou para um símbolo)\n"
        help_message += "/favoritar [símbolo] - Marca uma moeda como favorita (ex: /favoritar xrp)\n"
        help_message += "/desfavoritar [símbolo] - Desmarca uma moeda como favorita (ex: /desfavoritar xrp)\n"
        help_message += "/meusfavoritos - Lista suas moedas favoritas\n"
        help_message += "/listar [moeda_base] [quantidade] - Lista as principais moedas por capitalização (ex: /listar usd 10)\n"
        help_message += "/ajuda - Mostra esta mensagem\n"
        # Atualiza a ajuda para refletir a nova lógica de admin
        help_message += "\nComandos de Administrador (uso restrito):\n"
        help_message += "/broadcast [mensagem] - Envia uma mensagem para todos os usuários\n"
        help_message += "/addadmin [ID do usuário ou responder a mensagem] - Promove um usuário a administrador\n"
        help_message += "/removeadmin [ID do usuário ou responder a mensagem] - Rebaixa um usuário de administrador\n"
        help_message += "/isadmin [ID do usuário ou responder a mensagem] - Checa se um usuário é administrador"

        self.telegram_client.send_message(chat_id, help_message)


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

        def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
            text_str = str(text)
            special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
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

            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
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


    def handle_my_alerts(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """Trata o comando /meusalertas."""
        try:
            alert_preferences = self.db_manager.get_user_crypto_preferences(str(user_id), with_alerts=True)

            if not alert_preferences:
                self.telegram_client.send_message(chat_id, "Você ainda não configurou nenhum alerta de preço. Use /alerta [símbolo] [alta/baixa] [preço] para adicionar.")
                return

            response_lines = ["🔔 **Seus alertas de preço configurados:**"]

            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
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


    def handle_list_coins(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /listar.
        Espera argumentos opcionais: [moeda_base] [quantidade]
        Ex: /listar usd 10, /listar brl 20, /listar 50 (usa usd padrão)
        """
        parts = args.split()
        vs_currency = 'usd'
        per_page = 10

        if len(parts) == 1:
             try:
                  per_page = int(parts[0])
                  if per_page <= 0 or per_page > 250:
                       self.telegram_client.send_message(chat_id, "Quantidade inválida. Por favor, especifique um número entre 1 e 250.")
                       return
             except ValueError:
                  vs_currency = parts[0].lower()

        elif len(parts) == 2:
             vs_currency = parts[0].lower()
             try:
                  per_page = int(parts[1])
                  if per_page <= 0 or per_page > 250:
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
            coins_list = self.price_client.get_coins_list_with_price(vs_currency=vs_currency, per_page=per_page)

            if not coins_list:
                self.telegram_client.send_message(chat_id, f"❌ Não foi possível obter a lista de moedas em {vs_currency.upper()}. Por favor, tente novamente mais tarde.")
                return

            response_lines = [f"🏆 **Top {len(coins_list)} moedas por Capitalização de Mercado em {vs_currency.upper()}:**"]

            def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
                text_str = str(text)
                special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
                return re.sub(special_chars, r'\\\1', text_str)

            for coin in coins_list:
                rank = coin.get('market_cap_rank', 'N/A')
                symbol = coin.get('symbol', 'N/A').upper()
                name = coin.get('name', 'N/A')
                price = coin.get('current_price')
                change_24h = coin.get('price_change_percentage_24h')

                price_formatted = f"{price:,.2f}" if price is not None else "N/A"
                change_formatted = f"{change_24h:+.2f}%" if change_24h is not None else "N/A"

                if change_24h is not None:
                     if change_24h >= 0:
                          change_formatted += " 🟢"
                     else:
                          change_formatted += " 🔴"

                rank_escaped = escape_markdownv2_response_local(rank)
                symbol_escaped = escape_markdownv2_response_local(symbol)
                name_escaped = escape_markdownv2_response_local(name)
                price_escaped = escape_markdownv2_response_local(price_formatted)
                change_escaped = escape_markdownv2_response_local(change_formatted)

                line = f"{rank_escaped}\\. **{symbol_escaped}** \({name_escaped}\): \\${price_escaped} \(24h: {change_escaped}\)"

                response_lines.append(line)

            response_text = "\n".join(response_lines)
            self.telegram_client.send_message(chat_id, response_text, parse_mode='MarkdownV2')


    # CORRIGIDO: Lógica de verificação de admin agora usa a função combinada
    def handle_broadcast(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /broadcast.
        Envia a mensagem fornecida nos argumentos para todos os usuários registrados.
        Apenas usuários com permissão de admin (env var ou DB) podem usar este comando.
        """
        # 1. Verificar se o remetente é administrador usando a lógica combinada
        if not self._is_user_allowed_admin_command(user_id):
            logger.warning(f"Unauthorized attempt to use broadcast command by user {user_id} in chat {chat_id}.")
            self.telegram_client.send_message(chat_id, "❌ Comando de broadcast restrito a administradores.")
            return

        # 2. Obter a mensagem a ser transmitida dos argumentos
        broadcast_message = args.strip()
        if not broadcast_message:
            self.telegram_client.send_message(chat_id, "Por favor, forneça a mensagem a ser transmitida (ex: /broadcast Olá a todos!).")
            return

        logger.info(f"Admin user {user_id} is initiating broadcast message: '{broadcast_message[:100]}...'")

        # 3. Obter a lista de todos os IDs de usuário do banco de dados
        try:
            all_user_ids = self.db_manager.get_all_user_telegram_ids()
            logger.debug(f"Attempting to broadcast to {len(all_user_ids)} users.")
        except Exception as e:
            logger.error(f"Error getting all user IDs for broadcast: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "❌ Erro ao obter a lista de usuários para broadcast.")
            return

        if not all_user_ids:
            self.telegram_client.send_message(chat_id, "ℹ️ Não há usuários registrados no banco de dados para enviar o broadcast.")
            return

        # 4. Enviar a mensagem para cada usuário
        sent_count = 0
        failed_count = 0
        failed_users = []

        def escape_markdownv2_response_local(text: Union[str, float, int]) -> str:
            text_str = str(text)
            special_chars = r'([\[\]\(\)~`>#\+\-=\|\{\}\.!])'
            return re.sub(special_chars, r'\\\1', text_str)

        broadcast_message_escaped = escape_markdownv2_response_local(broadcast_message)

        for target_user_id in all_user_ids:
            try:
                self.telegram_client.send_message(chat_id=str(target_user_id), text=broadcast_message_escaped, parse_mode='MarkdownV2')
                sent_count += 1
                logger.debug(f"Broadcast message sent to user ID: {target_user_id}")
                time.sleep(0.1)
            except Exception as e:
                failed_count += 1
                failed_users.append(target_user_id)
                logger.error(f"❌ Failed to send broadcast message to user ID {target_user_id}: {e}", exc_info=True)

        result_message = f"✅ Broadcast concluído.\n"
        result_message += f"Enviado com sucesso para {sent_count} usuários.\n"
        if failed_count > 0:
            result_message += f"❌ Falha ao enviar para {failed_count} usuários (IDs: {', '.join(failed_users[:10])}{'...' if len(failed_users) > 10 else ''})."

        self.telegram_client.send_message(chat_id, result_message)
        logger.info(f"Broadcast result reported to admin in chat {chat_id}.")


    # CORRIGIDO: Lógica de verificação de admin agora usa a função combinada
    def handle_add_admin(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /addadmin.
        Promove um usuário a administrador (status no DB). Apenas admins (env var ou DB) podem usar este comando.
        Espera o ID do usuário como argumento ou responde a uma mensagem do usuário a ser promovido.
        """
        # 1. Verificar se o remetente é administrador usando a lógica combinada
        if not self._is_user_allowed_admin_command(user_id):
            self.telegram_client.send_message(chat_id, "❌ Comando restrito a administradores.")
            return

        target_user_id = None
        target_username = None

        # Tenta obter o ID do usuário a partir dos argumentos
        if args.strip():
            target_user_id = args.strip()
            # Nota: get_chat_member é assíncrona. Para chamá-la aqui, este handler precisaria ser async def.
            # Mantendo síncrono por enquanto, sem buscar nome por ID de argumento.
            pass # Não busca o nome por enquanto

        # Se não houver argumentos, tenta obter o ID da mensagem respondida
        elif update.effective_message.reply_to_message:
            target_user_id = str(update.effective_message.reply_to_message.from_user.id)
            target_username = update.effective_message.reply_to_message.from_user.username
            # Opcional: Obter first_name/last_name também

        if not target_user_id:
            self.telegram_client.send_message(chat_id, "Por favor, forneça o ID do usuário ou responda a uma mensagem do usuário que deseja promover a administrador.")
            return

        # Não permite promover a si mesmo (embora não cause erro, é redundante)
        if str(target_user_id) == str(user_id):
             self.telegram_client.send_message(chat_id, "Você já é um administrador.")
             return

        # Garante que o usuário alvo existe no banco de dados (cria se não existir)
        try:
             # get_or_create_user agora lida com a sessão internamente
             target_user = self.db_manager.get_or_create_user(telegram_id=target_user_id, username=target_username)
             if not target_user:
                  self.telegram_client.send_message(chat_id, f"❌ Não foi possível encontrar ou criar o usuário com ID {target_user_id} no banco de dados.")
                  return
        except Exception as e:
             logger.error(f"Error getting or creating target user {target_user_id} for addadmin: {e}", exc_info=True)
             self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro ao acessar o banco de dados para promover o usuário.")
             return


        # Define o status de administrador no banco de dados
        try:
            # set_user_admin_status agora lida com a sessão internamente
            success = self.db_manager.set_user_admin_status(target_user_id, True)

            if success:
                # Tenta obter o nome do usuário para a mensagem de confirmação
                user_display_name = target_username if target_username else f"ID {target_user_id}"
                self.telegram_client.send_message(chat_id, f"✅ Usuário {user_display_name} foi promovido a administrador.")
                # Opcional: Enviar uma mensagem privada para o novo admin
                try:
                     self.telegram_client.send_message(target_user_id, "🎉 Você agora é um administrador do bot MarianaCryptoBot!")
                except Exception as e:
                     logger.warning(f"Failed to send private message to new admin {target_user_id}: {e}")

            else:
                 self.telegram_client.send_message(chat_id, f"❌ Não foi possível promover o usuário com ID {target_user_id} a administrador.")

        except Exception as e:
            logger.error(f"Error setting admin status for user {target_user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro interno ao definir o status de administrador.")


    # CORRIGIDO: Lógica de verificação de admin agora usa a função combinada
    def handle_remove_admin(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /removeadmin.
        Rebaixa um usuário de administrador (status no DB). Apenas admins (env var ou DB) podem usar este comando.
        Espera o ID do usuário como argumento ou responde a uma mensagem do usuário a ser rebaixado.
        """
        # 1. Verificar se o remetente é administrador usando a lógica combinada
        if not self._is_user_allowed_admin_command(user_id):
            self.telegram_client.send_message(chat_id, "❌ Comando restrito a administradores.")
            return

        target_user_id = None
        target_username = None

        # Tenta obter o ID do usuário a partir dos argumentos
        if args.strip():
            target_user_id = args.strip()
            # Não busca o nome por enquanto (mesma razão do addadmin)
            pass

        # Se não houver argumentos, tenta obter o ID da mensagem respondida
        elif update.effective_message.reply_to_message:
            target_user_id = str(update.effective_message.reply_to_message.from_user.id)
            target_username = update.effective_message.reply_to_message.from_user.username

        if not target_user_id:
            self.telegram_client.send_message(chat_id, "Por favor, forneça o ID do usuário ou responda a uma mensagem do usuário que deseja remover de administrador.")
            return

        # Não permite remover o admin primário (env var) ou a si mesmo (se for o único admin DB)
        # Para remover o admin primário, a variável de ambiente deve ser removida.
        if self.primary_admin_telegram_id and str(target_user_id) == str(self.primary_admin_telegram_id):
             self.telegram_client.send_message(chat_id, "❌ Não é possível remover o administrador principal definido pela variável de ambiente TELEGRAM_ADMIN_ID usando este comando.")
             return

        if str(target_user_id) == str(user_id):
             # Verifica se ele é o único admin no DB antes de impedir a remoção
             # Se ele for admin DB e o único, não pode se remover.
             # Se ele for admin DB e houver outros admins (DB ou primário), ele PODE se remover.
             # Simplificando: impede a si mesmo de remover o status DB se for o único admin.
             # Para uma lógica mais robusta, precisaríamos contar admins.
             # Por enquanto, apenas impede a si mesmo de remover o status DB.
             self.telegram_client.send_message(chat_id, "Você não pode remover seu próprio status de administrador usando este comando.")
             return


        # Verifica se o usuário alvo existe e é admin no DB antes de tentar remover
        try:
             # is_user_admin (do DB) agora lida com a sessão internamente
             if not self.db_manager.is_user_admin(target_user_id):
                  user_display_name = target_username if target_username else f"ID {target_user_id}"
                  self.telegram_client.send_message(chat_id, f"ℹ️ Usuário {user_display_name} não é um administrador no banco de dados.")
                  return
        except Exception as e:
             logger.error(f"Error checking DB admin status for removeadmin on user {target_user_id}: {e}", exc_info=True)
             self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro ao verificar o status de administrador do usuário no banco de dados.")
             return


        # Define o status de administrador como False no banco de dados
        try:
            # set_user_admin_status agora lida com a sessão internamente
            success = self.db_manager.set_user_admin_status(target_user_id, False)

            if success:
                user_display_name = target_username if target_username else f"ID {target_user_id}"
                self.telegram_client.send_message(chat_id, f"✅ Usuário {user_display_name} foi removido de administrador.")
                # Opcional: Enviar uma mensagem privada para o usuário rebaixado
                try:
                     self.telegram_client.send_message(target_user_id, "😔 Seu status de administrador do bot MarianaCryptoBot foi removido.")
                except Exception as e:
                     logger.warning(f"Failed to send private message to removed admin {target_user_id}: {e}")
            else:
                 self.telegram_client.send_message(chat_id, f"❌ Não foi possível remover o usuário com ID {target_user_id} de administrador.")

        except Exception as e:
            logger.error(f"Error setting admin status for user {target_user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro interno ao definir o status de administrador.")


    # CORRIGIDO: Lógica de verificação de admin agora usa a função combinada
    def handle_is_admin(self, args: str, user_id: str, chat_id: str, update: Any, context: Any) -> None:
        """
        Trata o comando /isadmin.
        Checa se um usuário específico é administrador (env var ou DB).
        Espera o ID do usuário como argumento ou responde a uma mensagem do usuário a ser checado.
        """
        target_user_id = None
        target_username = None

        # Tenta obter o ID do usuário a partir dos argumentos
        if args.strip():
            target_user_id = args.strip()
            # Não busca o nome por enquanto
            pass

        # Se não houver argumentos, checa o próprio usuário que enviou o comando
        elif not update.effective_message.reply_to_message:
            target_user_id = user_id
            target_username = update.effective_message.from_user.username
            # Opcional: Obter first_name/last_name também

        # Se não houver argumentos e for uma resposta, tenta obter o ID da mensagem respondida
        elif update.effective_message.reply_to_message:
             target_user_id = str(update.effective_message.reply_to_message.from_user.id)
             target_username = update.effective_message.reply_to_message.from_user.username


        if not target_user_id:
            self.telegram_client.send_message(chat_id, "Por favor, forneça o ID do usuário, responda a uma mensagem do usuário, ou use o comando sem argumentos para checar seu próprio status.")
            return

        # Garante que o usuário alvo existe no banco de dados (cria se não existir)
        # Isso é necessário para checar o status is_admin do DB.
        try:
             # get_or_create_user agora lida com a sessão internamente
             target_user = self.db_manager.get_or_create_user(telegram_id=target_user_id, username=target_username)
             if not target_user:
                  # Se não existe no DB, não pode ser admin do DB.
                  # Mas ainda pode ser o admin primário da env var.
                  is_admin = self._is_user_allowed_admin_command(target_user_id)
                  user_display_name = target_username if target_username else f"ID {target_user_id}"
                  if is_admin:
                       self.telegram_client.send_message(chat_id, f"✅ Usuário {user_display_name} é um administrador (definido pela variável de ambiente).")
                  else:
                       self.telegram_client.send_message(chat_id, f"ℹ️ Usuário {user_display_name} não é um administrador.")
                  return # Sai da função após checar e responder

        except Exception as e:
             logger.error(f"Error getting or creating target user {target_user_id} for isadmin: {e}", exc_info=True)
             self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro ao acessar o banco de dados para checar o status do usuário.")
             return


        # Checa o status de administrador usando a lógica combinada
        try:
            is_admin = self._is_user_allowed_admin_command(target_user_id)
            user_display_name = target_username if target_username else f"ID {target_user_id}"

            if is_admin:
                # Especifica se é admin primário ou admin do DB
                if self.primary_admin_telegram_id and str(target_user_id) == str(self.primary_admin_telegram_id):
                     self.telegram_client.send_message(chat_id, f"✅ Usuário {user_display_name} é o administrador principal (definido pela variável de ambiente).")
                else:
                     self.telegram_client.send_message(chat_id, f"✅ Usuário {user_display_name} é um administrador (definido no banco de dados).")
            else:
                self.telegram_client.send_message(chat_id, f"ℹ️ Usuário {user_display_name} não é um administrador.")

        except Exception as e:
            logger.error(f"Error checking admin status for user {target_user_id}: {e}", exc_info=True)
            self.telegram_client.send_message(chat_id, "❌ Ocorreu um erro interno ao checar o status de administrador.")

