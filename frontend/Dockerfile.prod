# --- Estágio 1: Build (Construção) ---
# Usa a imagem Node para construir o app React
FROM node:20-alpine AS builder

WORKDIR /app

# Copia os arquivos de dependência e instala
COPY package.json package-lock.json ./
RUN npm install

# Copia todo o código-fonte e constrói o app
COPY . .
RUN npm run build # Cria a pasta 'dist' otimizada

# --- Estágio 2: Serve (Servidor) ---
# Usa uma imagem NGINX leve para servir os arquivos estáticos
FROM nginx:1.25-alpine

# Copia os arquivos da build (da pasta 'dist') para a pasta do NGINX
COPY --from=builder /app/dist /usr/share/nginx/html

# ATUALIZADO: Copia nossa configuração NGINX (próximo passo)
# Isso é crucial para o React Router funcionar
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expõe a porta 80 (porta padrão do NGINX)
EXPOSE 80

# Comando para iniciar o NGINX
CMD ["nginx", "-g", "daemon off;"]