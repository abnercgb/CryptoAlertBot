import logging
import os
# Certifique-se de que a biblioteca openai está instalada
from openai import OpenAI
from openai import APIError, APIStatusError, AuthenticationError, PermissionDeniedError, NotFoundError, ConflictError, UnprocessableEntityError, RateLimitError
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__) # Usando o logger configurado em main.py ou globalmente

# Configurar o logger se não estiver configurado externamente (fallback)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.warning("OpenAI API key not provided. OpenAIClient will not be initialized.")
            self.client = None
        else:
            try:
                # Inicializa o cliente OpenAI com a API key
                self.client = OpenAI(api_key=self.api_key)
                # Opcional: Testar a autenticação (ex: listando modelos)
                # self.client.models.list()
                logger.info("OpenAIClient initialized.")
            except AuthenticationError:
                 logger.critical("❌ OpenAI Authentication failed. Check your API key.", exc_info=True)
                 self.client = None
            except Exception as e:
                logger.critical(f"❌ Failed to initialize OpenAI client: {e}", exc_info=True)
                self.client = None

    # TODO: Implementar métodos para interagir com a API OpenAI
    # Exemplo: Análise de Sentimento (placeholder)
    def analyze_sentiment(self, text: str) -> Optional[str]:
        """
        Envia texto para a API OpenAI para análise de sentimento.
        Retorna uma string descrevendo o sentimento ou None em caso de erro.
        """
        if self.client is None:
            logger.warning("OpenAI client not initialized. Cannot analyze sentiment.")
            return None

        try:
            # Exemplo de como usar a API (você precisará ajustar o prompt e o modelo)
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo", # Ou outro modelo adequado
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that analyzes the sentiment of cryptocurrency-related text. Respond briefly with 'Positive', 'Negative', or 'Neutral'."},
                    {"role": "user", "content": f"Analyze the sentiment of this text: '{text}'"}
                ],
                max_tokens=10 # Resposta curta esperada
            )
            # Processa a resposta
            if response.choices and response.choices[0].message.content:
                sentiment = response.choices[0].message.content.strip()
                logger.debug(f"Sentiment analysis result: {sentiment}")
                return sentiment
            else:
                logger.warning("OpenAI sentiment analysis returned no content.")
                return None

        except RateLimitError:
            logger.warning("OpenAI Rate limit exceeded for sentiment analysis.")
            return "Sorry, I'm currently facing high demand and cannot perform sentiment analysis right now."
        except AuthenticationError:
             logger.error("OpenAI Authentication error during sentiment analysis.", exc_info=True)
             return "Sorry, there's an issue with my authentication for sentiment analysis."
        except APIError as e:
            logger.error(f"OpenAI API error during sentiment analysis: {e.status_code} - {e.response}", exc_info=True)
            return "Sorry, an API error occurred during sentiment analysis."
        except Exception as e:
            logger.error(f"An unexpected error occurred during sentiment analysis: {e}", exc_info=True)
            return "Sorry, an unexpected error occurred during sentiment analysis."

    # Exemplo: Gerar uma resposta de conversa (placeholder)
    # chat_history seria uma lista de dicionários {"role": "user"|"assistant", "content": "..."}
    # user_db seria o objeto User do banco de dados para contexto (opcional)
    def generate_response(self, chat_history: List[Dict[str, str]], user: Optional[Any] = None) -> Optional[str]:
        """
        Gera uma resposta de conversa usando a API OpenAI.
        chat_history é uma lista de mensagens no formato [{"role": "...", "content": "..."}].
        Retorna a string de resposta ou None.
        """
        if self.client is None:
            logger.warning("OpenAI client not initialized. Cannot generate conversation response.")
            return None

        # TODO: Ajustar o prompt do sistema e a estrutura das mensagens
        messages = [{"role": "system", "content": "You are a helpful cryptocurrency assistant bot. Keep your responses concise and informative."}] + chat_history

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo", # Ou outro modelo
                messages=messages,
                max_tokens=150 # Limita o tamanho da resposta
            )
            if response.choices and response.choices[0].message.content:
                response_text = response.choices[0].message.content.strip()
                logger.debug(f"Generated conversation response: {response_text[:100]}...")
                return response_text
            else:
                logger.warning("OpenAI conversation response returned no content.")
                return None

        except RateLimitError:
            logger.warning("OpenAI Rate limit exceeded for conversation.")
            return "Sorry, I'm currently facing high demand and cannot chat right now."
        except AuthenticationError:
             logger.error("OpenAI Authentication error during conversation.", exc_info=True)
             return "Sorry, there's an issue with my authentication for conversation."
        except APIError as e:
            logger.error(f"OpenAI API error during conversation: {e.status_code} - {e.response}", exc_info=True)
            return "Sorry, an API error occurred during conversation."
        except Exception as e:
            logger.error(f"An unexpected error occurred during conversation: {e}", exc_info=True)
            return "Sorry, an unexpected error occurred during conversation."


# TODO: Implementar IntentRecognizer class se necessário.
# class IntentRecognizer:
#     def __init__(self, openai_client: Optional[OpenAIClient]):
#         self.openai_client = openai_client
#         # TODO: Inicializar modelo de reconhecimento de intenção se usar um local ou outro serviço
#         logger.info("IntentRecognizer initialized.")

#     def recognize(self, text: str, chat_history: List[Dict[str, str]]) -> str:
#         """
#         Reconhece a intenção do usuário a partir do texto da mensagem.
#         Retorna uma string representando a intenção (ex: 'get_price', 'set_alert', 'chat').
#         """
#         if self.openai_client and hasattr(self.openai_client, 'analyze_intent'): # Assumindo um método analyze_intent no OpenAIClient
#             try:
#                 # TODO: Usar OpenAI para analisar a intenção
#                 # intent = self.openai_client.analyze_intent(text, chat_history)
#                 # return intent or 'unknown' # Retorna 'unknown' se não reconhecer
#                 pass # Placeholder
#             except Exception as e:
#                 logger.error(f"Error using OpenAI for intent recognition: {e}", exc_info=True)
#                 return 'unknown' # Fallback para 'unknown' em caso de erro

#         # TODO: Implementar lógica de reconhecimento de intenção alternativa se OpenAI não estiver disponível
#         # Lógica simples baseada em palavras-chave ou regex
#         if any(cmd in text.lower() for cmd in ['price', 'quote', 'valor']):
#              return 'get_price'
#         if any(cmd in text.lower() for cmd in ['alert', 'notify', 'avise']):
#              return 'set_alert'
#         # Adicionar outras regras

#         return 'chat' # Intenção padrão para conversa se não for comando conhecido ou intenção específica


#     def extract_symbol(self, text: str) -> Optional[str]:
#         """Extrai um símbolo de criptomoeda do texto da mensagem."""
#         # TODO: Implementar lógica de extração de símbolo (regex, lista de símbolos comuns, etc.)
#         # Exemplo simples de regex para algo como BTCUSDT
#         match = re.search(r'\b[A-Z]{3,5}USDT\b', text.upper())
#         if match:
#             return match.group(0)
#         return None