FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

# libpq-dev: للاتصال بـ PostgreSQL عبر psycopg2-binary
# build-essential: مطلوب لبناء بعض حزم ML من المصدر عند عدم توفر عجلة (wheel) جاهزة لهذا التوزيع
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# نثبّت torch من فهرس CPU الرسمي أولاً: السيرفر الهدف بلا GPU، وفهرس PyPI الافتراضي
# يجلب توزيعة CUDA (+نحو 3-4GB إضافية عبر حزم nvidia-*) لن تُستخدَم إطلاقاً هنا.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# النماذج الفعلية تُركَب كـ volume وقت التشغيل (docker-compose.yml) وليست هنا - راجع .dockerignore
RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "aspu_insight.asgi:application"]
