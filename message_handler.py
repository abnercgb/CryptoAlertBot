import logging
import os
import unicodedata
import re
from typing import Dict, Any, List, Optional, Type, Union
from datetime import datetime # <-- ADICIONADO: Importa o módulo datetime

# Importar as classes dependentes para type hinting (MANTENHA ESTE BLOCO)
# Isso ajuda ferramentas de análise de código (como linters e IDEs)
# a entender as dependências sem precisar importar os módulos reais aqui,
# evitando problemas de dependência circular, embora neste caso específico
# as dependências reais são importadas em main.py e passadas para o handler.
# Manter as classes dummy com type hints corretos é uma boa prática.
class TelegramClient:
    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None: pass

class DatabaseManager:
    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None): pass
    def log_message(self, telegram_id: str, role: str, content: str, chat_id: str, message_telegram_id: Optional[int] = None) -> None: pass
    def add_or_update_preference(self, telegram_id: str, symbol: str, is_favorite: Optional[bool] = None, high_alert: Optional[float] = None, low_alert: Optional[float] = None): pass
    def get_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, is_favorite: Optional[bool] = None, with_alerts: bool = False) -> List[Any]: pass
    def clear_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, clear_favorites: bool = True, clear_alerts: bool = True) -> bool: pass
    # Adicionado método para obter preferências para monitoramento, usado pelo PriceMonitor
    def get_all_user_preferences_for_monitoring(self) -> List[Any]: pass
    # Atualizado: Usa datetime na anotação de tipo, que agora está importado
    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool: pass # Importa datetime para type hinting


class PriceClientInterface:
    def is_ready(self) -> bool: pass
    def is_valid_symbol(self, symbol: str) -> bool: pass
    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]: pass
    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]: pass

class OpenAIClient: pass
class IntentRecognizer: pass
# --- Fim do bloco de classes dummy para type hinting ---


logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self,
                 telegram_client: TelegramClient,
                 db_manager: DatabaseManager,
                 price_client: Optional[PriceClientInterface] = None,
                 openai_client: Optional[OpenAIClient] = None,
                 intent_recognizer: Optional[IntentRecognizer] = None,
                ):

        if telegram_client is None or db_manager is None:
             logger.critical("❌ MessageHandler requires valid TelegramClient and DatabaseManager instances.")
             raise ValueError("Missing critical dependencies for MessageHandler")

        self.telegram_client = telegram_client
        self.db_manager = db_manager
        self.price_client = price_client
        self.openai_client = openai_client
        self.intent_recognizer = intent_recognizer

        # --- Mapeamento de Comandos (Usando nomes normalizados como chaves) ---
        # As chaves devem estar em minúsculas E sem acentos/caracteres especiais (normalizadas)
        # Os valores são os nomes internos dos comandos
        self._command_map = {
            'start': 'start',
            'iniciar': 'start',

            'help': 'help',
            'ajuda': 'help',

            'price': 'price',
            'preco': 'price', # Chave normalizada para 'preço'

            'alert': 'alert',
            'alerta': 'alert', # Chave normalizada para 'alerta'

            'myalerts': 'myalerts',
            'meusalertas': 'myalerts', # Chave normalizada para 'meusalertas'

            'clearalerts': 'clearalerts',
            'limparalertas': 'clearalerts', # Chave normalizada para 'limparalertas'

            'favorite': 'favorite',
            'favorito': 'favorite', # Chave normalizada para 'favorito'
            'favoritar': 'favorite', # Chave normalizada para 'favoritar'

            'myfavorites': 'myfavorites',
            'meusfavoritos': 'myfavorites', # Chave normalizada para 'meusfavoritos'

            'clearnotifications': 'clearnotifications',
            'limparnotificacoes': 'clearnotificacoes', # Chave normalizada para 'limparnotificacoes'
            'limpartudo': 'clearnotifications', # Chave normalizada para 'limpartudo'

            # TODO: Adicionar mapeamentos normalizados para outros comandos conforme forem implementados
        }
        # --- Fim do Mapeamento de Comandos ---

        logger.info("MessageHandler instance initialized.")

    # --- Função auxiliar para normalizar strings ---
    def _normalize_string(self, text: str) -> str:
        """
        Remove acentos e caracteres especiais de uma string, converte para minúsculas.
        Útil para comparar comandos ou aliases de forma insensível a acentos/capitalização.
        """
        # Converte para o formato de decomposição NFKD (separa base e diacríticos)
        nfkd_form = unicodedata.normalize('NFKD', text)
        # Remove os caracteres combinantes (diacríticos) usando regex
        # \u0300-\u036f é o intervalo Unicode comum para diacríticos combinantes
        # O re.compile pré-compila a regex para eficiência se a função for chamada muitas vezes
        if not hasattr(self, '_re_combine_chars'):
             self._re_combine_chars = re.compile(r'[\u0300-\u036f]', re.UNICODE)
        return self._re_combine_chars.sub('', nfkd_form).lower() # Remove diacríticos e converte para minúsculas

    def handle_message(self, message: Dict[str, Any], chat_history: List[Dict[str, str]]) -> Optional[str]:
        """
        Processa uma mensagem recebida do Telegram.
        """
        user_id = message.get("from", {}).get("id")
        chat_id = message.get("chat", {}).get("id")
        message_text = message.get("text")

        logger.debug(f"handle_message received - Raw message_dict: {message}")
        logger.debug(f"handle_message received - message_text: '{message_text}' (Type: {type(message_text)})")
        starts_with_slash = message_text.startswith('/') if isinstance(message_text, str) else False
        logger.debug(f"handle_message received - message_text starts with '/': {starts_with_slash}")

        if not user_id or not chat_id or not message_text:
            logger.warning("Received message with missing user_id, chat_id or text. Ignoring.")
            return None

        logger.info(f"Received message from user {user_id} in chat {chat_id}: {message_text[:100]}...")

        user = self.db_manager.get_or_create_user(telegram_id=str(user_id), username=message.get("from",{}).get("username"), first_name=message.get("from",{}).get("first_name"), last_name=message.get("from",{}).get("last_name"))
        if user:
             logger.debug(f"Processing message for user {user.telegram_id}.")
             content_to_log = str(message_text) if message_text is not None else "None"
             message_tele_id = message.get("message_id")
             self.db_manager.log_message(telegram_id=str(user_id), role='user', content=content_to_log, chat_id=chat_id, message_telegram_id=message_tele_id)
             logger.debug(f"Logged user message for user {user.telegram_id} in chat {chat_id}.")
        else:
             logger.error(f"Failed to get or create user for telegram_id {user_id}. Cannot log message or process commands related to user/DB.")
             try:
                 self.telegram_client.send_message(chat_id, "Desculpe, não consegui identificar você ou acessar seus dados. Por favor, tente novamente.")
             except Exception as e:
                 logger.error(f"Failed to send error message to chat {chat_id}: {e}", exc_info=True)
             return None

        if starts_with_slash:
            parts = message_text.split(' ', 1)
            command_alias_with_slash = parts[0].lower()
            command_alias = command_alias_with_slash[1:]

            # --- FIX: Define args with default empty string before potential assignment ---
            args = '' # <-- DEFINE args AQUI COM VALOR PADRÃO

            # Assign args conditionally if there are more parts
            if len(parts) > 1:
                 args = parts[1] # <-- ATRIBUI AQUI APENAS SE EXISTIR


            logger.info(f"Received command alias: {command_alias_with_slash} with args: '{args}'")

            # --- Normaliza o alias do comando ANTES de buscar no mapeamento ---
            normalized_command_alias = self._normalize_string(command_alias) # <-- APLICA A NORMALIZAÇÃO
            logger.debug(f"Normalized command alias '{command_alias}' to '{normalized_command_alias}'.")

            # Resolve o alias NORMALIZADO para o nome do comando interno
            internal_command = self._command_map.get(normalized_command_alias, 'unknown') # <-- USA O ALIAS NORMALIZADO
            logger.debug(f"Resolved normalized alias '{normalized_command_alias}' to internal command '{internal_command}'.")

            response = self.route_command(internal_command, user, args, chat_id)

            if response is not None:
                 logger.debug(f"handle_message returning response string: {response[:100]}...")
            else:
                 logger.debug("handle_message returning None (response sent directly).")
            return response

        else:
            logger.debug("Received free chat message.")
            return "Hmm, isso não parece um comando. Use /help ou /ajuda para ver o que posso fazer."

    def route_command(self, internal_command: str, user: Dict[str, Any], args: str, chat_id: str) -> Optional[str]:
        """
        Roteia e lida com comandos internos.
        """
        # args é garantido ser uma string aqui (vazia se não houveram argumentos)
        logger.debug(f"Routing internal command: '{internal_command}' with args: '{args}'")
        user_telegram_id = user.telegram_id

        if internal_command == 'start':
            user_display_name = user.first_name or user.username or 'lá'
            welcome_message = f"Olá, {user_display_name}! Eu sou seu Bot de Alertas e Informações de Criptomoedas."
            welcome_message += " Use /help ou /ajuda para ver o que posso fazer."
            logger.debug(f"Route: start -> Returning: {welcome_message[:50]}...")
            return welcome_message

        elif internal_command == 'help':
            help_message = self._get_help_message()
            logger.debug(f"Route: help -> Sending help message directly to chat {chat_id}.")
            try:
                 # Atualizado: Envia mensagem de ajuda sem parse_mode para evitar problemas com caracteres
                 self.telegram_client.send_message(chat_id, help_message, parse_mode=None) # <-- parse_mode=None
                 logger.debug(f"Route: help -> Help message sent successfully.")
                 return None
            except Exception as e:
                 logger.error(f"Error sending help message to chat {chat_id}: {e}", exc_info=True)
                 return "Ocorreu um erro ao enviar a mensagem de ajuda."

        elif internal_command == 'price':
            logger.debug("Route: price")
            if self.price_client is None or not hasattr(self.price_client, 'is_ready') or not self.price_client.is_ready():
                 return "Desculpe, o serviço de preços está indisponível no momento, pois a conexão com a fonte de dados de preço não pôde ser estabelecida."

            symbol = args.strip().upper()
            if not symbol:
                return "Por favor, especifique um símbolo de criptomoeda (ex: /price BTC ou /preco BTC)."

            try:
                 logger.debug(f"Attempting to get price for symbol '{symbol}' in USD and BRL using price client.")
                 price_data = self.price_client.get_price(symbol, currency=['usd', 'brl'])

                 price_usd = price_data.get('price_usd') if price_data else None
                 price_brl = price_data.get('price_brl') if price_data else None
                 change_percent_usd = price_data.get('price_change_percent_usd') if price_data else None
                 change_percent_brl = price_data.get('price_change_percent_brl') if price_data else None

                 if price_usd is not None or price_brl is not None:
                      message_lines = [f"Preço atual de {symbol}:"]

                      if price_usd is not None:
                          usd_line = f"🇺🇸 USD: ${price_usd:.8f}"
                          if change_percent_usd is not None:
                               change_emoji_usd = "📈" if change_percent_usd >= 0 else "📉"
                               usd_line += f" ({change_emoji_usd}{change_percent_usd:.2f}%)"
                          message_lines.append(usd_line)
                      elif price_data is not None and 'price_usd' in price_data and price_usd is None:
                           message_lines.append("🇺🇸 USD: N/D (Dados da API indisponíveis)")

                      if price_brl is not None:
                           brl_line = f"🇧🇷 BRL: R${price_brl:.8f}"
                           if change_percent_brl is not None:
                                change_emoji_brl = "📈" if change_percent_brl >= 0 else "📉"
                                brl_line += f" ({change_emoji_brl}{change_percent_brl:.2f}%)"
                           message_lines.append(brl_line)
                      elif price_data is not None and 'price_brl' in price_data and price_brl is None:
                            message_lines.append("🇧🇷 BRL: N/D (Dados da API indisponíveis)")

                      if len(message_lines) > 1:
                          message = "\n".join(message_lines)
                          logger.debug(f"Route: price -> Returning price message for {symbol}: {message[:100]}...")
                          return message
                      else:
                           logger.warning(f"Fetched data for symbol {symbol}, but both USD and BRL prices are None. Response: {price_data}")
                           if hasattr(self.price_client, 'is_valid_symbol') and self.price_client.is_valid_symbol(symbol):
                               logger.error(f"Price client reported symbol '{symbol}' as valid but returned no price data for USD/BRL.")
                               return f"Não foi possível obter o preço para {symbol} em USD ou BRL no momento."
                           else:
                               logger.warning(f"Symbol '{symbol}' deemed invalid or validation failed.")
                               return f"Símbolo '{symbol}' não encontrado ou inválido na fonte de dados de preço."
                 else:
                      logger.warning(f"No price data found for symbol {symbol} from price client. Response: {price_data}")
                      if hasattr(self.price_client, 'is_valid_symbol') and self.price_client.is_valid_symbol(symbol):
                           logger.error(f"Price client reported symbol '{symbol}' as valid but returned no data at all.")
                           return f"Não foi possível obter o preço para {symbol} no momento."
                      else:
                           logger.warning(f"Símbolo '{symbol}' não encontrado ou inválido na fonte de dados de preço.")
                           return f"Símbolo '{symbol}' não encontrado ou inválido na fonte de dados de preço."
            except Exception as e:
                 logger.error(f"Error handling price command for {symbol}: {e}", exc_info=True)
                 return f"Ocorreu um erro ao buscar o preço para {symbol}. Tente novamente mais tarde."


        elif internal_command == 'alert':
             logger.debug("Route: alert")
             if self.price_client is None or not hasattr(self.price_client, 'is_ready') or not self.price_client.is_ready():
                  return "Desculpe, a funcionalidade de definir alertas de preço está indisponível no momento, pois a conexão com a fonte de dados de preço não pôde ser estabelecida."

             parts = args.split(' ')
             if len(parts) < 3:
                  logger.warning(f"Alert command received with insufficient arguments: '{args}'")
                  return "Formato do comando /alert inválido. Use /alert <SIMBOLO> high/low/alta/baixa <PRECO>"

             symbol_arg = parts[0].strip().upper()
             alert_type_input = parts[1].strip().lower()
             price_str = parts[2].strip()

             # 1. Validar o tipo de alerta (aceita high, low, alta, baixa)
             if alert_type_input not in ['high', 'low', 'alta', 'baixa']:
                  logger.warning(f"Alert command received with invalid alert type: '{alert_type_input}'")
                  return "Tipo de alerta inválido. Use 'high', 'low', 'alta' ou 'baixa'."

             # 2. Converter o tipo de alerta para 'high' ou 'low' para uso interno
             if alert_type_input == 'alta':
                  alert_type = 'high'
             elif alert_type_input == 'baixa':
                  alert_type = 'low'
             else:
                  alert_type = alert_type_input

             # 3. Validar se o símbolo é suportado pelo cliente de preço
             if not hasattr(self.price_client, 'is_valid_symbol') or not self.price_client.is_valid_symbol(symbol_arg):
                  logger.warning(f"Alert command received with invalid symbol: '{symbol_arg}'")
                  return f"Símbolo '{symbol_arg}' não encontrado ou inválido na fonte de dados de preço."

             # 4. Validar e converter o preço
             try:
                 price_value = float(price_str)
                 if price_value <= 0:
                      logger.warning(f"Alert command received with non-positive price: {price_value}")
                      return "O preço do alerta deve ser um número positivo."
             except ValueError:
                 logger.warning(f"Alert command received with non-numeric price: '{price_str}'")
                 return "Preço do alerta inválido. Por favor, use um número válido (ex: 0.5, 70000.0)."
             except Exception as e:
                  logger.error(f"Unexpected error validating price '{price_str}': {e}", exc_info=True)
                  return "Ocorreu um erro ao validar o preço. Por favor, tente novamente."

             # 5. Salvar o alerta no banco de dados
             try:
                 if alert_type == 'high':
                     success_pref = self.db_manager.add_or_update_preference(
                         user_telegram_id,
                         symbol_arg,
                         high_alert=price_value,
                         low_alert=None,
                         is_favorite=None
                     )
                     alert_message = f"✅ Alerta de {alert_type_input.upper()} definido para {symbol_arg} em ${price_value:.8f}."

                 elif alert_type == 'low':
                      success_pref = self.db_manager.add_or_update_preference(
                         user_telegram_id,
                         symbol_arg,
                         low_alert=price_value,
                         high_alert=None,
                         is_favorite=None
                     )
                      alert_message = f"✅ Alerta de {alert_type_input.upper()} definido para {symbol_arg} em ${price_value:.8f}."

                 if success_pref:
                      logger.debug(f"Route: alert -> Alert saved/updated for user {user_telegram_id}, symbol {symbol_arg}, type {alert_type} (input: {alert_type_input}), price {price_value}. Preference ID: {getattr(success_pref, 'id', 'N/A')}")
                      return alert_message
                 else:
                      logger.error(f"Route: alert -> Failed to save alert for user {user_telegram_id}, symbol {symbol_arg}. DB operation failed.")
                      return f"❌ Não foi possível definir o alerta para {symbol_arg} no momento."
             except Exception as e:
                  logger.error(f"Error handling alert command for user {user_telegram_id}, symbol {symbol_arg}, type {alert_type_input}, price {price_value}: {e}", exc_info=True)
                  return f"❌ Ocorreu um erro inesperado ao definir o alerta para {symbol_arg}. Tente novamente mais tarde."

        elif internal_command == 'myalerts':
            logger.debug("Route: myalerts")
            try:
                 # get_user_crypto_preferences(with_alerts=True) deve retornar apenas preferências com alertas.
                 # Se ele retornar outras (como visto nos logs), a lógica abaixo lida com isso.
                 user_preferences_with_alerts = self.db_manager.get_user_crypto_preferences(user_telegram_id, with_alerts=True)
                 logger.debug(f"DB returned {len(user_preferences_with_alerts)} preferences with alerts.")

                 if not user_preferences_with_alerts:
                      logger.debug("Route: myalerts -> No alerts found for user.")
                      return "Você não tem alertas de preço configurados."

                 response_lines = ["🔔 Seus alertas de preço configurados:"]
                 valid_alerts_found = False # Flag para verificar se pelo menos um alerta válido foi formatado

                 for pref in user_preferences_with_alerts:
                      logger.debug(f"Processing preference object for /myalerts: {pref}")
                      alert_info = []
                      if pref.high_alert is not None:
                           logger.debug(f"  - High alert found: {pref.high_alert}")
                           alert_info.append(f"Alta > ${pref.high_alert:.8f}")
                      if pref.low_alert is not None:
                           logger.debug(f"  - Low alert found: {pref.low_alert}")
                           alert_info.append(f"Baixa < ${pref.low_alert:.8f}")

                      # Só adiciona a linha se a preferência realmente tem alertas
                      if alert_info:
                           line = f"- {pref.symbol}: {' e '.join(alert_info)}"
                           logger.debug(f"  - Formatted alert line: {line}")
                           response_lines.append(line)
                           valid_alerts_found = True # Marca que encontrou pelo menos um alerta válido
                      else:
                           # Este warning indica que get_user_crypto_preferences(with_alerts=True) retornou algo inesperado
                           logger.warning(f"Preference {getattr(pref, 'id', 'N/A')} for user {user_telegram_id} returned by get_user_crypto_preferences(with_alerts=True) has no alerts despite filter. Skipping.")

                 # Se nenhuma linha de alerta válida foi adicionada (apenas o cabeçalho está na lista)
                 if not valid_alerts_found:
                      logger.debug("Route: myalerts -> After processing, no valid alert lines were added.")
                      # Isso pode acontecer se a query retornou preferências, mas nenhuma delas tinha high_alert ou low_alert.
                      return "Você não tem alertas de preço configurados."


                 response = "\n".join(response_lines)
                 logger.debug(f"Route: myalerts -> Returning: {response[:100]}...")

                 # --- CORREÇÃO: Enviar mensagem sem parse_mode para evitar BadRequest ---
                 # O wrapper_handler em telegram_client.py tem parse_mode='HTML' como padrão.
                 # Para /myalerts, o texto formatado pode conter caracteres (<, >) que causam erro HTML.
                 # Enviamos como texto puro aqui.
                 try:
                     self.telegram_client.send_message(chat_id, response, parse_mode=None) # <-- ADICIONE parse_mode=None AQUI
                     logger.debug(f"Route: myalerts -> Response sent successfully to chat {chat_id}.")
                     return None # Retorna None porque a mensagem já foi enviada diretamente
                 except Exception as e:
                     logger.error(f"❌ Error sending /myalerts response to chat {chat_id}: {e}", exc_info=True)
                     # Fallback para enviar uma mensagem de erro simples se a formatação falhou
                     try:
                          self.telegram_client.send_message(chat_id, "Desculpe, não consegui enviar a lista completa de alertas.", parse_mode=None)
                     except Exception as e2:
                          logger.error(f"❌ Failed to send fallback error message to chat {chat_id}: {e2}", exc_info=True)
                     return None # Ainda retorna None pois a tentativa de resposta principal falhou

            except Exception as e:
                 logger.error(f"Error handling myalerts for user {user_telegram_id}: {e}", exc_info=True)
                 # Se ocorrer um erro antes de tentar formatar/enviar (ex: erro no DBManager),
                 # esta mensagem de erro genérica é retornada.
                 return "❌ Ocorreu um erro ao buscar seus alertas."

        elif internal_command == 'clearalerts':
             logger.debug("Route: clearalerts")
             try:
                  success = self.db_manager.clear_user_crypto_preferences(user_telegram_id, clear_favorites=False, clear_alerts=True)
                  if success:
                       logger.debug("Route: clearalerts -> Alerts cleared.")
                       return "✅ Todos os seus alertas de preço foram removidos."
                  else:
                       logger.debug("Route: clearalerts -> Failed to clear alerts (user not found?).")
                       return "❌ Não foi possível remover seus alertas."
             except Exception as e:
                  logger.error(f"Error handling clearalerts for user {user_telegram_id}: {e}", exc_info=True)
                  return "❌ Ocorreu um erro ao remover seus alertas."

        elif internal_command == 'favorite':
             logger.debug("Route: favorite")
             symbol = args.strip().upper()
             if not symbol:
                  return "Por favor, especifique um símbolo de criptomoeda para marcar como favorito (ex: /favorite BTC)."

             is_symbol_valid = True
             if self.price_client is not None and hasattr(self.price_client, 'is_valid_symbol') and hasattr(self.price_client, 'is_ready') and self.price_client.is_ready():
                  try:
                       logger.debug(f"Checking symbol validity for '{symbol}' using price client.")
                       is_symbol_valid = self.price_client.is_valid_symbol(symbol)
                       if not is_symbol_valid:
                            logger.warning(f"Symbol '{symbol}' deemed invalid by price client.")
                  except Exception as e:
                       logger.error(f"Error validating symbol {symbol} with price client: {e}", exc_info=True)
                       is_symbol_valid = False
                       logger.warning(f"Symbol validation for '{symbol}' failed due to an error, proceeding with DB save attempt.")
             elif self.price_client is None or not hasattr(self.price_client, 'is_valid_symbol') or not hasattr(self.price_client, 'is_ready') or (hasattr(self.price_client, 'is_ready') and not self.price_client.is_ready()):
                  logger.warning(f"Price client not available, not ready, or missing 'is_valid_symbol' method. Cannot validate symbol for favorite command for user {user_telegram_id}. Saving to DB without validation.")

             try:
                  updated_pref = self.db_manager.add_or_update_preference(user_telegram_id, symbol, is_favorite=True)
                  if updated_pref:
                       logger.debug(f"Route: favorite -> Marked {symbol} as favorite for user {user_telegram_id}.")
                       return f"✅ '{symbol}' foi marcado como favorito." + (" Aviso: Símbolo pode ser inválido." if not is_symbol_valid else "")
                  else:
                       logger.error(f"Route: favorite -> Failed to add/update {symbol} as favorite for user {user_telegram_id}.")
                       return f"❌ Não foi possível marcar '{symbol}' como favorito."
             except Exception as e:
                  logger.error(f"Error handling favorite command for user {user_telegram_id}, symbol {symbol}: {e}", exc_info=True)
                  return f"❌ Ocorreu um erro ao marcar '{symbol}' como favorito."

        elif internal_command == 'myfavorites':
             logger.debug("Route: myfavorites")
             try:
                  user_preferences = self.db_manager.get_user_crypto_preferences(user_telegram_id, is_favorite=True)
                  if not user_preferences:
                       logger.debug("Route: myfavorites -> No favorites found.")
                       return "Você não tem criptomoedas favoritas marcadas."

                  response_lines = ["⭐️ Suas criptomoedas favoritas:"]
                  for pref in user_preferences:
                       response_lines.append(f"- {pref.symbol}")

                  response = "\n".join(response_lines)
                  logger.debug(f"Route: myfavorites -> Returning: {response[:100]}...")
                  return response
             except Exception as e:
                  logger.error(f"Error handling myfavorites for user {user_telegram_id}: {e}", exc_info=True)
                  return "❌ Ocorreu um erro ao buscar seus favoritos."

        elif internal_command == 'clearnotifications':
             logger.debug("Route: clearnotifications")
             try:
                  success = self.db_manager.clear_user_crypto_preferences(user_telegram_id, clear_favorites=True, clear_alerts=True)
                  if success:
                       logger.debug("Route: clearnotifications -> Alerts and favorites cleared.")
                       return "✅ Todos os seus alertas e favoritos foram removidos."
                  else:
                       logger.debug("Route: clearnotifications -> Failed to clear alerts and favorites (user not found?).")
                       return "❌ Não foi possível remover seus alertas e favoritos."
             except Exception as e:
                  logger.error(f"Error handling clearnotifications for user {user_telegram_id}: {e}", exc_info=True)
                  return "❌ Ocorreu um erro ao remover seus alertas e favoritos."

        elif internal_command == 'unknown':
            # args não é usado aqui, então a correção do NameError já resolve
            logger.warning(f"Unknown command alias received resolved to 'unknown'.")
            return "Comando desconhecido. Use /help ou /ajuda para ver os comandos disponíveis."

        else:
            logger.warning(f"Internal command '{internal_command}' is not implemented.")
            return "Desculpe, este comando ainda não foi completamente implementado."

    def _get_help_message(self) -> str:
        help_message = (
                "Comandos disponíveis:\n"
                "/start ou /iniciar - Inicia a conversa\n"
                "/help ou /ajuda - Mostra esta mensagem\n"
                "/price <SIMBOLO> ou /preco <SIMBOLO> - Mostra o preço atual de uma criptomoeda (ex: /price BTC)\n"
                "/alert <SIMBOLO> high/low/alta/baixa <PRECO> ou /alerta <SIMBOLO> high/low/alta/baixa <PRECO> - Define um alerta de preço (ex: /alert BTC alta 70000)\n"
                "/myalerts ou /meusalertas - Mostra seus alertas configurados\n"
                "/clearalerts ou /limparalertas - Remove todos os seus alertas\n"
                "/favorite <SIMBOLO> ou /favorito <SIMBOLO> ou /favoritar <SIMBOLO> - Marca uma criptomoeda como favorita (ex: /favorite ADA)\n"
                "/myfavorites ou /meusfavoritos - Mostra suas criptomoedas favoritas\n"
                "/clearnotifications ou /limparnotificacoes ou /limpartudo - Remove todos os alertas e favoritos\n"
            )
        return help_message