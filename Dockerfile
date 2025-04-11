FROM python:3.10-slim

ENV PYTHONBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/

# Install dependencies first (better caching)
RUN pip install --upgrade pip && \
    apt-get update && \
    apt-get install -y \
    default-mysql-client \
    default-libmysqlclient-dev \
    pkg-config \
    build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    pip install -r requirements.txt

# Copy the rest of the application
COPY . /app/

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000", "python manage.py search_index --rebuild"]