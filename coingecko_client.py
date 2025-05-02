import logging
import time
from pycoingecko import CoinGeckoAPI
from typing import List, Dict, Any, Optional, Union # Importa Union

logger = logging.getLogger(__name__)

# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

class CoinGeckoClient:
    def __init__(self):
        self.client = None
        # Cache para moedas suportadas {symbol: id} - ainda útil como fallback
        self._supported_coins = {}
        self._last_fetched_supported_coins = 0 # Timestamp da última busca

        # --- Mapeamento interno para símbolos comuns para resolver ambiguidade ---
        # Estes são os IDs corretos na CoinGecko para os símbolos mais comuns
        self._common_symbols_map = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'ADA': 'cardano',
            'XRP': 'ripple',
            'LTC': 'litecoin',
            'BCH': 'bitcoin-cash',
            'DOT': 'polkadot',
            'DOGE': 'dogecoin', # Exemplo adicional
            'SHIB': 'shiba-inu', # Exemplo adicional
            # Adicione mais símbolos comuns conforme necessário
        }
        # --- Fim do Mapeamento ---


        try:
            # Inicializa o cliente CoinGeckoAPI. A API pública não precisa de chave.
            self.client = CoinGeckoAPI()
            logger.info("✅ CoinGeckoAPI client initialized.")

            # Não buscar a lista de moedas na inicialização para não travar.
            # Será buscada sob demanda no get_coin_id se não estiver no cache ou mapeamento.

        except Exception as e:
            logger.critical(f"❌ Failed to initialize CoinGeckoAPI client: {e}", exc_info=True)
            self.client = None # Garante que o cliente é None se a inicialização falhar

    def _fetch_supported_coins(self):
        """Busca a lista completa de moedas suportadas e as armazena em cache."""
        # Limita a frequência da busca para evitar sobrecarregar a API ou ser bloqueado
        if time.time() - self._last_fetched_supported_coins < 3600: # Buscar no máximo a cada hora (3600 segundos)
            logger.debug("Using cached supported coins list.")
            return True # Assume que o cache recente é válido

        if self.client is None:
            logger.error("CoinGecko client not initialized, cannot fetch supported coins.")
            return False

        logger.info("Fetching supported coins list from CoinGecko...")
        try:
            # Obtém a lista simples de moedas (id e symbol)
            coins_list = self.client.get_coins_list()
            # Refaz o cache: {symbol.lower(): id}
            # Nota: Isso ainda pode ter ambiguidade para símbolos repetidos,
            # mas get_coin_id prioriza o mapeamento interno.
            self._supported_coins = {coin['symbol'].lower(): coin['id'] for coin in coins_list}
            self._last_fetched_supported_coins = time.time()
            logger.info(f"✅ Fetched {len(self._supported_coins)} supported coins from CoinGecko.")
            # logger.debug(f"Supported coins sample: {list(self._supported_coins.items())[:10]}...") # Opcional: logar sample
            return True
        except Exception as e:
            logger.error(f"❌ Failed to fetch supported coins from CoinGecko: {e}", exc_info=True)
            # Limpa o cache em caso de falha para tentar buscar novamente depois
            self._supported_coins = {}
            self._last_fetched_supported_coins = 0 # Reseta o timestamp para tentar novamente imediatamente
            return False


    def get_coin_id(self, symbol: str) -> Optional[str]:
        """
        Converte um símbolo de criptomoeda (ex: BTC) para o ID da CoinGecko (ex: bitcoin).
        Prioriza mapeamento interno para símbolos comuns, depois busca na lista completa.
        Retorna o ID CoinGecko em minúsculas ou None se não encontrado.
        """
        # Converte o símbolo de entrada para maiúsculas para comparação consistente
        symbol_upper = symbol.upper()

        # 1. Tenta resolver usando o mapeamento interno para símbolos comuns
        common_id = self._common_symbols_map.get(symbol_upper)
        if common_id:
            logger.debug(f"Resolved common symbol '{symbol_upper}' to CoinGecko ID '{common_id}' using internal map.")
            return common_id.lower() # Retorna o ID mapeado em minúsculas


        # 2. Se não está no mapeamento comum, tenta buscar na lista completa de moedas
        # Certifica que a lista de moedas suportadas está carregada (fetch_supported_coins cuida do cache/busca)
        # Se falhar ao buscar, _fetch_supported_coins logará o erro e retornará False.
        if not self._supported_coins:
            if not self._fetch_supported_coins():
                logger.warning(f"Could not fetch supported coins list, cannot resolve symbol '{symbol}'.")
                return None # Falhou ao buscar a lista, não pode resolver o símbolo

        # Tenta encontrar o ID na lista completa usando o símbolo em minúsculas
        # Nota: Isso ainda pode retornar IDs incorretos para símbolos não-comuns ambíguos,
        # pois o dicionário symbol -> id na lista pode ter colisão.
        # Mas para símbolos não comuns não no mapeamento, é o melhor palpite.
        coin_id_from_list = self._supported_coins.get(symbol_upper.lower()) # Busca usando símbolo em minúsculas

        if coin_id_from_list:
            logger.debug(f"Resolved symbol '{symbol}' to CoinGecko ID '{coin_id_from_list}' using supported coins list (fallback).")
            return coin_id_from_list.lower() # Retorna o ID encontrado na lista em minúsculas


        # 3. Se não encontrado no mapeamento comum nem na lista, o símbolo é inválido ou não suportado
        logger.warning(f"Symbol '{symbol}' not found in common map or supported coins list.")
        return None # Símbolo não resolvido para um ID CoinGecko


    def is_valid_symbol(self, symbol: str) -> bool:
        """Verifica se um símbolo de criptomoeda é suportado pela CoinGecko."""
        # Um símbolo é válido se conseguirmos resolver ele para um ID CoinGecko válido.
        # get_coin_id já cuida da lógica de cache/busca e mapeamento.
        # get_coin_id retorna o ID em minúsculas ou None
        resolved_id = self.get_coin_id(symbol)
        logger.debug(f"is_valid_symbol check for '{symbol}': resolved to ID '{resolved_id}'. Result: {resolved_id is not None}")
        return resolved_id is not None


    def get_price(self, symbol: str, currency: Union[str, List[str]] = 'usd') -> Optional[Dict[str, Optional[float]]]:
        """
        Obtém o preço atual de uma criptomoeda em uma ou mais moedas de referência.
        CoinGecko API usa IDs de moeda (ex: 'bitcoin') e moedas de referência (ex: 'usd', 'brl').
        Usa get_coin_id para tentar resolver o símbolo para o ID CoinGecko correto.
        Retorna um dicionário com o preço(s) e variação(ões) no formato {'price_usd': ..., 'price_change_percent_usd': ..., 'price_brl': ..., ...}
        Retorna None em caso de falha na resolução do símbolo ou na busca de preço.
        """
        if self.client is None:
            logger.error("CoinGecko client not initialized, cannot get price.")
            return None

        coin_id = self.get_coin_id(symbol) # get_coin_id retorna o ID em minúsculas ou None
        if coin_id is None:
            # get_coin_id já logou um warning se não encontrou o ID
            return None # Símbolo inválido ou não encontrado


        # Garante que currency_list é uma lista de strings em minúsculas
        if isinstance(currency, str):
            currency_list = [currency.lower()]
        elif isinstance(currency, list):
            currency_list = [c.lower() for c in currency]
        else:
             logger.error(f"Invalid currency type provided: {type(currency)}")
             return None


        # Remove duplicatas e None da lista de moedas solicitadas
        currencies_to_fetch = list(set(c for c in currency_list if c))
        if not currencies_to_fetch:
             logger.warning("No valid currencies specified for price fetch.")
             return None

        logger.debug(f"Fetching price for CoinGecko ID '{coin_id}' in currencies: {currencies_to_fetch}.")
        try:
            # Usa o endpoint get_price, passando a lista de moedas
            # pycoingecko get_price espera 'ids' como string ou lista e 'vs_currencies' como string ou lista
            price_data_from_api = self.client.get_price(ids=coin_id, vs_currencies=currencies_to_fetch, include_24hr_change=True)

            # O retorno esperado é um dict como {'coin_id': {'currency1': price, 'currency1_24h_change': change, 'currency2': price, ...}}
            # Ex: {'bitcoin': {'usd': 65000.0, 'usd_24h_change': 2.5, 'brl': 300000.0, 'brl_24h_change': 3.0}}

            result_data: Dict[str, Optional[float]] = {}
            # Verifica se a resposta da API contém o ID da moeda esperado
            if price_data_from_api and coin_id in price_data_from_api:
                data_for_coin = price_data_from_api[coin_id]
                # Itera sobre as moedas que *solicitamos*
                for cur in currencies_to_fetch:
                    # Verifica se a API retornou dados para esta moeda
                    if cur in data_for_coin:
                        result_data[f'price_{cur}'] = data_for_coin[cur]
                        # Tenta obter a variação de 24h, pode não estar presente para todas as moedas ou APIs
                        change_key = f'{cur}_24h_change'
                        result_data[f'price_change_percent_{cur}'] = data_for_coin.get(change_key) # .get retorna None se a chave não existe
                    else:
                        # Se a API NÃO retornou dados para a moeda solicitada (ex: par inválido ou API não suporta)
                        logger.warning(f"Price data for currency '{cur}' not found for CoinGecko ID '{coin_id}'. Available data keys: {list(data_for_coin.keys())}")
                        result_data[f'price_{cur}'] = None
                        result_data[f'price_change_percent_{cur}'] = None


                if result_data: # Retorna os dados se pelo menos um preço foi encontrado para qualquer moeda solicitada
                    # Verifica se TODOS os valores de preço no result_data são None. Se sim, nenhum preço válido foi obtido.
                    if all(v is None for k, v in result_data.items() if k.startswith('price_')):
                         logger.warning(f"Fetched data for CoinGecko ID '{coin_id}' but all requested prices ({currencies_to_fetch}) are None. Raw data: {price_data_from_api}")
                         return None
                    else:
                         # Pelo menos um preço é not None
                         logger.debug(f"Fetched price data for {symbol} (ID '{coin_id}'): {result_data}")
                         return result_data
                else:
                     # Isso só aconteceria se price_data_from_api[coin_id] existisse, mas o loop acima não adicionasse nada ao result_data
                     # (ex: currencies_to_fetch estava vazia ou dados malformados)
                     logger.warning(f"Processing API response for CoinGecko ID '{coin_id}' yielded no results. Raw data: {price_data_from_api.get(coin_id)}")
                     return None


            else:
                # Se a resposta da API não contém o ID da moeda esperado ou está vazia
                logger.warning(f"CoinGecko API response did not contain expected ID '{coin_id}' for symbol '{symbol}'. Response: {price_data_from_api}")
                # Verifica se get_coin_id retornou um ID, mas a API falhou ao retornar dados para ele
                # if coin_id is not None: # Esta verificação é redundante pois só chegamos aqui se coin_id não for None
                #    logger.error(f"Symbol '{symbol}' resolved to ID '{coin_id}' but API did not return data for this ID.")
                return None


        except Exception as e:
            # Captura exceções da chamada da API pycoingecko
            # get_price pode levantar exceções se a moeda/símbolo não for encontrado *na API*, mesmo após a validação local.
            # Ex: 'coin_id' válido mas par 'coin_id/currency' inválido (menos comum para usd/brl).
            # Ou erro de rede, rate limiting, etc.
            logger.error(f"❌ Failed to get price for {symbol} (resolved to ID '{coin_id}') in {currencies_to_fetch} from CoinGecko API: {e}", exc_info=True)
            return None # Retorna None em caso de erro na comunicação com a API

    def get_multiple_prices(self, symbols: List[str], currency: Union[str, List[str]] = 'usd') -> Dict[str, Optional[Dict[str, Optional[float]]]]:
        """
        Obtém preços para múltiplos símbolos em uma ou mais moedas.
        Retorna um dict {symbol_original: {'price_cur1': float, 'price_change_percent_cur1': float, ...} ou None}.
        Retorna None no VALOR do dicionário para símbolos que falharam na resolução do ID ou na busca de preço.
        """
        if self.client is None:
            logger.error("CoinGecko client not initialized, cannot get multiple prices.")
            # Retorna um dicionário com None para todos os símbolos se o cliente não está pronto
            return {symbol: None for symbol in symbols}

        # Garante que currency_list é uma lista de strings em minúsculas para passar para a API
        if isinstance(currency, str):
            currency_list = [currency.lower()]
        elif isinstance(currency, list):
            currency_list = [c.lower() for c in currency]
        else:
             logger.error(f"Invalid currency type provided to get_multiple_prices: {type(currency)}")
             return {symbol: None for symbol in symbols}


        # Remove duplicatas e None da lista de moedas solicitadas
        currencies_to_fetch = list(set(c for c in currency_list if c))
        if not currencies_to_fetch:
             logger.warning("No valid currencies specified for multiple price fetch.")
             return {symbol: None for symbol in symbols}


        # Converte todos os símbolos fornecidos para IDs CoinGecko
        # Cria um mapeamento {CoinGecko ID: símbolo original}
        id_to_symbol_map = {}
        valid_ids_to_fetch = [] # Lista de IDs válidos (em minúsculas) para passar para a API
        # Inicializa o dicionário de resultados final com None para todos os símbolos originais
        results: Dict[str, Optional[Dict[str, Optional[float]]]] = {symbol: None for symbol in symbols}


        for symbol in symbols:
            coin_id = self.get_coin_id(symbol) # get_coin_id retorna o ID em minúsculas ou None
            if coin_id:
                # Mapeia o ID (chave) para o símbolo original (valor)
                id_to_symbol_map[coin_id] = symbol
                valid_ids_to_fetch.append(coin_id)
            else:
                logger.warning(f"Symbol '{symbol}' cannot be resolved to CoinGecko ID, skipping price fetch for this symbol.")
                # O valor para este símbolo já é None no dicionário 'results' inicial.


        if not valid_ids_to_fetch:
            logger.warning("No valid symbols resolved to CoinGecko IDs for get_multiple_prices.")
            return results # Retorna o dict inicial com todos os valores None


        logger.debug(f"Fetching prices for CoinGecko IDs: {valid_ids_to_fetch} in currencies: {currencies_to_fetch}.")
        try:
            # Usa o endpoint get_price para buscar múltiplos preços eficientemente
            # ids e vs_currencies devem ser listas de strings para buscar múltiplos
            price_data_from_api = self.client.get_price(ids=valid_ids_to_fetch, vs_currencies=currencies_to_fetch, include_24hr_change=True)

            # O retorno esperado é um dict como {'coin_id1': {dados}, 'coin_id2': {dados}, ...}
            # Ex: {'bitcoin': {'usd': 65000.0, ...}, 'ethereum': {'usd': 3000.0, ...}}

            # Processa a resposta da API e popula o dicionário de resultados final
            # price_data_from_api é um dict onde as chaves são CoinGecko IDs (em minúsculas)
            for coin_id_returned, data_for_coin in price_data_from_api.items():
                 # Obtém o símbolo original usando o mapeamento ID -> Símbolo Original
                 original_symbol = id_to_symbol_map.get(coin_id_returned)
                 # Verifica se o símbolo original foi encontrado (deveria, se o ID veio da nossa lista valid_ids_to_fetch)
                 # e se os dados para a moeda de referência estão presentes
                 if original_symbol:
                      # Processa os dados retornados para este ID para as moedas solicitadas
                      symbol_price_data: Dict[str, Optional[float]] = {}
                      # Itera sobre as moedas que *solicitamos* para garantir que todas as chaves esperadas estejam no resultado (mesmo que com None)
                      for cur in currencies_to_fetch:
                           # Verifica se a API retornou dados para esta moeda dentro dos dados para o ID
                           if cur in data_for_coin:
                                symbol_price_data[f'price_{cur}'] = data_for_coin[cur]
                                change_key = f'{cur}_24h_change'
                                symbol_price_data[f'price_change_percent_{cur}'] = data_for_coin.get(change_key) # .get retorna None se a chave não existe
                           else:
                                # Se a API NÃO retornou dados para a moeda solicitada para este ID
                                logger.warning(f"Price data for currency '{cur}' not found for CoinGecko ID '{coin_id_returned}' in get_multiple_prices. Available data keys: {list(data_for_coin.keys()) if data_for_coin else 'None'}")
                                symbol_price_data[f'price_{cur}'] = None
                                symbol_price_data[f'price_change_percent_{cur}'] = None

                      # Se dados foram encontrados para este símbolo em pelo menos uma moeda
                      # Ou se queremos incluir o símbolo no resultado mesmo que todos os preços sejam None
                      # A lógica atual inclui no dict 'results', mesmo que todos os preços para ele sejam None.
                      # A validação de "pelo menos um preço não None" pode ser feita no código chamador (monitoramento).
                      results[original_symbol] = symbol_price_data
                      logger.debug(f"Fetched data for {original_symbol} (ID '{coin_id_returned}'): {symbol_price_data}")

                 else:
                      # Caso inesperado: A API retornou um ID que não estava na nossa lista de valid_ids_to_fetch?
                      # Isso não deveria acontecer se valid_ids_to_fetch foi construída corretamente.
                      logger.error(f"API returned data for unknown CoinGecko ID '{coin_id_returned}' not in id_to_symbol_map. Data: {data_for_coin}")


            return results # Retorna o dict com resultados (None no valor para falhas ou símbolos não resolvidos/sem dados)


        except Exception as e:
            logger.error(f"❌ Failed to get multiple prices from CoinGecko API for IDs {valid_ids_to_fetch} in {currencies_to_fetch}: {e}", exc_info=True)
            # Em caso de erro na API durante a busca multi-preço, o dict 'results' já foi inicializado com None
            # para todos os símbolos originais que tentamos resolver. Ele refletirá que a busca falhou.
            # Podemos opcionalmente iterar sobre valid_ids_to_fetch e setar os resultados correspondentes para None,
            # mas a inicialização já faz isso para os símbolos cujos IDs estão em valid_ids_to_fetch.
            return results # Retorna o dict com None para os que falharam ou não foram resolvidos

    def is_ready(self) -> bool:
        """Verifica se o cliente está inicializado e pronto para fazer chamadas."""
        # Considera o cliente pronto se o objeto CoinGeckoAPI foi criado
        return self.client is not None

    def is_authenticated(self) -> bool:
        """Verifica se o cliente está autenticado (CoinGecko pública não precisa)."""
        # Para a API pública da CoinGecko, não há autenticação.
        # Podemos retornar True se o cliente estiver pronto.
        return self.is_ready()

