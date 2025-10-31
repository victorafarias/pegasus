import { Routes, Route, useNavigate } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import axios from 'axios' // ATUALIZADO: Importa o axios
import './App.css'
import Notebook from './components/Notebook'
import Login from './components/Login'

const API_URL = '/api/v1';
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${window.location.host}/api/v1/execute`;

// ATUALIZADO: Definições de células padrão
const EMPTY_MARKDOWN_CELL = {
  cell_type: "markdown",
  metadata: {},
  source: ["# Nova Célula", "Clique para editar..."]
};

const EMPTY_CODE_CELL = {
  cell_type: "code",
  metadata: {},
  outputs: [], // Células de código têm 'outputs'
  source: ["print('Olá!')"]
};

const EMPTY_NOTEBOOK_CONTENT = {
  cells: [ EMPTY_MARKDOWN_CELL ], // Começa com uma célula de markdown
  metadata: {},
  nbformat: 4,
  nbformat_minor: 5
};

// apiClient será redefinido após o login
let apiClient = axios.create({
  baseURL: API_URL,
});

function App() {
  // --- Estados do App ---
  const [token, setToken] = useState(() => localStorage.getItem('meuColabToken'));
  const navigate = useNavigate(); // Hook para redirecionar
  const [notebooks, setNotebooks] = useState([])
  const [files, setFiles] = useState([])
  const [currentNotebook, setCurrentNotebook] = useState(null)
  const [content, setContent] = useState(null)
  const [status, setStatus] = useState('Pronto.')
  const [hasError, setHasError] = useState(false)
  const [activeCellIndex, setActiveCellIndex] = useState(null)
  const [isDirty, setIsDirty] = useState(false)

  // --- Refs ---
  const autosaveTimer = useRef(null)
  const websocket = useRef(null)
  const fileInputRef = useRef(null)

  // --- ATUALIZADO: Lógica de Auth ---

  const handleLoginSuccess = (newToken) => {
    // 1. Salva o token no localStorage e no estado
    localStorage.setItem('meuColabToken', newToken);
    setToken(newToken);
    
    // 2. Redireciona para a página principal
    navigate('/');
  }

  const handleLogout = () => {
    localStorage.removeItem('meuColabToken');
    setToken(null);
    // O useEffect de token cuidará do redirecionamento
  }

  // --- Funções de API (com algumas atualizações) ---

  const fetchNotebooks = async () => {
    // ... (igual à Sprint 3)
    try {
      setStatus('Carregando lista...')
      const response = await apiClient.get('/notebooks')
      setNotebooks(response.data)
      setStatus('Lista carregada.')
      setHasError(false)
    } catch (error) {
      console.error('Erro ao buscar notebooks:', error)
      setStatus('Erro ao carregar lista.')
      setHasError(true)
    }
  }

  // 2. Abre um notebook específico
  const openNotebook = async (filename) => {
    if (isDirty) {
      if (!confirm('Você tem alterações não salvas. Deseja descartá-las?')) {
        return; 
      }
    }
    
    try {
      setStatus(`Abrindo ${filename}...`)
      const response = await apiClient.get(`/notebooks/${filename}`)
      setContent(response.data)
      setCurrentNotebook(filename)
      setStatus(`'${filename}' aberto.`)
      setHasError(false)
      setIsDirty(false)
      setActiveCellIndex(null) 
    } catch (error) {
      console.error('Erro ao abrir notebook:', error)
      setStatus(`Erro ao abrir ${filename}.`)
      setHasError(true)
    }
  }

  // ATUALIZADO: Esta função agora é chamada pelo autosave ou manualmente
  const saveNotebook = async () => {
    if (!currentNotebook || !content) return
    
    // Limpa qualquer timer de autosave pendente
    if (autosaveTimer.current) {
      clearTimeout(autosaveTimer.current);
    }
    
    try {
      setStatus(`Salvando ${currentNotebook}...`)
      await apiClient.put(`/notebooks/${currentNotebook}`, content)
      
      setStatus(`'${currentNotebook}' salvo com sucesso!`)
      setHasError(false)
      setIsDirty(false) // O notebook está "limpo" (salvo)
    } catch (error) {
      console.error('Erro ao salvar notebook:', error)
      setStatus(`Erro ao salvar ${currentNotebook}.`)
      setHasError(true)
    }
  }

  // 4. Cria um novo notebook
  const newNotebook = async () => {
    if (isDirty) {
      if (!confirm('Você tem alterações não salvas. Deseja descartá-las?')) {
        return;
      }
    }

    const filename = prompt('Digite o nome do novo notebook (ex: meu_notebook.ipynb):')
    if (!filename) return
    
    let safeFilename = filename
    if (!filename.endsWith('.ipynb')) {
      safeFilename += '.ipynb'
    }

    // ATUALIZADO: Salva o novo notebook imediatamente
    try {
      setStatus('Criando novo notebook...');
      await apiClient.put(`/notebooks/${safeFilename}`, EMPTY_NOTEBOOK_CONTENT);
      setStatus(`'${safeFilename}' criado.`);
      
      // ATUALIZADO: Atualiza a lista *depois* de salvar
      await fetchNotebooks(); 
      
      // Abre o notebook que acabamos de criar
      openNotebook(safeFilename);
      
    } catch (error) {
      console.error('Erro ao criar notebook:', error);
      setStatus(`Erro ao criar ${safeFilename}.`);
      setHasError(true);
    }
  }

  // ATUALIZADO: Nova função (Recurso #4)
  const handleDeleteNotebook = async (event, filename) => {
    event.stopPropagation(); 
    
    if (!confirm(`Tem certeza que deseja excluir '${filename}'?\nEsta ação não pode ser desfeita.`)) {
      return;
    }

    try {
      setStatus(`Excluindo ${filename}...`);
      await apiClient.delete(`/notebooks/${filename}`);
      setStatus(`'${filename}' excluído.`);
      
      await fetchNotebooks();
      
      if (currentNotebook === filename) {
        setContent(null);
        setCurrentNotebook(null);
        setActiveCellIndex(null);
      }

    } catch (error) {
      console.error('Erro ao excluir notebook:', error);
      setStatus(`Erro ao excluir ${filename}.`);
      setHasError(true);
    }
  }

  // ATUALIZADO: Nova função para Renomear
  const handleRenameNotebook = async () => {
    if (!currentNotebook) return;

    const newFilename = prompt(
      "Digite o novo nome para o notebook:", 
      currentNotebook // Sugere o nome atual
    );

    if (!newFilename || newFilename === currentNotebook) {
      return; // Cancelado ou sem mudança
    }

    // Garante que termina com .ipynb
    let safeNewFilename = newFilename.endsWith('.ipynb') 
      ? newFilename 
      : newFilename + '.ipynb';

    try {
      setStatus(`Renomeando para ${safeNewFilename}...`);
      await apiClient.patch(`/notebooks/${currentNotebook}`, {
        new_filename: safeNewFilename
      });

      setStatus('Renomeado com sucesso.');

      // ATUALIZADO: Atualiza a UI imediatamente
      await fetchNotebooks(); // Atualiza a lista da barra lateral
      setCurrentNotebook(safeNewFilename); // Atualiza o título

    } catch (error) {
      console.error('Erro ao renomear:', error);
      setStatus(`Erro ao renomear: ${error.response?.data?.detail || 'Erro'}`);
      setHasError(true);
    }
  }
  
  const handleDownloadNotebook = () => {
    if (!currentNotebook) return;

    // Usa o mesmo truque de "link fantasma" da Sprint 10
    const downloadUrl = `${API_URL}/notebooks/download/${currentNotebook}`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', currentNotebook);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  // --- Funções de API (Arquivos) ---
  const fetchFiles = async () => {
    try {
      const response = await apiClient.get('/files');
      setFiles(response.data);
    } catch (error) {
      console.error('Erro ao buscar arquivos:', error);
      setStatus('Erro ao carregar arquivos.');
      setHasError(true);
    }
  }

  const handleUploadFile = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      setStatus(`Enviando ${file.name}...`);
      await apiClient.post('/files/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setStatus(`'${file.name}' enviado com sucesso.`);
      // Atualiza a lista de arquivos
      fetchFiles(); 
    } catch (error) {
      console.error('Erro no upload:', error);
      setStatus(`Erro ao enviar ${file.name}.`);
      setHasError(true);
    }

    // Limpa o input para permitir o upload do mesmo arquivo novamente
    event.target.value = null;
  }

  const triggerFileInput = () => {
    // Clica no input de arquivo escondido
    fileInputRef.current.click();
  };

  // ATUALIZADO: Nova função para Download
  const handleDownloadFile = (filename) => {
    // Esta é uma maneira simples de acionar um download no navegador
    // sem usar 'axios', que não lida bem com downloads de 'blob'.
    const downloadUrl = `${API_URL}/files/download/${filename}`;

    // Cria um link 'fantasma' e clica nele
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  // ATUALIZADO: Nova função (Recurso #1)
  const handleDeleteFile = async (filename) => {
    if (!confirm(`Tem certeza que deseja excluir '${filename}' do workspace?`)) {
      return;
    }

    try {
      setStatus(`Excluindo ${filename}...`);
      await apiClient.delete(`/files/delete/${filename}`);
      setStatus(`'${filename}' excluído.`);
      fetchFiles(); // Atualiza a lista de arquivos
    } catch (error) {
      console.error('Erro ao excluir arquivo:', error);
      setStatus(`Erro ao excluir ${filename}.`);
      setHasError(true);
    }
  }

  // --- Handlers de Célula ---

  const handleCellFocus = (index) => {
    setActiveCellIndex(index);
  }

  /** ATUALIZADO: Chamado quando o usuário digita em uma célula */
  const handleCellChange = (index, newSourceString) => {
    if (!content) return;
    
    setIsDirty(true);
    
    setContent(prevContent => {
      const currentCells = prevContent?.cells || [];
      const newCells = currentCells.map((cell, i) => {
        if (i === index) {
          return {
            ...cell,
            source: newSourceString.split('\n') 
          };
        }
        return cell;
      });
      
      return { ...prevContent, cells: newCells };
    });
  }

  // ATUALIZADO: Nova função (Recurso #2)
  const handleDeleteCell = (index) => {
    if (!content) return;

    if (content.cells.length === 1) {
      if (!confirm("Esta é a última célula. Deseja mesmo excluí-la?")) {
        return;
      }
    }

    setContent(prevContent => {
      const newCells = prevContent.cells.filter((cell, i) => i !== index);
      return { ...prevContent, cells: newCells };
    });

    if (activeCellIndex === index) {
      setActiveCellIndex(index > 0 ? index - 1 : null);
    } else if (activeCellIndex > index) {
      setActiveCellIndex(prevIndex => prevIndex - 1);
    }

    setIsDirty(true);
  }

  const handleMoveCell = (index, direction) => {
    if (!content) return;

    const newIndex = direction === 'up' ? index - 1 : index + 1;

    // Verifica se o movimento é válido
    if (newIndex < 0 || newIndex >= content.cells.length) {
      return; // Não pode mover para fora dos limites
    }

    setContent(prevContent => {
      const newCells = [...prevContent.cells];

      // "Remove" a célula da posição antiga
      const [cellToMove] = newCells.splice(index, 1);
      // "Insere" a célula na nova posição
      newCells.splice(newIndex, 0, cellToMove);

      return { ...prevContent, cells: newCells };
    });

    // Atualiza a célula ativa para seguir a célula que movemos
    setActiveCellIndex(newIndex);
    setIsDirty(true); // Marca para o autosave
  }
  
  /**
   * Modifica o estado 'content' para atualizar a saída de uma célula
   */
  const setCellOutput = (cellIndex, output) => {
    setContent(prevContent => {
      if (!prevContent) return null; 
      const newCells = prevContent.cells.map((cell, i) => {
        if (i === cellIndex) {
          return { ...cell, outputs: [output] }; 
        }
        return cell;
      });
      return { ...prevContent, cells: newCells };
    });
  }

  /**
   * Chamado pelo botão "Run"
   */
  const handleRunCell = (index) => {
    setActiveCellIndex(index); 

    if (!content || !websocket.current || websocket.current.readyState !== WebSocket.OPEN) {
      console.error("WebSocket não está aberto ou notebook não carregado.");
      setStatus("Kernel não conectado. Tente recarregar.")
      setHasError(true);
      return;
    }
    
    const cell = content.cells[index];
    if (cell.cell_type !== 'code') return; 

    const code = cell.source.join('\n');
    setCellOutput(index, { type: "status", content: "Executando..." });

    try {
      websocket.current.send(JSON.stringify({ code: code }));
      setStatus('Executando código...');
      setHasError(false);
    } catch (error) {
      console.error("Erro ao enviar pelo WebSocket:", error);
      setStatus('Erro de conexão WebSocket.');
      setHasError(true);
    }
  }

  // ATUALIZADO: Nova função (Recurso #2)
  const handleAddCell = (type) => {
    if (!content) return;

    const newCell = type === 'code' ? EMPTY_CODE_CELL : EMPTY_MARKDOWN_CELL;
    
    setContent(prevContent => {
      const newCells = [...prevContent.cells];
      const insertIndex = (activeCellIndex !== null) 
        ? activeCellIndex + 1 
        : newCells.length;
      
      newCells.splice(insertIndex, 0, newCell);
      return { ...prevContent, cells: newCells };
    });
    
    setActiveCellIndex((activeCellIndex !== null) ? activeCellIndex + 1 : content.cells.length);
    setIsDirty(true);
  }

  // --- Efeito de Inicialização ---
  useEffect(() => {
    if (token) {
      // O usuário tem um token. Configura o cliente 'apiClient'
      // para enviar este token em *todos* os cabeçalhos.
      apiClient = axios.create({
        baseURL: API_URL,
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      // Inicia as conexões
      fetchNotebooks();
      fetchFiles();
      connectWebSocket();
      
    } else {
      // Não há token. Redireciona para o login.
      navigate('/login');
    }
    
    // Função de limpeza
    return () => {
      if (websocket.current) {
        websocket.current.close();
      }
    }
  }, [token]); // Roda sempre que o 'token' mudar

  // Lógica do WebSocket movida para uma função
  const connectWebSocket = () => {
    if (websocket.current && websocket.current.readyState === WebSocket.OPEN) {
      return; // Já está conectado
    }
    
    // Passa o token como parâmetro de query
    const newWsUrl = `${WS_URL}?token=${encodeURIComponent(token)}`;
    console.log("Tentando conectar ao WebSocket...");
    websocket.current = new WebSocket(newWsUrl);
    
    websocket.current.onopen = () => {
      console.log("WebSocket conectado!");
      setStatus("Conectado ao Kernel.");
      setHasError(false);
    };

    websocket.current.onerror = (error) => {
      console.error("Erro no WebSocket:", error);
      setStatus("Erro de conexão com o Kernel.");
      setHasError(true);
    };

    websocket.current.onclose = (event) => {
      console.log("WebSocket desconectado.", event.code);
      // Se o token for inválido, o backend fecha com 1008
      if (event.code === 1008) { 
        setStatus("Sessão expirada. Faça login novamente.");
        handleLogout(); // Força o logout
      } else {
        setStatus("Desconectado do Kernel.");
        setHasError(true);
      }
    };
  }  

  // Efeito de Salvamento Automático (Autosave)
  useEffect(() => {
    if (!websocket.current) return; // Não faz nada se o WS não estiver pronto

    // Define o que fazer quando uma mensagem (saída) chega
    websocket.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("Recebido do WS:", data);

      // Lida com os diferentes tipos de mensagem
      switch(data.type) {
        case 'stdout':
        case 'stderr':
        case 'status':
          // Mensagem de Saída de Célula
          if (activeCellIndex !== null) {
            setCellOutput(activeCellIndex, data);
          }
          setStatus("Execução concluída.");
          break;

        case 'filesystem_update':
          // Mensagem de Atualização de Arquivos (Seu Pedido)
          console.log("Atualizando lista de arquivos do workspace...");
          fetchFiles(); // Re-busca a lista de arquivos
          break;

        default:
          console.warn("Mensagem WS desconhecida:", data);
      }
    }

  }, [token, activeCellIndex]);

  // Esta é a lógica de autosave
  useEffect(() => {
    // Se não estiver "sujo" (dirty) ou não houver notebook, não faz nada
    if (!isDirty || !currentNotebook || !content) {
      return;
    }

    if (autosaveTimer.current) {
      clearTimeout(autosaveTimer.current);
    }

    setStatus('Alterações não salvas...');
    setHasError(false);
    
    autosaveTimer.current = setTimeout(() => {
      saveNotebook(); // Salva o notebook
    }, 2000); // Delay de 2 segundos

    return () => {
      if (autosaveTimer.current) {
        clearTimeout(autosaveTimer.current);
      }
    };
  }, [content, isDirty, currentNotebook]);

  // --- Renderização (JSX) ---
  // O return agora é um ROTEADOR
  return (
    <Routes>
      {/* Rota de Login */}
      <Route 
        path="/login" 
        element={<Login onLoginSuccess={handleLoginSuccess} />} 
      />
      
      {/* Rota Principal (Protegida) */}
      <Route 
        path="/" 
        element={
          token ? (
            <div className="App">
      
              <nav className="Sidebar">
                <h2>Meus Notebooks</h2>
                <ul className="Sidebar-list">
                  {notebooks.map((nb) => (
                    <li
                      key={nb.filename}
                      className={`Sidebar-item ${nb.filename === currentNotebook ? 'active' : ''}`}
                      onClick={() => openNotebook(nb.filename)}
                    >
                      <span className="Sidebar-item-name">{nb.filename}</span>
                      <button 
                        className="Sidebar-delete-btn"
                        onClick={(e) => handleDeleteNotebook(e, nb.filename)}
                      >
                        &times; 
                      </button>
                    </li>
                  ))}
                </ul>
                <button className="Sidebar-button" onClick={newNotebook}>
                  + Novo Notebook
                </button>
                <div className="Sidebar-divider"></div>
                <h3>Workspace</h3>
                <ul className="Workspace-list">
                  {files.length === 0 && (
                    <li className="Workspace-item"><i>Nenhum arquivo</i></li>
                  )}
                  {files.map((file) => (
                    <li key={file.filename} className="Workspace-item">
                      <span className="Workspace-item-name">{file.filename}</span>
                      <div className="Workspace-item-actions">
                        <span className="Workspace-item-size">{file.size_kb} KB</span>
                        <button 
                          className="Workspace-download-btn"
                          title={`Baixar ${file.filename}`}
                          onClick={() => handleDownloadFile(file.filename)}
                        >
                          {/* Ícone de Download (Unicode) */}
                          &#x21E9;
                        </button>
                        <button 
                          className="Workspace-delete-btn"
                          title={`Excluir ${file.filename}`}
                          onClick={() => handleDeleteFile(file.filename)}
                        >
                          &times;
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>

                {/* Input de upload escondido */}
                <input 
                  type="file"
                  ref={fileInputRef}
                  onChange={handleUploadFile}
                  style={{ display: 'none' }} 
                />
                {/* Botão de upload visível */}
                <button className="Sidebar-upload-btn" onClick={triggerFileInput}>
                  Fazer Upload
                </button>
                {/* Botão de Logout */}
                <div className="Sidebar-divider"></div>
                <button 
                  className="Sidebar-button" 
                  onClick={handleLogout}
                  style={{backgroundColor: 'var(--color-error)'}} // Deixa vermelho
                >
                  Sair (Logout)
                </button>      
              </nav>

              <main className="MainContent">
                <div className="EditorHeader">
                  <h1 onClick={handleRenameNotebook} title="Clique para renomear">
                    {currentNotebook || 'Nenhum notebook aberto'}
                  </h1>          
                  <div>
                    <span className={`EditorStatus ${hasError ? 'error' : ''}`}>
                      {status}
                    </span>
                    
                    {currentNotebook && (
                      <button 
                        className="EditorButton" 
                        onClick={saveNotebook}
                        disabled={!isDirty} 
                      >
                        Salvar Agora
                      </button>
                    )}
                  </div>
                </div>

                {currentNotebook && (
                      <button 
                        className="Editor-download-btn" 
                        title={`Baixar ${currentNotebook}`}
                        onClick={handleDownloadNotebook}
                      >
                        Baixar
                      </button>
                    )}

                {currentNotebook && (
                  <div className="Cell-add-bar">
                    <button className="Cell-add-btn" onClick={() => handleAddCell('code')}>
                      + Código
                    </button>
                    <button className="Cell-add-btn" onClick={() => handleAddCell('markdown')}>
                      + Texto
                    </button>
                  </div>
                )}

                <div className="NotebookContainer">
                  <Notebook
                    notebook={content}
                    activeCellIndex={activeCellIndex}
                    onCellChange={handleCellChange}
                    onCellFocus={handleCellFocus}
                    onRunCell={handleRunCell}
                    onDeleteCell={handleDeleteCell} 
                    onMoveCell={handleMoveCell}
                  />
                </div>
              </main>
            </div>
          ) : null
        }
      />
    </Routes>
  )
}

export default App