# 1. Use uma imagem Python oficial como base
FROM python:3.11-slim

# ATUALIZADO: "Sujando" o cache para forçar o rebuild
ENV CACHE_BUSTER=sprint11.1

# 2. Defina o diretório de trabalho dentro do contêiner
WORKDIR /app

# 3. Copie o arquivo de requisitos para o contêiner
COPY requirements.txt .

# 4. Instale as bibliotecas Python
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copie todo o código do backend (o 'main.py') para o contêiner
COPY . .

# 6. Exponha a porta 8000 (onde o FastAPI vai rodar)
EXPOSE 8000

# 7. O comando para iniciar o servidor quando o contêiner rodar
# uvicorn main:app --host 0.0.0.0 --port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]