import os
import json
import shlex
from pathlib import Path
import aiofiles
from fastapi import ( 
    FastAPI, HTTPException, WebSocket, 
    WebSocketDisconnect, status, 
    UploadFile, File, Depends, Query
)
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel, constr
from typing import List, Any, Dict

# Importa tudo do nosso novo arquivo auth.py
from auth import (
    User,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_current_user_ws,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# Importações para Execução Segura
import docker # A biblioteca do Docker
import docker.errors # Para capturar erros
from docker.types import LogConfig, DeviceRequest # (Necessário para logs)

# --- Configuração ---

ARQUIVOS_DIR = Path("/app/Arquivos") 
NOTEBOOK_DIR = ARQUIVOS_DIR / "Notebooks"
WORKSPACE_DIR = ARQUIVOS_DIR / "Uploads"

NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True) 
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Pega o caminho do host para o sandbox
HOST_WORKSPACE = os.getenv("HOST_WORKSPACE_PATH")
if not HOST_WORKSPACE:
    print("ALERTA: HOST_WORKSPACE_PATH não está definido. Montagem de dados pode falhar.")

APP_TITLE = os.getenv("APP_TITLE", "Pegasus")
ENV_MODE = os.getenv("ENV_MODE", "production")

# ATUALIZADO: Configuração condicional
app_config = {"title": APP_TITLE}
if ENV_MODE == "production":
    # Só usa o root_path em produção (VPS com Traefik)
    app_config["root_path"] = "/api"

app = FastAPI(**app_config)

# CORS condicional
origins = [
    "https://pegasus.ovictorfarias.com.br" # Produção
]
if ENV_MODE == "development":
    # Adiciona o localhost SÓ em desenvolvimento
    origins.append("http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# ATUALIZADO: Inicializa o cliente Docker
# Ele vai se conectar automaticamente ao /var/run/docker.sock
try:
    docker_client = docker.from_env()
    # Verifica se a imagem base existe. Se não, baixa ela.
    docker_client.images.pull("python:3.11-slim")
    print("Cliente Docker conectado e imagem python:3.11-slim pronta.")
except Exception as e:
    print(f"ERRO: Não foi possível conectar ao Docker. {e}")
    print("O Docker está rodando? O docker.sock está montado?")
    docker_client = None

# Gerenciador de Kernels (Contêineres)
# Esta é a nossa "memória" de quais usuários estão rodando quais contêineres.
kernel_sessions: Dict[str, docker.models.containers.Container] = {}

# --- Modelos de Dados (Pydantic) ---

class StatusResponse(BaseModel):
    status: str
    app_title: str

# Modelo para a lista de notebooks
class NotebookInfo(BaseModel):
    filename: str
    # (poderíamos adicionar 'last_modified' no futuro)

# Modelo para o *conteúdo* de um notebook
# É flexível para aceitar qualquer estrutura JSON válida de .ipynb
class NotebookContent(BaseModel):
    cells: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    nbformat: int
    nbformat_minor: int

# ATUALIZADO: Novo modelo de dados para a lista de arquivos
class FileInfo(BaseModel):
    filename: str
    size_kb: float # Tamanho em kilobytes

# ATUALIZADO: Novo modelo para receber o 'novo nome'
class RenameRequest(BaseModel):
    new_filename: str # Garante que o nome não seja vazio

    class Config:
        min_length = 1
    
    # new_filename: constr(min_length=1) #versão antiga

# --- Funções de Ajuda (Segurança) ---

def get_safe_path(filename: str) -> Path:
    """
    Valida e retorna um caminho seguro para um arquivo de notebook.
    Previne ataques de "Path Traversal" (ex: "lendo ../../etc/passwd")
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        # ATUALIZADO: Rejeita nomes de arquivo inválidos
        raise HTTPException(
            status_code=400, detail="Nome de arquivo inválido."
        )

    # Garante que o arquivo termina com .ipynb
    if not filename.endswith(".ipynb"):
         filename += ".ipynb"

    # Resolve o caminho completo do arquivo
    safe_path = (NOTEBOOK_DIR / filename).resolve()

    # Verifica se o caminho resolvido ainda está DENTRO do nosso diretório
    if NOTEBOOK_DIR.resolve() not in safe_path.parents:
        raise HTTPException(
            status_code=403, detail="Acesso negado."
        )

    return safe_path

# ATUALIZADO: Nova função de ajuda para o workspace
def get_safe_workspace_path(filename: str) -> Path:
    """
    Valida e retorna um caminho seguro para um arquivo no WORKSPACE.
    Previne Path Traversal.
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400, detail="Nome de arquivo inválido."
        )
    
    safe_path = (WORKSPACE_DIR / filename).resolve()
    
    if WORKSPACE_DIR.resolve() not in safe_path.parents:
        raise HTTPException(
            status_code=403, detail="Acesso negado ao workspace."
        )
            
    return safe_path

