import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import pytz
from pytz import timezone # <-- Importar timezone especificamente para clareza
import re # <-- Importa o módulo re para usar expressões regulares
from apscheduler.schedulers.background import BackgroundScheduler # <-- IMPORTAR BackgroundScheduler REAL aqui
from apscheduler.triggers.interval import IntervalTrigger


# Importar as classes dependentes para type hinting
# Ajustado: Importa apenas o necessário para evitar NameErrors se DatabaseManager tiver type hints para modelos
# from database_manager import DatabaseManager # Não precisamos importar a classe real aqui para type hinting
# from telegram_client import TelegramClient   # Não precisamos importar a classe real aqui para type hinting
# from coingecko_client import CoinGeckoClient as PriceClient # Não precisamos importar a classe real aqui para type hinting


# Adiciona classes dummy para type hinting, conforme a estrutura esperada
class DatabaseManager:
    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None): pass
    def log_message(self, telegram_id: str, role: str, content: str, chat_id: str, message_telegram_id: Optional[int] = None) -> None: pass
    def add_or_update_preference(self, telegram_id: str, symbol: str, is_favorite: Optional[bool] = None, high_alert: Optional[float] = None, low_alert: Optional[float] = None): pass
    def get_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, is_favorite: Optional[bool] = None, with_alerts: bool = False) -> List[Any]: pass
    def clear_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, clear_favorites: bool = True, clear_alerts: bool = True) -> bool: pass
    # Método usado pelo PriceMonitor - CORRIGIDO O NOME NA CLASSE DUMMY TAMBÉM!
    def get_all_user_preferences_for_monitoring(self) -> List[Any]: pass
    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool: pass
    # Adiciona classe dummy para o modelo CryptoPreference se for usado diretamente aqui para type hinting
    # Se Preference for retornado diretamente pela sessão, pode ser necessário definir uma classe dummy.
    # Assumindo que get_all_user_preferences_for_monitoring retorna objetos com atributos symbol, high_alert, low_alert, last_alert_triggered_at, last_alert_price e user (com telegram_id)
    class CryptoPreference:
         id: int
         user_id: int
         symbol: str
         is_favorite: bool
         high_alert: Optional[float]
         low_alert: Optional[float]
         last_alert_triggered_at: Optional[datetime]
         last_alert_price: Optional[float]
         user: 'DatabaseManager.User' # Assumindo relacionamento com a classe User dummy

    class User:
         id: int
         telegram_id: str
         username: Optional[str]
         first_name: Optional[str]
         last_name: Optional[str]


class TelegramClient:
    # Note: send_message na classe dummy não precisa ser idêntico ao real
    # A implementação real está em telegram_client.py e lida com parse_mode
    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None: pass

class PriceClientInterface:
    def is_ready(self) -> bool: pass
    def is_valid_symbol(self, symbol: str) -> bool: pass
    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]: pass
    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]: pass

# Classe Dummy para BackgroundScheduler apenas para type hinting na inicialização
# REMOVIDO: Não precisamos mais da dummy, importamos a classe real no __init__


logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class PriceMonitor:
    # Ajustado type hints para usar as classes dummy definidas acima
    def __init__(self, db_manager: DatabaseManager, price_client: PriceClientInterface, telegram_client: TelegramClient):
        """
        Inicializa o PriceMonitor com as dependências.
        :param db_manager: Instância do DatabaseManager.
        :param price_client: Instância do PriceClient (ex: CoinGeckoClient).
        :param telegram_client: Instância do TelegramClient.
        """
        if db_manager is None or price_client is None or telegram_client is None:
             logger.critical("❌ PriceMonitor requires valid instances of DatabaseManager, PriceClient, and TelegramClient.")
             raise ValueError("Missing critical dependencies for PriceMonitor")

        # Guarda as instâncias REAIS passadas de main.py
        self.db_manager: DatabaseManager = db_manager
        self.price_client: PriceClientInterface = price_client
        self.telegram_client: TelegramClient = telegram_client


        # Define o fuso horário do Brasil (Sudeste)
        self.brazil_timezone = timezone('America/Sao_Paulo') # <-- Define o timezone específico

        # Configura o scheduler COM O TIMEZONE DO BRASIL
        # Inicializa o scheduler REAL aqui
        self.scheduler = BackgroundScheduler(timezone=self.brazil_timezone) # <-- Use self.brazil_timezone aqui
        logger.info(f"BackgroundScheduler initialized with timezone: {self.brazil_timezone}.")


        # Configura um cache local para preços recentes das moedas monitoradas
        # {symbol: {'price_usd': float, 'price_brl': float, 'timestamp': datetime}}
        self._price_cache: Dict[str, Dict[str, Union[float, datetime]]] = {}
        # TODO: Implementar uso real do cache para otimização futura


    def start(self):
        """Inicia o scheduler para monitorar preços."""
        if not self.price_client or not self.price_client.is_ready():
             logger.warning("PriceClient is not ready. Cannot start price monitoring.")
             return

        # Adiciona o job de monitoramento ao scheduler
        # run_alerts_check será executado a cada 30 segundos para teste
        # replace_existing=True evita duplicidade se start() for chamado mais de uma vez
        self.scheduler.add_job(
            self.run_alerts_check,
            trigger=IntervalTrigger(seconds=30), # Roda a cada 30 segundos para teste
            id='alerts_check_job',
            name='alerts_check_job',
            replace_existing=True # Substitui se já existir um job com este ID
        )
        logger.info("Scheduled 'alerts_check_job' to run every 30 seconds for testing.")

        # Inicia o scheduler
        if not self.scheduler.running: # Evita iniciar múltiplas vezes se start() for chamado
             self.scheduler.start()
             logger.info("PriceMonitor scheduler started.")
        else:
             logger.info("PriceMonitor scheduler is already running.")


    def run_alerts_check(self):
        """
        Job que é executado periodicamente pelo scheduler.
        Busca alertas, verifica preços e envia notificações.
        """
        logger.debug("Running scheduled alerts check...")
        try:
            # 1. Obter todas as preferências de usuário que têm alertas configurados
            # get_all_user_preferences_for_monitoring já retorna APENAS prefs com high_alert ou low_alert
            # CORRIGIDO: Usar o nome correto do método no DBManager
            alert_preferences = self.db_manager.get_all_user_preferences_for_monitoring()
            logger.debug(f"Found {len(alert_preferences)} active alert preferences in DB.")

            if not alert_preferences:
                logger.debug("No active alerts found. Skipping price check.")
                return # Não há alertas para verificar

            # 2. Coletar símbolos únicos das preferências com alertas
            symbols_to_check = list(set([pref.symbol for pref in alert_preferences]))
            logger.debug(f"Symbols to check prices for: {symbols_to_check}")

            # 3. Obter os preços atuais para todos os símbolos de uma vez (em USD e BRL)
            current_prices_data = self.price_client.get_multiple_prices(symbols_to_check, currency=['usd', 'brl']) # Obtém USD e BRL

            logger.debug(f"Fetched current prices data: {current_prices_data}")

            if not current_prices_data:
                 logger.warning("Failed to fetch any current prices from price client. Cannot check alerts.")
                 # TODO: Adicionar contagem de falhas e talvez notificar admin se persistir?
                 return # Falhou em obter preços

            # 4. Iterar sobre cada preferência para verificar se os alertas foram atingidos
            # Usamos a hora atual NO FUSO HORÁRIO DO SCHEDULER (America/Sao_Paulo) para comparações consistentes
            now = datetime.now(self.brazil_timezone) # <-- Use datetime.now() com o timezone configurado

            for pref in alert_preferences:
                user_telegram_id = getattr(pref.user, 'telegram_id', None) # Acessa o telegram_id através do relacionamento 'user'
                if user_telegram_id is None:
                     logger.error(f"Preference ID {pref.id} has no associated user. Skipping alert check for this preference.")
                     continue # Pula esta preferência se o usuário não puder ser identificado

                symbol = pref.symbol
                high_alert = pref.high_alert
                low_alert = pref.low_alert
                last_triggered = pref.last_alert_triggered_at # Pode ser None
                last_triggered_price = pref.last_alert_price # Pode ser None


                # Garante que last_triggered é um datetime aware (America/Sao_Paulo ou None) para comparação
                # Se o datetime naive salvo no DB é comum com SQLite sem configuração especial,
                # precisamos "torná-lo" aware no mesmo timezone do scheduler para a comparação.
                # A melhor prática é salvar sempre aware, mas para compatibilidade com SQLite naive:
                if last_triggered is not None and last_triggered.tzinfo is None:
                     # Assume que o datetime naive salvo no DB representa um ponto no tempo
                     # que deve ser interpretado no timezone do scheduler.
                     # Use localize para adicionar a informação do timezone sem converter.
                     try:
                         last_triggered = self.brazil_timezone.localize(last_triggered)
                     except Exception as e:
                          logger.error(f"Error localizing naive datetime for preference ID {pref.id}: {last_triggered}. Error: {e}", exc_info=True)
                          # Em caso de erro na localização, tratamos como se nunca tivesse disparado para evitar loop.
                          last_triggered = None # Trata como None se não conseguir localizar


                # Log de Debug para verificar last_triggered de forma segura
                logger.debug(f"Checking alerts for user {user_telegram_id}, symbol {symbol}. High: {high_alert}, Low: {low_alert}. Last triggered: {last_triggered}. (Aware: {last_triggered.tzinfo is not None if last_triggered else 'N/A'}), Last triggered price: {last_triggered_price}.")


                # Obtém os dados de preço atuais para este símbolo
                symbol_price_data = current_prices_data.get(symbol) # Retorna dict ou None
                current_price_usd = symbol_price_data.get('price_usd') if symbol_price_data else None
                current_price_brl = symbol_price_data.get('price_brl') if symbol_price_data else None

                if current_price_usd is None:
                    logger.warning(f"Current USD price not available for symbol {symbol}. Cannot check alerts for this symbol.")
                    # Não pule, continue para o próximo alerta, mas este símbolo não será verificado nesta rodada
                    continue # Pula para a próxima iteração do loop for


                alert_to_send = None # Flag para determinar se um alerta deve ser enviado (high ou low)
                triggered_price = None # O preço que disparou o alerta (será o current_price_usd)
                alert_type = None # 'high' ou 'low'

                # Verifica alerta de ALTA
                # Se high_alert está definido E o preço atual >= high_alert
                if high_alert is not None and current_price_usd >= high_alert:
                     logger.debug(f"High alert triggered for {symbol}: Current price ${current_price_usd:.8f} >= High target ${high_alert:.8f}.")
                     alert_to_send = 'high'
                     triggered_price = current_price_usd # O preço de disparo é o preço atual
                     alert_type = 'high'


                # Verifica alerta de BAIXA (apenas se ALTA não foi disparado)
                # Se low_alert está definido E o preço atual <= low_alert
                if alert_to_send is None and low_alert is not None and current_price_usd <= low_alert:
                     logger.debug(f"Low alert triggered for {symbol}: Current price ${current_price_usd:.8f} <= Low target ${low_alert:.8f}.")
                     alert_to_send = 'low'
                     triggered_price = current_price_usd # O preço de disparo é o preço atual
                     alert_type = 'low'

                # Define target_price APENAS se um alerta foi detectado
                target_price = None
                if alert_type == 'high':
                    target_price = high_alert
                elif alert_type == 'low':
                    target_price = low_alert


                # --- Lógica de Throttling (Evitar Spam) ---
                # Só aplica throttling se um alerta foi disparado (alert_to_send is not None) E target_price foi definido
                # (target_price estará definido se alert_to_send não for None pela lógica acima)
                if alert_to_send is not None and target_price is not None:
                     send_alert = True # Assume que pode enviar por padrão

                     # Regra 1: Não disparar se já disparou nos últimos 10 minutos
                     # Compara datetime aware 'now' com datetime aware 'last_triggered'
                     if last_triggered is not None:
                          # Crie um datetime aware para a comparação de 10 minutos atrás
                          ten_minutes_ago = now - timedelta(minutes=10)
                          if last_triggered > ten_minutes_ago: # Se o último disparo foi APÓS 10 minutos atrás
                              logger.debug(f"Throttling alert for {symbol} ({alert_type}): Last triggered less than 10 minutes ago ({last_triggered}). Blocking based on time rule.")
                              send_alert = False # Não envia se disparou recentemente

                     # Regra 2: Se bloqueado pela Regra 1 (send_alert is False neste ponto),
                     # só envia se a variação desde o último disparo > 0.5% E o preço do último disparo está registrado E o preço atual é válido.
                     # Nota: last_triggered_price é o preço *quando* o alerta foi disparado pela última vez.
                     # Esta regra só sobrepõe a Regra 1 (permitindo disparo) SE Regra 1 BLOQUEOU
                     if send_alert is False and last_triggered_price is not None and triggered_price is not None:
                         # Calcula a variação percentual entre o preço atual (que disparou) e o preço do último disparo
                         # Evita divisão por zero
                         if last_triggered_price != 0:
                              # Use abs() para variação em qualquer direção
                              price_change_percent_since_last_alert = abs((triggered_price - last_triggered_price) / last_triggered_price) * 100
                              logger.debug(f"Throttling check for {symbol} ({alert_type}): Price change since last triggered price ({last_triggered_price:.8f}) to current ({triggered_price:.8f}) is {price_change_percent_since_last_alert:.2f}%.")
                              # Se a variação for >= 0.5%, PODE enviar o alerta (override Regra 1)
                              if price_change_percent_since_last_alert >= 0.5:
                                  logger.debug(f"Throttling rule 2 met: Price change >= 0.5%. Allowing alert.")
                                  send_alert = True # Permite enviar apesar da Regra 1
                              else:
                                  logger.debug(f"Throttling rule 2 failed: Price change < 0.5%. Blocking alert.")
                                  # send_alert já é False, não muda

                         else:
                             # last_triggered_price era 0, o que é inesperado para preço de cripto, mas lidamos com isso.
                             # Neste caso, não podemos calcular variação percentual. Mantemos a decisão da Regra 1.
                             logger.warning(f"Last triggered price for preference ID {pref.id} was 0. Cannot calculate price change for throttling rule 2.")
                             # send_alert mantém o valor definido pela Regra 1.
                     elif send_alert is False and (last_triggered_price is None or triggered_price is None):
                          # Se bloqueado pela Regra 1, mas last_triggered_price ou triggered_price é None,
                          # não podemos aplicar a Regra 2 de variação de preço. Mantemos o bloqueio da Regra 1.
                          logger.debug(f"Throttling check for {symbol} ({alert_type}): Blocked by time rule, but price change rule 2 cannot be applied (last_triggered_price or triggered_price is None). Blocking alert.")
                          # send_alert mantém o valor definido pela Regra 1.


                     # --- Fim Lógica de Throttling ---


                     # Se as condições de disparo e throttling permitem enviar o alerta
                     if send_alert:
                          logger.info(f"Sending {alert_type} alert for {symbol} to user {user_telegram_id}.")
                          # Formata a mensagem de alerta
                          # Usando MarkdownV2, precisamos escapar: _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
                          # Dos que usamos: **, (, ), ., -, ! (e o $)
                          # A biblioteca python-telegram-bot cuida do ** para negrito
                          # Precisamos escapar (, ), ., -, !

                          # Função auxiliar para escapar caracteres MarkdownV2
                          def escape_markdownv2(text: Union[str, float, int]) -> str:
                               # Converte para string caso seja número
                               text_str = str(text)
                               # Caracteres especiais em MarkdownV2 que precisam ser escapados
                               # Re.compile pode ser mais eficiente se chamada muitas vezes, mas sub direto já funciona.
                               special_chars = r'([_\*\[\]\(\)~`>#\+\-=\|\{\}\.!])'
                               # Escapa cada caractere especial com uma barra invertida
                               return re.sub(special_chars, r'\\\1', text_str)


                          # Valores para preencher a mensagem
                          alert_type_upper = alert_type.upper()
                          current_price_usd_formatted = f"{current_price_usd:.8f}"
                          current_price_brl_formatted = f"{current_price_brl:.8f}" if current_price_brl is not None else None
                          alert_type_lower = alert_type
                          target_price_formatted = f"{target_price:.8f}"


                          # Monta a mensagem final escapando os caracteres necessários diretamente na string
                          # CORRIGIDO: Escapa os parênteses literais, o $ e o ! explicitamente nas f-strings
                          alert_message = f"🔔 **ALERTA DE PREÇO \({escape_markdownv2(alert_type_upper)}\)** para {escape_markdownv2(symbol)}\!\n" # Escapa ( e ) e o valor, e o !
                          alert_message += f"Preço atual: \\${escape_markdownv2(current_price_usd_formatted)}" # Escapa $ e o valor
                          if current_price_brl_formatted is not None:
                               alert_message += f" \(R\\${escape_markdownv2(current_price_brl_formatted)}\)" # Escapa ( , ) e $, e o valor
                          alert_message += f"\nSeu alvo \({escape_markdownv2(alert_type_lower)}\): \\${escape_markdownv2(target_price_formatted)}" # Escapa ( , ) e $, e o valor


                          # Envia a mensagem via TelegramClient
                          try:
                              # Usa o chat_id salvo no objeto User, acessível via relacionamento Preference.user
                              user_chat_id = getattr(pref.user, 'telegram_id', None) # Garantimos que pegamos o chat_id do usuário
                              if user_chat_id:
                                  # Enviamos com MarkdownV2 e string já escapada
                                  self.telegram_client.send_message(chat_id=str(user_chat_id), text=alert_message, parse_mode='MarkdownV2') # Use MarkdownV2
                                  # O log de debug abaixo foi o que nos enganou antes, pois roda ANTES do erro de envio.
                                  # Mantenha o log, mas saiba que ele não garante o sucesso do envio na API.
                                  logger.debug(f"Attempted to send alert message to user {user_telegram_id} in chat {user_chat_id}. Prepared message: {alert_message}") # Loga mensagem preparada

                                  # Atualiza o timestamp e o preço do último disparo no banco de dados
                                  # triggered_price é o preço atual que disparou o alerta.
                                  # Salva o datetime local do Brasil naive.
                                  if self.db_manager.update_alert_triggered_at(pref.id, datetime.now(self.brazil_timezone).replace(tzinfo=None), triggered_price):
                                      logger.debug(f"Updated last_alert_triggered_at and last_alert_price for preference ID {pref.id}.")
                                  else:
                                       logger.error(f"Failed to update last_alert_triggered_at and last_alert_price for preference ID {pref.id} in DB after sending alert.")
                              else:
                                  logger.error(f"Could not send alert for preference ID {pref.id}: User telegram_id is None.")

                          except Exception as e:
                              # Captura o erro específico do Telegram API para logar
                              if isinstance(e, Exception): # Verifica se é uma instância de Exception
                                   logger.error(f"❌ Failed to send alert message for {symbol} ({alert_type}) to user {user_telegram_id}: {e}", exc_info=True)
                              else:
                                   # Loga erro genérico se não for uma Exception esperada
                                   logger.error(f"❌ An unexpected error occurred while sending alert message for {symbol} ({alert_type}) to user {user_telegram_id}: {e}", exc_info=True)


                     else:
                          # Alerta disparou, mas foi bloqueado pelo throttling
                          logger.debug(f"Alert for {symbol} ({alert_type}) triggered but blocked by throttling rules.")

                # Se alert_to_send é None, nenhum alerta foi atingido para esta preferência.

        except Exception as e:
            # Captura erros que acontecem durante a execução do job (busca de alertas, preços, etc.)
            # Importante: não deixar exceções não tratadas saírem do job do scheduler
            logger.error(f"❌ Error during scheduled alerts check: {e}", exc_info=True)
