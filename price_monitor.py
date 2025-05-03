import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, Any, List, Optional, Union # Importa Union

# Importar as classes dependentes para type hinting (usando classes dummy)
# from database_manager import DatabaseManager
# from telegram_client import TelegramClient
# from coingecko_client import CoinGeckoClient

# Adiciona classes dummy para type hinting, conforme a estrutura esperada
class DatabaseManager:
    def get_all_user_preferences_for_monitoring(self) -> List[Any]: pass # Retorna lista de preferências com alertas
    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool: pass
    # Adiciona type hint para o novo método get_or_create_user que PriceMonitor pode precisar no futuro (embora não use agora)
    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None): pass


class TelegramClient:
    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = 'HTML') -> None: pass

class PriceClientInterface:
    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]: pass
    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]: pass


logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class PriceMonitor:
    # CORRIGIDO: Adiciona chat_id_for_alerts ao __init__
    def __init__(self, db_manager: DatabaseManager, price_client: PriceClientInterface, telegram_client: TelegramClient, chat_id_for_alerts: Optional[str] = None):
        """
        Inicializa o PriceMonitor com as dependências e configura o scheduler.
        :param db_manager: Instância do DatabaseManager.
        :param price_client: Instância do PriceClient (ex: CoinGeckoClient).
        :param telegram_client: Instância do TelegramClient.
        # CORRIGIDO: Adiciona parâmetro para o chat ID de alertas
        :param chat_id_for_alerts: O ID do chat para enviar alertas gerais ou de status. Pode ser None.
        """
        if db_manager is None or price_client is None or telegram_client is None:
             logger.critical("❌ PriceMonitor requires valid instances of DatabaseManager, PriceClient, and TelegramClient.")
             raise ValueError("Missing critical dependencies for PriceMonitor")

        self.db_manager: DatabaseManager = db_manager
        self.price_client: PriceClientInterface = price_client
        self.telegram_client: TelegramClient = telegram_client
        # CORRIGIDO: Armazena o chat ID para alertas
        self.chat_id_for_alerts: Optional[str] = chat_id_for_alerts


        self.scheduler = BackgroundScheduler()
        # Adiciona o job de monitoramento. Intervalo pode ser configurado.
        # Exemplo: a cada 5 minutos
        self.scheduler.add_job(self.monitor_prices, 'interval', minutes=5)
        logger.info("PriceMonitor initialized with background scheduler.")
        # O scheduler ainda não está rodando, start() precisa ser chamado.

    def start(self):
        """Inicia o scheduler do monitoramento de preços."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Price monitoring scheduler started.")
        else:
            logger.warning("Price monitoring scheduler is already running.")

    def stop_scheduler(self):
        """Para o scheduler do monitoramento de preços."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Price monitoring scheduler stopped.")
        else:
            logger.warning("Price monitoring scheduler is not running.")


    def monitor_prices(self):
        """
        Job agendado para monitorar os preços das criptomoedas
        com base nas preferências de alerta dos usuários.
        """
        logger.debug("Running price monitoring job.")
        try:
            # Obtém todas as preferências de usuários que têm alertas configurados
            # get_all_user_preferences_for_monitoring agora lida com a sessão
            alert_preferences = self.db_manager.get_all_user_preferences_for_monitoring()

            if not alert_preferences:
                logger.debug("No active alert preferences found. Skipping price check.")
                return # Sai se não houver alertas para monitorar

            logger.debug(f"Found {len(alert_preferences)} active alert preferences.")

            # Coleta os símbolos únicos para buscar os preços de uma vez
            symbols_to_check = list(set([pref.symbol for pref in alert_preferences]))
            logger.debug(f"Checking prices for symbols: {symbols_to_check}")

            # Obtém os preços atuais para todos os símbolos relevantes
            # Obtém em USD, pois os alertas são definidos em USD
            prices_data = self.price_client.get_multiple_prices(symbols_to_check, currency='usd')

            if not prices_data:
                logger.error("Failed to fetch prices from CoinGecko API during monitoring.")
                # Opcional: Enviar um alerta para o admin/chat de alertas sobre falha na API
                if self.chat_id_for_alerts:
                     error_message = "⚠️ Alerta: Falha ao obter preços da API CoinGecko durante o monitoramento."
                     self.telegram_client.send_message(self.chat_id_for_alerts, error_message)
                return # Sai se não conseguir obter os preços

            # Itera sobre as preferências para verificar se algum alerta foi atingido
            for pref in alert_preferences:
                current_price_data = prices_data.get(pref.symbol) # Obtém os dados de preço para o símbolo da preferência

                if not current_price_data or current_price_data.get('price_usd') is None:
                     logger.warning(f"No current price data available for {pref.symbol} during monitoring. Skipping alert check for this preference.")
                     continue # Pula para a próxima preferência se não houver preço

                current_price = current_price_data['price_usd']
                alert_triggered = False
                alert_message = ""

                # --- Lógica de Throttling (Evitar múltiplos alertas para o mesmo evento) ---
                # Verifica se o último alerta foi disparado recentemente (ex: nas últimas 4 horas)
                # E se o preço ainda está no "lado" do alerta que disparou anteriormente.
                # Isso impede que o bot envie alertas repetidos enquanto o preço fica flutuando
                # levemente acima/abaixo do limite do alerta.
                throttling_interval_hours = 4 # Intervalo de throttling em horas
                is_throttled = False
                if pref.last_alert_triggered_at and pref.last_alert_price is not None:
                    time_since_last_alert = datetime.now() - pref.last_alert_triggered_at
                    if time_since_last_alert.total_seconds() < throttling_interval_hours * 3600:
                        # Verifica se o preço ainda está no "lado" do alerta anterior
                        if (pref.high_alert is not None and pref.last_alert_price >= pref.high_alert and current_price >= pref.high_alert) or \
                           (pref.low_alert is not None and pref.last_alert_price <= pref.low_alert and current_price <= pref.low_alert):
                            is_throttled = True
                            logger.debug(f"Alert for {pref.symbol} for user {pref.user.telegram_id} is throttled. Last triggered at {pref.last_alert_triggered_at}.")


                if is_throttled:
                    continue # Pula esta preferência se estiver sob throttling


                # --- Verificação de Alerta de Alta ---
                if pref.high_alert is not None and current_price >= pref.high_alert:
                    alert_message = f"📈 Alerta de Alta para {pref.symbol.upper()}! O preço atingiu ou ultrapassou ${current_price:,.2f} (seu alerta era > ${pref.high_alert:,.2f})."
                    alert_triggered = True
                    logger.info(f"High alert triggered for {pref.symbol} for user {pref.user.telegram_id} at price {current_price}.")

                # --- Verificação de Alerta de Baixa ---
                # Usa elif para não disparar alta E baixa ao mesmo tempo, embora improvável
                elif pref.low_alert is not None and current_price <= pref.low_alert:
                    alert_message = f"📉 Alerta de Baixa para {pref.symbol.upper()}! O preço atingiu ou caiu abaixo de ${current_price:,.2f} (seu alerta era < ${pref.low_alert:,.2f})."
                    alert_triggered = True
                    logger.info(f"Low alert triggered for {pref.symbol} for user {pref.user.telegram_id} at price {current_price}.")


                # --- Disparar Alerta e Atualizar Histórico ---
                if alert_triggered:
                    try:
                        # Envia a mensagem de alerta para o usuário (usando o telegram_id do objeto User relacionado)
                        # O objeto User é carregado via joinedload na consulta get_all_user_preferences_for_monitoring
                        self.telegram_client.send_message(str(pref.user.telegram_id), alert_message)
                        logger.debug(f"Alert message sent to user {pref.user.telegram_id} for {pref.symbol}.")

                        # Atualiza o timestamp do último alerta disparado no DB para throttling
                        # update_alert_triggered_at agora lida com a sessão
                        self.db_manager.update_alert_triggered_at(pref.id, datetime.now(), current_price)
                        logger.debug(f"Updated last_alert_triggered_at for preference ID {pref.id}.")

                    except Exception as e:
                        logger.error(f"❌ Error sending alert message or updating timestamp for user {pref.user.telegram_id}, preference ID {pref.id}: {e}", exc_info=True)
                        # Continua para o próximo alerta mesmo que um falhe

        except Exception as e:
            logger.critical(f"❌ An unexpected error occurred during price monitoring job: {e}", exc_info=True)
            # Opcional: Enviar um alerta para o admin/chat de alertas sobre falha crítica no monitor
            if self.chat_id_for_alerts:
                 critical_error_message = f"❌ Alerta Crítico: Ocorreu um erro inesperado durante o monitoramento de preços: {e}"
                 self.telegram_client.send_message(self.chat_id_for_alerts, critical_error_message)

