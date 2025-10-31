import React, { useState } from 'react';
import axios from 'axios';
import './Login.css'; // Vamos criar este arquivo

// URL da nossa API de token
const LOGIN_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1') + '/auth/token';

/**
 * Componente da Tela de Login.
 * @param {object} props
 * @param {function} props.onLoginSuccess - Função para chamar quando o login for bem-sucedido
 */
function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(''); // Limpa erros antigos

    // O FastAPI espera dados de 'form-urlencoded' para o OAuth2
    const loginData = new URLSearchParams();
    loginData.append('username', username);
    loginData.append('password', password);

    try {
      const response = await axios.post(LOGIN_URL, loginData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const token = response.data.access_token;

      // Chama a função do App.jsx para salvar o token
      onLoginSuccess(token);

    } catch (err) {
      if (err.response && err.response.status === 401) {
        setError('Usuário ou senha incorretos.');
      } else {
        setError('Erro ao conectar ao servidor. Tente novamente.');
      }
      console.error('Erro de login:', err);
    }
  };

  return (
    <div className="LoginContainer">
      <form className="LoginForm" onSubmit={handleSubmit}>
        <h1>Pegasus</h1>
        <h2>Login</h2>
        <div className="InputGroup">
          <label htmlFor="username">Usuário</label>
          <input
            type="text"
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="InputGroup">
          <label htmlFor="password">Senha</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="LoginError">{error}</p>}
        <button type="submit" className="LoginButton">
          Entrar
        </button>
      </form>
    </div>
  );
}

export default Login;