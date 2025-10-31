# Este é o Dockerfile de DESENVOLVIMENTO
# Ele roda o servidor do Vite com 'hot-reload'

FROM node:20-alpine

WORKDIR /app

# Copia APENAS o package.json para cachear as dependências
COPY package.json ./

# Instala as dependências
# (Não precisamos do package-lock.json no dev)
RUN npm install

# Copia o resto do código
COPY . .

# Expõe a porta do Vite
EXPOSE 5173

# O comando para iniciar o servidor de desenvolvimento
CMD ["npm", "run", "dev", "--", "--host"]