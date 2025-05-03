import logging
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import sessionmaker, relationship, scoped_session, joinedload
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime # <-- Importar datetime aqui
from typing import Optional, List # <-- Importa List também

logger = logging.getLogger(__name__)

# Configuração básica de logging, apenas para garantir no contexto do módulo
# NÍVEL DEBUG PARA DIAGNOSTICO - Mantenha assim por enquanto
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

Base = declarative_base()

# Definição dos Modelos
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    # Relacionamento com CryptoPreference
    preferences = relationship("CryptoPreference", back_populates="user") # Um usuário tem várias preferências

class CryptoPreference(Base):
    __tablename__ = 'crypto_preferences'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False) # Chave estrangeira para o usuário
    symbol = Column(String, nullable=False) # Símbolo da criptomoeda (ex: BTC)
    is_favorite = Column(Boolean, default=False) # Marcado como favorito
    high_alert = Column(Float) # Preço para alerta de alta
    low_alert = Column(Float) # Preço para alerta de baixa
    last_alert_triggered_at = Column(DateTime) # Timestamp do último alerta disparado
    last_alert_price = Column(Float) # Preço no momento do último alerta disparado

    # Relacionamento com User
    user = relationship("User", back_populates="preferences") # Uma preferência pertence a um usuário

    # Restrição de unicidade para garantir que um usuário só tenha uma preferência por símbolo
    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='_user_symbol_uc'),)


