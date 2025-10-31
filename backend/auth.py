import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

# --- Configuração ---
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Contexto de Senha (usamos bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Define o "esquema" de login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# --- Funções de Segurança ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Gera um hash bcrypt da senha."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um novo token JWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Lógica de "Usuário" (simples, baseada no .env) ---

class User:
    """Modelo de usuário simples."""
    def __init__(self, username: str):
        self.username = username

# HASH da senha do .env para comparação segura
# Em um app real, isso viria de um banco de dados
APP_USERNAME = os.getenv("APP_USERNAME")
# ATENÇÃO: Para esta sprint, faremos a comparação em texto plano
# como pedido. Não é o ideal, mas cumpre o requisito do .env.
APP_PASSWORD = os.getenv("APP_PASSWORD")

def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Verifica se o usuário e senha correspondem aos do .env.
    """
    if username == APP_USERNAME and password == APP_PASSWORD:
        return User(username=username)
    return None

# --- Dependências (para proteger rotas) ---

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Valida o token JWT e retorna o usuário.
    Usado para proteger rotas HTTP.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username != APP_USERNAME:
            raise credentials_exception
        return User(username=username)
    except JWTError:
        raise credentials_exception

async def get_current_user_ws(token: str) -> User:
    """
    Valida o token JWT recebido (via query param) pelo WebSocket.
    """
    # Reutiliza a mesma lógica de get_current_user,
    # mas pega o token de um lugar diferente.
    return await get_current_user(token)