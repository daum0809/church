# 주일예배 PDF 웹 화면 (핸드폰용) - 인터넷 서버에 올릴 때 사용
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m -u 1000 app && chown -R app /app
USER app

EXPOSE 8000
CMD ["python", "web.py"]
