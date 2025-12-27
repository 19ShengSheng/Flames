# 使用官方 Python 3.10 镜像作为基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（PDF 生成和中文字体支持）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxcursor1 libxdamage1 \
    libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 \
    libglib2.0-0 libgtk-3-0 libfontconfig1 \
    fonts-wqy-zenhei fonts-wqy-microhei \
    curl \
    libnss3 libnspr4 libdrm2 libxkbcommon0 libasound2 libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理工具（使用国内镜像）
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple uv
ENV PATH="/root/.local/bin:$PATH"

# 复制项目配置文件
COPY pyproject.toml uv.lock ./

# 使用 uv 安装依赖
RUN uv sync --frozen 

# 复制项目文件
COPY Flask.py .
COPY infer.py .
COPY collect.py .
COPY config.json .
COPY config.yaml .
COPY configuration_internlm.py .
COPY modeling_internlm.py .
COPY tokenization_internlm.py .
COPY tokenizer.model .
COPY special_tokens_map.json .
COPY pytorch_model.bin.index.json .
COPY generate_pdf.js .
COPY package.json .
COPY templates/ ./templates/

# 安装 Node.js 依赖（用于 PDF 生成）
RUN npm install

# 创建必要的目录
RUN mkdir -p data logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=1
ENV HF_HUB_DISABLE_PROGRESS_BARS=1
ENV HF_HUB_DISABLE_INPUT=1

# 数据库配置环境变量（默认值，可通过 docker-compose.yml 或运行时覆盖）
ENV DB_HOST=host.docker.internal
ENV DB_PORT=3307
ENV DB_USER=root
ENV DB_PASSWORD=123
ENV DB_NAME=llm-eval
ENV DB_CHARSET=utf8mb4

# 暴露端口
EXPOSE 5001

# 启动命令
CMD ["uv", "run", "python", "Flask.py"]