class DatabaseManager:
    def __init__(self, db_url: str = 'sqlite:///./database.db'):
        """
        Inicializa o DatabaseManager e conecta ao banco de dados.
        :param db_url: URL de conexão do banco de dados.
                       Ex: 'sqlite:///./database.db' para SQLite local.
        """
        self.engine = create_engine(db_url)
        # Testar a conexão
        try:
            with self.engine.connect() as connection:
                logger.debug("Database engine created and connection tested successfully.")
        except Exception as e:
            logger.critical(f"Failed to connect to the database: {e}", exc_info=True)
            raise # Re-lança a exceção, pois o DB é crítico

        # Criar todas as tabelas se não existirem
        # COMENTADO: Assumindo que as tabelas são criadas externamente (ex: via Alembic)
        # OU que este código é rodado uma única vez na primeira execução para criar a estrutura inicial.
        # Se estiver rodando em um ambiente que recria o container (como alguns setups do Replit)
        # e você quer que as tabelas sejam criadas automaticamente a cada run se não existirem,
        # descomente a linha abaixo. CUIDADO: isso pode apagar dados se o engine for recriado para um DB vazio.
        # Base.metadata.create_all(self.engine)
        logger.debug("Skipping automatic table creation. Assumes tables are managed externally or created manually after first run.")


        # Configurar a sessão
        # Usamos scoped_session para gerenciar sessões em um ambiente multi-threaded como um bot
        session_factory = sessionmaker(bind=self.engine)
        self.SessionLocal = scoped_session(session_factory)

        logger.info("DatabaseManager initialized.")

    def get_session(self):
        """Retorna uma nova sessão de banco de dados."""
        return self.SessionLocal()

    def get_or_create_user(self, telegram_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None):
        """
        Busca um usuário pelo ID do Telegram. Se não existir, cria um novo.
        Retorna o objeto User.
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.telegram_id == str(telegram_id)).first() # Garante que telegram_id é string

            if not user:
                logger.debug(f"User with telegram_id {telegram_id} not found. Creating new user.")
                user = User(telegram_id=str(telegram_id), username=username, first_name=first_name, last_name=last_name)
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(f"New user created with telegram_id: {telegram_id}")
            else:
                logger.debug(f"Existing user {telegram_id} found.")
                # Opcional: Atualizar username/first_name/last_name se mudaram
                # user.username = username
                # user.first_name = first_name
                # user.last_name = last_name
                # session.commit() # Commit se atualizar campos

            return user
        except Exception as e:
            session.rollback()
            logger.error(f"Error getting or creating user {telegram_id}: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    def log_message(self, telegram_id: str, role: str, content: str, chat_id: str, message_telegram_id: Optional[int] = None) -> None:
        """
        Registra uma mensagem no banco de dados associada a um usuário.
        """
        session = self.get_session()
        try:
            # Primeiro, garanta que o usuário existe
            user = self.get_or_create_user(telegram_id) # get_or_create_user já fecha sua sessão, então buscamos o user novamente na nova sessão

            # Na nova sessão:
            user_in_this_session = session.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if user_in_this_session:
                # TODO: Implementar a tabela de logs e o modelo Message se necessário
                # Por enquanto, apenas registramos no log.
                # Uma tabela 'messages' seria necessária para armazenar isso no DB.
                # Ex: new_message = Message(user_id=user_in_this_session.id, role=role, content=content, chat_id=str(chat_id), message_telegram_id=message_telegram_id, timestamp=datetime.now())
                # session.add(new_message)
                # session.commit()
                # logger.debug(f"Logged user message for user {telegram_id} in chat {chat_id}.")
                pass # Apenas passa se a tabela de logs não for implementada no DB
            else:
                logger.error(f"User {telegram_id} not found in this session after get_or_create_user. Cannot log message in DB.")

        except Exception as e:
            session.rollback()
            logger.error(f"Error logging message for user {telegram_id}: {e}", exc_info=True)
            # Não relança, pois falha no log não deve parar o bot
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    def add_or_update_preference(self, telegram_id: str, symbol: str, is_favorite: Optional[bool] = None, high_alert: Optional[float] = None, low_alert: Optional[float] = None):
        """
        Adiciona ou atualiza uma preferência de criptomoeda para um usuário.
        Se o alerta high/low for ATUALIZADO, zera last_alert_triggered_at e last_alert_price.
        Retorna o objeto CryptoPreference.
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if not user:
                # Isso não deveria acontecer se get_or_create_user for chamado antes, mas para segurança:
                logger.error(f"User {telegram_id} not found when trying to add/update preference for {symbol}. Cannot proceed.")
                return None # Retorna None se o usuário não existir

            # Busca a preferência existente para este usuário e símbolo
            preference = session.query(CryptoPreference).filter(
                CryptoPreference.user_id == user.id,
                CryptoPreference.symbol == symbol.upper() # Garante que o símbolo está em maiúsculas
            ).first()

            # Flag para verificar se algum alerta foi atualizado
            alert_value_updated = False

            if not preference:
                logger.debug(f"Preference for user {telegram_id}, symbol {symbol.upper()} not found. Creating new preference.")
                preference = CryptoPreference(user_id=user.id, symbol=symbol.upper())
                session.add(preference)
                # Se é uma nova preferência e tem alertas, considerar alerta atualizado
                if high_alert is not None or low_alert is not None:
                    alert_value_updated = True


            # --- Lógica para verificar se alertas foram ATUALIZADOS com um NOVO valor ---
            # Verificamos se um NOVO valor para high_alert foi fornecido E é diferente do valor atual NO BANCO.
            if high_alert is not None and (preference.high_alert is None or preference.high_alert != high_alert):
                logger.debug(f"High alert value for user {telegram_id}, symbol {symbol.upper()} provided and is different from current ({preference.high_alert} != {high_alert}). Marking for reset.")
                preference.high_alert = high_alert # Atualiza o valor do alerta
                alert_value_updated = True # Marca que um valor de alerta foi atualizado


            # Verificamos se um NOVO valor para low_alert foi fornecido E é diferente do valor atual NO BANCO.
            if low_alert is not None and (preference.low_alert is None or preference.low_alert != low_alert):
                logger.debug(f"Low alert value for user {telegram_id}, symbol {symbol.upper()} provided and is different from current ({preference.low_alert} != {low_alert}). Marking for reset.")
                preference.low_alert = low_alert # Atualiza o valor do alerta
                alert_value_updated = True # Marca que um valor de alerta foi atualizado


            # --- Resetar histórico de throttling SE um valor de alerta foi atualizado ---
            if alert_value_updated:
                logger.debug(f"Resetting throttling history for user {telegram_id}, symbol {symbol.upper()} due to alert value update.")
                preference.last_alert_triggered_at = None
                preference.last_alert_price = None


            # Se is_favorite foi fornecido, atualiza (isso não reseta o histórico de alerta)
            if is_favorite is not None:
                preference.is_favorite = is_favorite


            session.commit()
            session.refresh(preference)
            logger.debug(f"Preference for user {telegram_id}, symbol {symbol.upper()} updated/created. High: {preference.high_alert}, Low: {preference.low_alert}, Fav: {preference.is_favorite}.")
            return preference
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding or updating preference for user {telegram_id}, symbol {symbol.upper()}: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    def get_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, is_favorite: Optional[bool] = None, with_alerts: bool = False) -> List[CryptoPreference]: # Usando type hint para a classe dummy
        """
        Busca preferências de criptomoeda para um usuário.
        Pode filtrar por símbolo e/ou se é favorito.
        Se with_alerts=True, filtra apenas preferências com high_alert ou low_alert definidos.
        Retorna uma lista de objetos CryptoPreference.
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if not user:
                logger.debug(f"User {telegram_id} not found when getting preferences. Returning empty list.")
                return [] # Retorna lista vazia se o usuário não existir

            query = session.query(CryptoPreference).filter(CryptoPreference.user_id == user.id)

            if symbol:
                query = query.filter(CryptoPreference.symbol == symbol.upper()) # Filtra por símbolo (case-insensitive na busca)

            if is_favorite is not None:
                query = query.filter(CryptoPreference.is_favorite == is_favorite)

            if with_alerts:
                # Filtra onde high_alert IS NOT NULL OU low_alert IS NOT NULL
                query = query.filter(
                    (CryptoPreference.high_alert != None) | (CryptoPreference.low_alert != None)
                )

            preferences = query.all()
            logger.debug(f"Found {len(preferences)} preferences for user {telegram_id} with filters.")
            return preferences
        except Exception as e:
            session.rollback()
            logger.error(f"Error getting preferences for user {telegram_id}: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    def clear_user_crypto_preferences(self, telegram_id: str, symbol: Optional[str] = None, clear_favorites: bool = True, clear_alerts: bool = True) -> bool:
        """
        Limpa (reseta para None) alertas e/ou status de favorito para a preferência de um usuário.
        Se symbol for None, limpa para todas as preferências do usuário.
        Retorna True se alguma preferência foi modificada, False caso contrário.
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if not user:
                logger.debug(f"User {telegram_id} not found when clearing preferences. No preferences cleared.")
                return False # Retorna False se o usuário não existir

            query = session.query(CryptoPreference).filter(CryptoPreference.user_id == user.id)

            if symbol:
                query = query.filter(CryptoPreference.symbol == symbol.upper()) # Filtra por símbolo

            preferences_to_update = query.all()
            modified_count = 0

            for pref in preferences_to_update:
                updated = False
                if clear_favorites and pref.is_favorite:
                    pref.is_favorite = False
                    updated = True
                if clear_alerts: # Se clear_alerts é True, zeramos high_alert, low_alert E o histórico de throttling
                    if pref.high_alert is not None or pref.low_alert is not None or pref.last_alert_triggered_at is not None or pref.last_alert_price is not None:
                        pref.high_alert = None
                        pref.low_alert = None
                        pref.last_alert_triggered_at = None # Zera histórico de throttling
                        pref.last_alert_price = None       # Zera histórico de throttling
                        updated = True

                if updated:
                    modified_count += 1

            if modified_count > 0:
                session.commit()
                logger.debug(f"Cleared preferences for user {telegram_id}, symbol: {symbol.upper() if symbol else 'all'}. Cleared {modified_count} preferences.")
                return True
            else:
                logger.debug(f"No preferences found or cleared for user {telegram_id}, symbol: {symbol.upper() if symbol else 'all'} with specified criteria.")
                return False

        except Exception as e:
            session.rollback()
            logger.error(f"Error clearing preferences for user {telegram_id}, symbol: {symbol.upper() if symbol else 'all'}: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    # Método usado pelo PriceMonitor para obter todas as preferências com alertas configurados
    def get_all_user_preferences_for_monitoring(self) -> List[CryptoPreference]: # Usando type hint para a classe dummy
        """
        Busca todas as preferências de todos os usuários que possuem alertas (high_alert ou low_alert) definidos.
        Inclui o objeto User relacionado para acessar o telegram_id.
        Retorna uma lista de objetos CryptoPreference com User carregado.
        """
        session = self.get_session()
        try:
            # Junte CryptoPreference com User e filtre onde high_alert OU low_alert é NOT NULL
            # use joinedload para carregar o relacionamento 'user' eficientemente
            preferences = session.query(CryptoPreference).options(joinedload(CryptoPreference.user)).filter(
                (CryptoPreference.high_alert != None) | (CryptoPreference.low_alert != None)
            ).all()
            # Nota: Na classe dummy, usamos User diretamente. Na implementação real com SQLAlchemy,
            # o relacionamento 'user' no objeto CryptoPreference carregado conterá o objeto User.
            logger.debug(f"Found {len(preferences)} active alert preferences for monitoring.")
            return preferences
        except Exception as e:
            session.rollback()
            logger.error(f"Error getting all user preferences for monitoring: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    def update_alert_triggered_at(self, preference_id: int, timestamp: datetime, triggered_price: float) -> bool:
        """
        Atualiza last_alert_triggered_at e last_alert_price para uma preferência específica.
        Retorna True se atualizado com sucesso, False caso contrário.
        """
        session = self.get_session()
        try:
            preference = session.query(CryptoPreference).filter(CryptoPreference.id == preference_id).first()
            if preference:
                preference.last_alert_triggered_at = timestamp
                preference.last_alert_price = triggered_price # Salva o preço que disparou o alerta
                session.commit()
                logger.debug(f"Updated last_alert_triggered_at and last_alert_price for preference ID {preference_id} to {timestamp} at price {triggered_price}.")
                return True
            else:
                logger.warning(f"Preference with ID {preference_id} not found for update.")
                return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating last_alert_triggered_at for preference ID {preference_id}: {e}", exc_info=True)
            raise # Re-lança a exceção
        finally:
            # CORRIGIDO: Chamar remove() no objeto scoped_session
            self.SessionLocal.remove()

    # --- NOVO MÉTODO: Obter todos os IDs de usuário ---
    def get_all_user_telegram_ids(self) -> List[str]:
        """
        Busca os IDs do Telegram de todos os usuários registrados no banco de dados.
        Retorna uma lista de strings (IDs do Telegram).
        """
        session = self.get_session()
        try:
            # Consulta a coluna telegram_id da tabela User
            user_ids = session.query(User.telegram_id).all()
            # O resultado de all() é uma lista de tuplas (telegram_id,),
            # usamos uma list comprehension para extrair apenas os IDs.
            telegram_ids = [uid[0] for uid in user_ids]
            logger.debug(f"Found {len(telegram_ids)} user Telegram IDs in DB.")
            return telegram_ids
        except Exception as e:
            session.rollback()
            logger.error(f"Error getting all user Telegram IDs: {e}", exc_info=True)
            # Retorna uma lista vazia em caso de erro para que o broadcast não quebre
            return []
        finally:
            self.SessionLocal.remove() # Fecha a sessão
