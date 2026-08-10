# نشر ASPU Insight على سيرفر إنتاج

هذا الدليل يشرح استخدام ملفات النشر الجاهزة في هذا المستودع. للتحليل الكامل لاختيار السيرفر
راجع التقرير المُفصَّل على سطح المكتب: `تقرير_نشر_ASPU_Insight.html`.

## الملفات المُجهَّزة في هذا المستودع

| الملف | الغرض |
|---|---|
| `Dockerfile` | صورة تشغيل التطبيق (Daphne ASGI) |
| `docker-compose.yml` | تنسيق الخدمات: db, redis, web, celery-worker, celery-beat, nginx, certbot |
| `.dockerignore` | يستثني venv/النماذج الضخمة/الأسرار من صورة Docker |
| `nginx/nginx.conf` | الإعداد النشط حالياً (HTTP فقط - مرحلة بدء التشغيل) |
| `nginx/nginx.http-only.conf` | نسخة احتياطية من نفس إعداد HTTP فقط |
| `nginx/nginx.ssl.conf.example` | القالب الذي تنسخه إلى `nginx/nginx.conf` بعد الحصول على شهادة SSL |
| `.env.production.example` | قالب متغيرات بيئة الإنتاج (يُنسَخ إلى `.env` على السيرفر فقط) |
| `scripts/upload_models.sh` | يرفع فقط نماذج ML الضرورية (~1.6GB) عبر rsync، ويتجاهل ~10GB تجارب قديمة |
| `requirements.txt` | أُعيد ترميزه لـ UTF-8 (كان UTF-16 يكسر pip داخل Docker) + أُضيف `psycopg2-binary` |

## 1. إنشاء السيرفر

أنشئ سيرفر Hetzner CPX31 (4 vCPU / 8GB RAM / 160GB) أو ما يعادله (راجع التقرير للمقارنة)،
نظام Ubuntu 22.04، وأضف مفتاح SSH العام لجهازك عند الإنشاء.

## 2. تجهيز السيرفر

```bash
ssh root@YOUR_SERVER_IP

apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin ufw rsync

ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable

adduser deploy
usermod -aG docker deploy
```

## 3. رفع الكود

```bash
su - deploy
git clone <رابط مستودعك> aspu-insight
cd aspu-insight
```

## 4. رفع نماذج ML (غير موجودة في Git)

من **جهازك المحلي** (وليس على السيرفر):

```bash
cd /c/Users/hp/Desktop/aspuinsight/aspu-insight
./scripts/upload_models.sh deploy@YOUR_SERVER_IP /home/deploy/aspu-insight
```

يرفع هذا فقط: `exp9-balanced-domain-APPROVED-BACKUP`, `paraphrase-multilingual-MiniLM-L12-v2-base`,
`opus-mt-ar-en`, `opus-mt-en-ar`, `commonness_reference_arpd.npy`, `my-model/` — أي ~1.6GB
بدل 12GB، لأن الباقي (تجارب/checkpoints قديمة) غير مستخدَم في الإنتاج حسب `settings.py`.

## 5. إعداد ملف .env على السيرفر

```bash
cp .env.production.example .env
nano .env
```

عبّئ فيه (خصوصاً):
- `SECRET_KEY`: ولّده أولاً ببناء الصورة:
  ```bash
  docker compose build web
  docker compose run --rm web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `FRONTEND_URL`: دومينك الفعلي.
- `DB_PASSWORD`: كلمة سر قوية جديدة.
- اترك `SECURE_PRODUCTION=False` و `BEHIND_HTTPS_PROXY=False` مؤقتاً حتى الحصول على SSL (الخطوة 7).

## 6. التشغيل الأول (HTTP فقط، بدون SSL بعد)

```bash
docker compose up -d --build

docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser
```

تحقق: `docker compose ps` (يجب أن تكون كل الخدمات `Up`)، وافتح `http://YOUR_SERVER_IP` في المتصفح.

## 7. توجيه الدومين والحصول على شهادة SSL

1. في لوحة تحكم الدومين، أنشئ سجل `A` يوجّه `YOUR_DOMAIN` و `www.YOUR_DOMAIN` إلى IP السيرفر.
2. انتظر انتشار DNS (تحقق بـ `ping YOUR_DOMAIN`).
3. اطلب الشهادة:
   ```bash
   docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
     -d YOUR_DOMAIN -d www.YOUR_DOMAIN
   ```
4. عدّل `nginx/nginx.ssl.conf.example` (استبدل `YOUR_DOMAIN`)، ثم:
   ```bash
   cp nginx/nginx.ssl.conf.example nginx/nginx.conf
   docker compose restart nginx
   ```
5. في `.env` غيّر `SECURE_PRODUCTION=True` و `BEHIND_HTTPS_PROXY=True`، ثم:
   ```bash
   docker compose restart web celery-worker celery-beat
   ```

## 8. بعد النشر

- **نسخ احتياطي يومي:**
  ```bash
  docker compose exec db pg_dump -U aspu_user aspu_insight > backup_$(date +%F).sql
  ```
  أضفها إلى crontab.
- **تجديد SSL شهرياً:** `docker compose run --rm certbot renew` عبر cron.
- **مراقبة السجلات:** `docker compose logs -f web celery-worker`.

## قائمة تحقق سريعة

- [ ] الكود مرفوع عبر git clone
- [ ] النماذج مرفوعة عبر `scripts/upload_models.sh`
- [ ] `.env` معبّى بالكامل (SECRET_KEY جديد، DB_PASSWORD قوي، دومين صحيح)
- [ ] `docker compose up -d --build` يعمل وكل الخدمات Up
- [ ] migrate + collectstatic + createsuperuser تمّت
- [ ] الدومين موجّه وشهادة SSL صادرة
- [ ] `nginx/nginx.conf` مُحدَّث لنسخة SSL و `SECURE_PRODUCTION=True`
- [ ] نسخ احتياطي وتجديد SSL مُجدولان عبر cron