# ATUALIZADO: Novo endpoint para RENOMEAR um notebook
@app.patch("/v1/notebooks/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_notebook(filename: str, request: RenameRequest):
    """
    Renomeia um arquivo de notebook.
    """
    old_path = get_safe_path(filename)
    new_path = get_safe_path(request.new_filename)

    if not old_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook original não encontrado."
        )
    if new_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um notebook com esse nome."
        )
    
    try:
        old_path.rename(new_path) # Renomeia o arquivo no disco
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao renomear o notebook: {e}"
        )

# --- Novo Endpoint de Autenticação ---

@app.post("/v1/auth/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Gera um token JWT para o usuário.
    O frontend envia dados de formulário (username, password).
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Endpoints da API HTTP ---

@app.get("/v1/status", response_model=StatusResponse)
def get_status():
    return StatusResponse(status="ativo", app_title=APP_TITLE)

# ATUALIZADO: Novo endpoint para listar notebooks
@app.get("/v1/notebooks", response_model=List[NotebookInfo])
async def list_notebooks():
    """
    Lista todos os arquivos .ipynb no diretório de notebooks.
    """
    notebooks = []
    for f in NOTEBOOK_DIR.glob("*.ipynb"):
        notebooks.append(NotebookInfo(filename=f.name))
    return notebooks

# ATUALIZADO: Novo endpoint para ler um notebook
@app.get("/v1/notebooks/{filename}", response_model=NotebookContent)
async def get_notebook(filename: str):
    """
    Lê e retorna o conteúdo JSON de um arquivo .ipynb específico.
    """
    safe_path = get_safe_path(filename)

    if not safe_path.exists():
        raise HTTPException(
            status_code=404, detail="Notebook não encontrado."
        )

    try:
        # Abre o arquivo de forma assíncrona
        async with aiofiles.open(safe_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        # Converte o conteúdo de texto para JSON
        data = json.loads(content)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Erro ao ler o notebook: {e}"
        )

# ATUALIZADO: Novo endpoint para salvar/criar um notebook
@app.put("/v1/notebooks/{filename}", status_code=204)
async def save_notebook(filename: str, content: NotebookContent):
    """
    Salva (sobrescreve) o conteúdo de um notebook.
    Cria um novo se o nome de arquivo não existir.
    """
    safe_path = get_safe_path(filename)
    try:
        content_dict = content.model_dump()
        json_content = json.dumps(content_dict, indent=2)
        async with aiofiles.open(safe_path, mode='w', encoding='utf-8') as f:
            await f.write(json_content)
            return
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Erro ao salvar o notebook: {e}"
        )

# ATUALIZADO: Novo endpoint para EXCLUIR um notebook
@app.delete("/v1/notebooks/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(filename: str):
    """
    Exclui um arquivo .ipynb específico do diretório.
    """
    safe_path = get_safe_path(filename)
    
    if not safe_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Notebook não encontrado."
        )
    
    try:
        safe_path.unlink() # O comando 'unlink' do pathlib é como 'excluir'
        return
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir o notebook: {e}"
        )

@app.get("/v1/files", response_model=List[FileInfo])
async def list_files_in_workspace():
    """
    Lista todos os arquivos no diretório de workspace.
    """
    files = []
    for f in WORKSPACE_DIR.glob("*"):
        if f.is_file(): # Ignora subdiretórios por enquanto
            size_kb = round(f.stat().st_size / 1024, 2)
            files.append(FileInfo(filename=f.name, size_kb=size_kb))
    return files

@app.post("/v1/files/upload", response_model=FileInfo)
async def upload_file_to_workspace(file: UploadFile = File(...)):
    """
    Recebe um arquivo e o salva no diretório de workspace.
    """
    safe_path = get_safe_workspace_path(file.filename)
    
    try:
        # Salva o arquivo de forma assíncrona
        async with aiofiles.open(safe_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024): # Lê em chunks de 1MB
                await f.write(chunk)
        
        size_kb = round(safe_path.stat().st_size / 1024, 2)
        return FileInfo(filename=file.filename, size_kb=size_kb)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar o arquivo: {e}"
        )

