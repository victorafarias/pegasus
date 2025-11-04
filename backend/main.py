import os
import json
import shlex 
import asyncio # Importa asyncio para tarefas concorrentes
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
from docker.types import LogConfig, DeviceRequest 

# --- Configuração ---
ARQUIVOS_DIR = Path("/app/Arquivos") 
NOTEBOOK_DIR = ARQUIVOS_DIR / "Notebooks"
WORKSPACE_DIR = ARQUIVOS_DIR / "Uploads"

NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True) 
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

HOST_WORKSPACE = os.getenv("HOST_WORKSPACE_PATH")
if not HOST_WORKSPACE:
    print("ALERTA: HOST_WORKSPACE_PATH não está definido. Montagem de dados pode falhar.")

APP_TITLE = os.getenv("APP_TITLE", "Pegasus")
ENV_MODE = os.getenv("ENV_MODE", "production")

app_config = {"title": APP_TITLE}
if ENV_MODE == "production":
    app_config["root_path"] = "/api"

app = FastAPI(**app_config)

origins = [
    "https://pegasus.ovictorfarias.com.br" # Produção
]
if ENV_MODE == "development":
    origins.append("http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

try:
    docker_client = docker.from_env()
    docker_client.images.pull("python:3.11-slim")
    print("Cliente Docker conectado e imagem python:3.11-slim pronta.")
except Exception as e:
    print(f"ERRO: Não foi possível conectar ao Docker. {e}")
    docker_client = None

kernel_sessions: Dict[str, docker.models.containers.Container] = {}

# --- Modelos de Dados (Pydantic) ---
class StatusResponse(BaseModel):
    status: str
    app_title: str

class NotebookInfo(BaseModel):
    filename: str

class NotebookContent(BaseModel):
    cells: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    nbformat: int
    nbformat_minor: int

class FileInfo(BaseModel):
    filename: str
    size_kb: float

class RenameRequest(BaseModel):
    new_filename: str 
    class Config:
        min_length = 1

# --- Funções de Ajuda (Segurança) ---
def get_safe_path(filename: str) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if not filename.endswith(".ipynb"):
         filename += ".ipynb"
    safe_path = (NOTEBOOK_DIR / filename).resolve()
    if NOTEBOOK_DIR.resolve() not in safe_path.parents:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    return safe_path

def get_safe_workspace_path(filename: str) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    safe_path = (WORKSPACE_DIR / filename).resolve()
    if WORKSPACE_DIR.resolve() not in safe_path.parents:
        raise HTTPException(status_code=403, detail="Acesso negado ao workspace.")
    return safe_path

# --- Funções Helper de Stats (Sprint 14) ---

async def stream_resource_stats(
    websocket: WebSocket, 
    container: docker.models.containers.Container
):
    """ Tarefa concorrente que transmite estatísticas (RAM/CPU) """
    try:
        stats_stream = docker_client.api.stats(
            container.id, 
            stream=True, 
            decode=True
        )
        
        print(f"Iniciando streaming de stats para o kernel {container.short_id}...")
        
        for stats in stats_stream:
            try:
                mem_stats = stats.get('memory_stats', {})
                ram_usage = mem_stats.get('usage', 0)
                ram_limit = mem_stats.get('limit', 0)

                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                            stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                               stats['precpu_stats']['system_cpu_usage']
                
                if 'online_cpus' in stats['cpu_stats']:
                    cpu_count = stats['cpu_stats']['online_cpus']
                else:
                    cpu_count = len(stats['cpu_stats']['cpu_usage']['percpu_usage'])

                cpu_percent = 0.0
                if system_delta > 0.0 and cpu_delta > 0.0:
                    cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
                
                await websocket.send_json({
                    "type": "resource_stats",
                    "content": {
                        "ram_usage": ram_usage,
                        "ram_limit": ram_limit,
                        "cpu_percent": round(cpu_percent, 2)
                    }
                })
            except (KeyError, ZeroDivisionError, TypeError) as e:
                print(f"Aviso de stats (ignorável): {e}")
                pass
            
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        print(f"Parando streaming de stats para o kernel {container.short_id}.")
        raise 
    except Exception as e:
        print(f"Erro no streaming de stats: {e}")
        try:
            await websocket.send_json({
                "type": "stderr", 
                "content": f"Monitoramento de recursos falhou: {e}"
            })
        except:
            pass # Socket pode estar morto

async def get_disk_stats(
    websocket: WebSocket, 
    container: docker.models.containers.Container
):
    """ Executa 'df' UMA VEZ e envia as estatísticas de disco. """
    try:
        cmd = ["df", "-Pk", "/data"]
        exec_instance = docker_client.api.exec_create(container.id, cmd=cmd, tty=False)
        exec_output_raw = docker_client.api.exec_start(exec_instance['Id'], tty=False, demux=True)
        
        # exec_start pode retornar None se não houver saída
        if exec_output_raw[0]:
            stdout = exec_output_raw[0].decode('utf-8').strip()
            lines = stdout.splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    disk_limit_kb = int(parts[1])
                    disk_usage_kb = int(parts[2])
                    
                    await websocket.send_json({
                        "type": "disk_stats",
                        "content": {
                            "disk_usage": disk_usage_kb * 1024, # Converte para bytes
                            "disk_limit": disk_limit_kb * 1024  # Converte para bytes
                        }
                    })
    except Exception as e:
        print(f"Erro ao obter stats de disco: {e}")
        pass

# --- Função Helper de Execução ---
async def run_cell_execution(
    websocket: WebSocket, 
    container: docker.models.containers.Container, 
    code: str
):
    """
    Executa o código da célula como uma tarefa separada,
    permitindo que a conexão principal do WebSocket continue ouvindo.
    """
    try:
        # Prepara o comando (Shell ou Python)
        command_to_run = []
        code_to_run = code.strip()
        cell_type = "python"
        
        for line in code_to_run.splitlines():
            stripped_line = line.strip()
            if not stripped_line: continue
            if stripped_line.startswith("#"): continue
            if stripped_line.startswith("!"):
                cell_type = "shell"
            break 
        
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
            safe_code = shlex.quote(code_to_run)
            command_to_run = ["/bin/sh", "-c", f"python -c {safe_code}"]
        
        # --- Lógica de Execução com STREAMING ---
        
        # 1. Criar a instância de execução
        exec_instance = docker_client.api.exec_create(
            container=container.id, 
            cmd=command_to_run,
            tty=True,
            stdout=True,
            stderr=True
        )
        exec_id = exec_instance.get('Id')

        # 2. Iniciar a execução e obter o fluxo (stream)
        output_stream = docker_client.api.exec_start(
            exec_id=exec_id, 
            stream=True,
            demux=False, 
            tty=True
        )
        
        # 3. Iterar sobre o fluxo de saída em tempo real
        for chunk in output_stream:
            output_line = chunk.decode('utf-8')
            await websocket.send_json({
                "type": "stream",
                "content": output_line
            })
            await asyncio.sleep(0.001) # Libera o loop de eventos

        # 4. Após o fim do fluxo, INSPECIONAR a execução
        inspect_data = docker_client.api.exec_inspect(exec_id)
        exit_code = inspect_data.get("ExitCode", 0)

        # 5. Envia uma mensagem final de "concluído"
        if exit_code == 0:
            await websocket.send_json({
                "type": "stdout", 
                "content": f"\n[Execução concluída com código {exit_code}]"
            })
        else:
            await websocket.send_json({
                "type": "stderr", 
                "content": f"\n[Execução falhou com código {exit_code}]"
            })

    except asyncio.CancelledError:
        # O 'restart_kernel' ou 'stop_execution' cancelou esta tarefa
        print("Execução da célula foi cancelada pelo usuário.")
        try:
            # Tenta parar a execução no contêiner (melhor esforço)
            docker_client.api.exec_resize(exec_id, height=0, width=0) # Envia um sinal de interrupção
        except:
            pass # Ignora se a execução já terminou
            
        await websocket.send_json({
            "type": "stderr", 
            "content": "\n[Execução interrompida pelo usuário]"
        })
    except Exception as e:
        # Um erro inesperado aconteceu na execução
        await websocket.send_json({
            "type": "stderr", 
            "content": f"Erro inesperado no orquestrador: {e}"
        })
    finally:
        # 6. Envia o aviso de filesystem_update (separadamente)
        await websocket.send_json({
            "type": "filesystem_update",
            "content": "Verificando arquivos..."
        })

# --- Endpoints da API HTTP ---

@app.post("/v1/auth/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
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

# --- Rotas Protegidas ---

@app.get("/v1/status", response_model=StatusResponse)
def get_status(current_user: User = Depends(get_current_user)):
    return StatusResponse(status="ativo", app_title=APP_TITLE)

@app.get("/v1/notebooks", response_model=List[NotebookInfo])
async def list_notebooks(current_user: User = Depends(get_current_user)):
    notebooks = []
    for f in NOTEBOOK_DIR.glob("*.ipynb"):
        notebooks.append(NotebookInfo(filename=f.name))
    return notebooks

@app.get("/v1/notebooks/{filename}", response_model=NotebookContent)
async def get_notebook(filename: str, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_path(filename)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Notebook não encontrado.")
    try:
        async with aiofiles.open(safe_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        data = json.loads(content)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler o notebook: {e}")

@app.put("/v1/notebooks/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def save_notebook(filename: str, content: NotebookContent, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_path(filename)
    try:
        content_dict = content.model_dump()
        json_content = json.dumps(content_dict, indent=2)
        async with aiofiles.open(safe_path, mode='w', encoding='utf-8') as f:
            await f.write(json_content)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar o notebook: {e}")

@app.delete("/v1/notebooks/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(filename: str, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_path(filename)
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Notebook não encontrado.")
    try:
        safe_path.unlink()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao excluir o notebook: {e}")

@app.patch("/v1/notebooks/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_notebook(filename: str, request: RenameRequest, current_user: User = Depends(get_current_user)):
    old_path = get_safe_path(filename)
    new_path = get_safe_path(request.new_filename)
    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Notebook original não encontrado.")
    if new_path.exists():
        raise HTTPException(status_code=409, detail="Já existe um notebook com esse nome.")
    try:
        old_path.rename(new_path)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao renomear o notebook: {e}")

@app.get("/v1/notebooks/download/{filename}")
async def download_notebook_file(filename: str, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_path(filename)
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Notebook não encontrado.")
    return FileResponse(path=safe_path, filename=filename, media_type='application/x-ipynb+json')

@app.get("/v1/files", response_model=List[FileInfo])
async def list_files_in_workspace(current_user: User = Depends(get_current_user)):
    files = []
    for f in WORKSPACE_DIR.glob("*"):
        if f.is_file():
            size_kb = round(f.stat().st_size / 1024, 2)
            files.append(FileInfo(filename=f.name, size_kb=size_kb))
    return files

@app.post("/v1/files/upload", response_model=FileInfo)
async def upload_file_to_workspace(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    safe_path = get_safe_workspace_path(file.filename)
    try:
        async with aiofiles.open(safe_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        size_kb = round(safe_path.stat().st_size / 1024, 2)
        return FileInfo(filename=file.filename, size_kb=size_kb)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar o arquivo: {e}")

@app.get("/v1/files/download/{filename}")
async def download_file_from_workspace(filename: str, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_workspace_path(filename)
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no workspace.")
    return FileResponse(path=safe_path, filename=filename, media_type='application/octet-stream')

@app.delete("/v1/files/delete/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_from_workspace(filename: str, current_user: User = Depends(get_current_user)):
    safe_path = get_safe_workspace_path(filename)
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no workspace.")
    try:
        safe_path.unlink()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao excluir o arquivo: {e}")


# --- FUNÇÃO WEBSOCKET ---
    
@app.websocket("/v1/execute")
async def websocket_execute(
    websocket: WebSocket,
    token: str = Query(...) 
):
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
    kernel_id = user.username 
    container: docker.models.containers.Container = None
    stats_task: asyncio.Task = None # Referência para a tarefa de stats
    exec_task: asyncio.Task = None # Referência para a tarefa de execução

    try:
        # 2. Encontrar ou Criar o Kernel
        if kernel_id in kernel_sessions:
            container = kernel_sessions[kernel_id]
            print(f"Reconectando ao kernel para o usuário: {kernel_id}")
            container.reload() 
            if container.status != "running":
                raise Exception("O kernel foi parado inesperadamente.")
        else:
            # Primeiro login, precisamos criar um novo kernel
            print(f"Criando novo kernel para o usuário: {kernel_id}...")
            
            volumes_to_mount = {}
            working_dir_path = "/"
            if HOST_WORKSPACE:
                host_path_str = str(HOST_WORKSPACE).replace("\\", "/")
                if host_path_str.startswith("C:"):
                    host_path_str = "/" + host_path_str[0].lower() + host_path_str[2:]
                volumes_to_mount[host_path_str] = { 'bind': '/data', 'mode': 'rw' }
                working_dir_path = "/data/Uploads"
            
            common_config = {
                "image": "python:3.11-slim",
                "command": ["sleep", "infinity"], 
                "detach": True, 
                "mem_limit": "8g", # Limite de 8GB de RAM
                "volumes": volumes_to_mount,
                "working_dir": working_dir_path,
                "auto_remove": True,
            }
            
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
                if "could not select device driver" in str(e):
                    # TENTATIVA 2: Alocar com CPU Apenas
                    print(f"Falha ao alocar GPU (NVIDIA Toolkit ausente?). Erro: {e}")
                    print(f"Tentando alocar kernel em modo fallback (somente CPU) para {kernel_id}...")
                    container = docker_client.containers.run(
                        **common_config
                    )
                    print(f"Kernel {container.short_id} criado com SUCESSO (somente CPU).")
                else:
                    raise e
            
            kernel_sessions[kernel_id] = container
            await websocket.send_json({"type": "stdout", "content": "Kernel conectado e pronto."})

        # --- Inicia as tarefas de monitoramento (Sprint 14) ---
        
        # 1. Envia os stats de DISCO (uma vez)
        await get_disk_stats(websocket, container)
        
        # 2. Inicia o streaming de RAM/CPU (em segundo plano)
        stats_task = asyncio.create_task(
            stream_resource_stats(websocket, container)
        )

        # 3. Loop de Execução (escuta por código)
        while True:
            data = await websocket.receive_json()
            
            action = data.get("action")
            is_running = exec_task and not exec_task.done()

            if action == "execute":
                if is_running:
                    await websocket.send_json({
                        "type": "stderr", 
                        "content": "\n[Ignorado: Uma célula já está em execução]"
                    })
                    continue
                
                code = data.get("code")
                if code is None:
                    continue
                
                # Lança a execução como uma tarefa de segundo plano
                exec_task = asyncio.create_task(
                    run_cell_execution(websocket, container, code)
                )

            # Ação "Parar"
            elif action == "stop_execution":
                print(f"Recebida solicitação de PARAR para {kernel_id}...")
                if is_running:
                    print("Cancelando execução de célula em progresso...")
                    exec_task.cancel()
                else:
                    print("Nenhuma execução para parar.")
                    # Envia uma mensagem de volta para o frontend
                    # para garantir que o loader seja desligado
                    await websocket.send_json({
                        "type": "stdout", 
                        "content": "\n[Nenhuma execução para parar]"
                    })

            elif action == "restart_kernel":
                print(f"Recebida solicitação de reinício de kernel para {kernel_id}...")
                
                if is_running:
                    # Cancela a tarefa de execução em progresso
                    print("Cancelando execução de célula em progresso...")
                    exec_task.cancel()
                
                await websocket.send_json({
                    "type": "status", 
                    "content": "Reiniciando kernel..."
                })
                
                # Fecha a conexão para acionar o 'finally' e matar o contêiner
                await websocket.close(code=1000, reason="Kernel restarting")
                break # Sai do loop 'while True'

    except WebSocketDisconnect:
        print(f"Cliente WebSocket desconectado: {kernel_id}")
    except Exception as e:
        print(f"Erro no WebSocket ou Kernel: {e}")
        try:
            await websocket.close(code=1011, reason=f"Erro: {e}")
        except:
            pass 
    finally:
        # 10. Limpeza (Destruir o Kernel e Tarefas)
        if stats_task:
            stats_task.cancel()
        if exec_task: 
            exec_task.cancel()
        
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