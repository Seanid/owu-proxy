FROM python:3.13-slim

# 非 root 用户运行
RUN groupadd -r owuproxy && useradd -r -g owuproxy owuproxy

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝代码
COPY main.py .

# 切换非 root 用户
USER owuproxy

EXPOSE 18000

CMD ["python", "main.py"]