# ATUALIZADO: Novo endpoint para BAIXAR um arquivo
@app.get("/v1/files/download/{filename}")
async def download_file_from_workspace(filename: str):
    """
    Fornece um arquivo do workspace para download.
    """
    safe_path = get_safe_workspace_path(filename)

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado no workspace."
        )
    
    # FileResponse usa o sistema de 'streaming' do FastAPI
    # para enviar o arquivo de forma eficiente
    return FileResponse(
        path=safe_path,
        filename=filename, # Sugere o nome do arquivo para o navegador
        media_type='application/octet-stream' # Força o 'download'
    )

# ATUALIZADO: Nova API para Baixar o Notebook (Recurso #3)
@app.get("/v1/notebooks/download/{filename}")
async def download_notebook_file(filename: str):
    """
    Fornece um arquivo .ipynb para download.
    """
    safe_path = get_safe_path(filename)

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook não encontrado."
        )
    
    return FileResponse(
        path=safe_path,
        filename=filename,
        media_type='application/x-ipynb+json' # Media type para notebooks
    )

# ATUALIZADO: Nova API para Excluir Arquivo (Recurso #1)
@app.delete("/v1/files/delete/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_from_workspace(filename: str):
    """
    Exclui um arquivo do diretório de workspace.
    """
    safe_path = get_safe_workspace_path(filename)

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado no workspace."
        )
    
    try:
        safe_path.unlink() # Exclui o arquivo
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir o arquivo: {e}"
        )

