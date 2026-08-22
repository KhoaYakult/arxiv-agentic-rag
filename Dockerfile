# Dùng Python 3.11 làm base image
FROM python:3.11-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt hệ thống cần thiết cho PyMuPDF và OpenCV
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements và cài đặt python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Tạo thư mục data nếu chưa có
RUN mkdir -p data

# Mở cổng 7860 (Cổng mặc định của Hugging Face Spaces)
EXPOSE 7860

# Chạy uvicorn tự động nhận $PORT từ Railway (hoặc 7860 nếu chạy local)
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