# Exemplo de uso (apenas para teste local direto deste arquivo, não rodará no bot)
# if __name__ == "__main__":
#     cg_client = CoinGeckoClient()
#     if cg_client.is_ready():
#         print("\n--- Testing single price ---")
#         # Testando com uma lista de moedas
#         btc_price_data = cg_client.get_price("BTC", ["usd", "brl"])
#         if btc_price_data:
#             print(f"BTC Price Data: {btc_price_data}")
#             usd_price = btc_price_data.get('price_usd')
#             brl_price = btc_price_data.get('price_brl')
#             usd_change = btc_price_data.get('price_change_percent_usd')
#             brl_change = btc_price_data.get('price_change_percent_brl')
#             if usd_price is not None:
#                  print(f"  USD: ${usd_price:.8f}" + (f" ({usd_change:.2f}%)" if usd_change is not None else ""))
#             if brl_price is not None:
#                  print(f"  BRL: R${brl_price:.8f}" + (f" ({brl_change:.2f}%)" if brl_change is not None else ""))
#         else:
#             print("Failed to get BTC price.")

#         invalid_price_data = cg_client.get_price("INVALID_SYMBOL", ["usd", "brl"])
#         if invalid_price_data is None:
#             print("INVALID_SYMBOL correctly returned None.")
#         else:
#              print(f"INVALID_SYMBOL returned data unexpectedly: {invalid_price_data}")


#         print("\n--- Testing multiple prices ---")
#         # Testando multiple prices com uma lista de moedas
#         multi_prices_data = cg_client.get_multiple_prices(["BTC", "ETH", "ADA", "INVALID_SYMBOL", "XRP", "DOT"], ["usd", "brl"])
#         print("Multiple Prices:")
#         for symbol, data in multi_prices_data.items():
#             print(f" {symbol}:")
#             if data:
#                  usd_price = data.get('price_usd')
#                  brl_price = data.get('price_brl')
#                  usd_change = data.get('price_change_percent_usd')
#                  brl_change = data.get('price_change_percent_brl')
#                  if usd_price is not None:
#                      print(f"   USD: ${usd_price:.8f}" + (f" ({usd_change:.2f}%)" if usd_change is not None else ""))
#                  else:
#                       print("   USD: N/D")
#                  if brl_price is not None:
#                       print(f"   BRL: R${brl_price:.8f}" + (f" ({brl_change:.2f}%)" if brl_change is not None else ""))
#                  else:
#                       print("   BRL: N/D")
#             else:
#                 print("   Failed to get price data.")
#     else:
#         print("CoinGecko client failed to initialize.")