# --- Endpoint de WebSocket (Executor) ---
@app.websocket("/v1/execute")
async def websocket_execute(
    websocket: WebSocket,
    token: str = Query(...) 
):
    """
    Endpoint WebSocket para execução de código SEGURA em um contêiner Docker.
    """
    
    # 1. Autenticar o Usuário
    try:
        user = await get_current_user_ws(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept() 
    
    if not docker_client:
        await websocket.send_json({"type": "stderr", "content": "Erro Crítico: O servidor não está conectado ao Docker."})
        await websocket.close()
        return

    if not HOST_WORKSPACE: 
        await websocket.send_json({"type": "stderr", "content": "Erro Crítico: O servidor não está configurado com HOST_WORKSPACE_PATH."})
        await websocket.close()
        return

    # --- Lógica de Kernel Persistente ---
    
    kernel_id = user.username # Vamos usar o username como ID do kernel
    container: docker.models.containers.Container = None

    try:
        # 2. Encontrar ou Criar o Kernel
        if kernel_id in kernel_sessions:
            # Usuário já tem um kernel, vamos reutilizá-lo
            container = kernel_sessions[kernel_id]
            print(f"Reconectando ao kernel para o usuário: {kernel_id}")
            # Garante que o contêiner ainda está rodando
            container.reload() 
            if container.status != "running":
                raise Exception("O kernel foi parado inesperadamente.")
            
        else:
            # --- Lógica de Alocação Adaptativa ---
            print(f"Criando novo kernel para o usuário: {kernel_id}...")
            
            # Prepara os volumes e working_dir
            volumes_to_mount = {}
            working_dir_path = "/"
            if HOST_WORKSPACE:
                host_path_str = str(HOST_WORKSPACE).replace("\\", "/")
                if host_path_str.startswith("C:"):
                    host_path_str = "/" + host_path_str[0].lower() + host_path_str[2:]
                volumes_to_mount[host_path_str] = { 'bind': '/data', 'mode': 'rw' }
                working_dir_path = "/data/Uploads"
            
            # Define a configuração COMUM do kernel
            common_config = {
                "image": "python:3.11-slim",
                "command": ["sleep", "infinity"], 
                "detach": True, 
                "mem_limit": "4g", 
                "volumes": volumes_to_mount,
                "working_dir": working_dir_path,
                "auto_remove": True,
            }
            
            # Define a configuração IDEAL (com GPU)
            gpu_config = {
                "device_requests": [
                    DeviceRequest(count=-1, capabilities=[['gpu']])
                ]
            }

            container = None
            try:
                # TENTATIVA 1: Alocar com GPU
                print(f"Tentando alocar kernel com GPU para {kernel_id}...")
                container = docker_client.containers.run(
                    **common_config,
                    **gpu_config
                )
                print(f"Kernel {container.short_id} criado com SUCESSO (com GPU).")

            except docker.errors.APIError as e:
                # ERRO! Vamos verificar se é o erro de GPU que esperamos.
                if "could not select device driver" in str(e):
                    # É o erro da GPU! Vamos tentar de novo sem ela.
                    print(f"Falha ao alocar GPU (NVIDIA Toolkit ausente?). Erro: {e}")
                    print(f"Tentando alocar kernel em modo fallback (somente CPU) para {kernel_id}...")
                    
                    # TENTATIVA 2: Alocar com CPU Apenas
                    container = docker_client.containers.run(
                        **common_config
                    )
                    print(f"Kernel {container.short_id} criado com SUCESSO (somente CPU).")
                else:
                    # Foi um erro de API diferente. Devemos falhar.
                    raise e
            
            # Salva o kernel (seja CPU ou GPU) na nossa "memória"
            kernel_sessions[kernel_id] = container
            await websocket.send_json({"type": "stdout", "content": "Kernel conectado e pronto."})
            

        # 3. Loop de Execução (escuta por código)
        while True:
            data = await websocket.receive_json()
            code = data.get("code")
            if code is None:
                continue

            output = {}
            
            # Prepara o comando (Shell ou Python)
            command_to_run = []
            code_to_run = code.strip()

            cell_type = "python" # Assume Python por padrão
            for line in code_to_run.splitlines():
                stripped_line = line.strip()
                if not stripped_line: # Pula linhas em branco
                    continue
                if stripped_line.startswith("#"): # Pula comentários
                    continue
                
                # Esta é a primeira linha de código real
                if stripped_line.startswith("!"):
                    cell_type = "shell"
                
                # Já descobrimos o tipo, podemos parar de ler
                break 
            
            # Agora, constrói o comando baseado no tipo da célula
            if cell_type == "shell":
                shell_commands = []
                for line in code_to_run.splitlines():
                    stripped_line = line.strip()
                    if stripped_line.startswith("!"):
                        shell_commands.append(stripped_line[1:].strip())
                
                full_shell_command = " && ".join(shell_commands)                
                
                final_command_string = f"export DEBIAN_FRONTEND=noninteractive && {full_shell_command}"
                command_to_run = ["/bin/sh", "-c", final_command_string]
            
            else:
                # É uma célula Python.
                safe_code = shlex.quote(code_to_run)                
                command_to_run = ["/bin/sh", "-c", f"python -c {safe_code}"]
            
            try:
                # 4. EXECUTAR DENTRO do contêiner persistente
                exec_result = container.exec_run(
                    cmd=command_to_run,
                    demux=True 
                )
                
                # 5. Coletar a Saída
                exit_code = exec_result.exit_code
                stdout = exec_result.output[0].decode('utf-8').strip() if exec_result.output[0] else ""
                stderr = exec_result.output[1].decode('utf-8').strip() if exec_result.output[1] else ""

                full_output = ""
                
                if stdout:
                    full_output += stdout
                if stderr:
                    if full_output:
                        full_output += "\n"
                    full_output += stderr
                
                # Verifica se o timeout foi atingido
                if exit_code == 0:
                    output = {"type": "stdout", "content": full_output}
                else:
                    output = {"type": "stderr", "content": full_output}

            except Exception as e:
                output = {"type": "stderr", "content": f"Erro inesperado no 'exec_run': {e}"}
            
            # 6. Envia a saída da célula de volta
            await websocket.send_json(output)
            
            # 7. Envia o aviso de filesystem_update
            await websocket.send_json({
                "type": "filesystem_update",
                "content": "Execução concluída, atualize os arquivos."
            })

    except WebSocketDisconnect:
        print(f"Cliente WebSocket desconectado: {kernel_id}")
    except Exception as e:
        print(f"Erro no WebSocket ou Kernel: {e}")
        try:
            await websocket.close(code=1011, reason=f"Erro: {e}")
        except:
            pass # A conexão pode já estar morta
    finally:
        # 8. Limpeza (Destruir o Kernel)
        # Quando o usuário desconecta (ou ocorre um erro),
        # paramos e removemos seu contêiner.
        if kernel_id in kernel_sessions:
            container_to_remove = kernel_sessions.pop(kernel_id)
            try:
                print(f"Destruindo kernel {container_to_remove.short_id} para {kernel_id}...")
                container_to_remove.remove(force=True)
                print(f"Kernel {container_to_remove.short_id} destruído.")
            except docker.errors.NotFound:
                print("Kernel já havia sido removido.")
            except Exception as e:
                print(f"Erro ao tentar remover o kernel {container_to_remove.short_id}: {e}")