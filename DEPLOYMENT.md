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

## 1. إنشاء السيرفر (Oracle Cloud Infrastructure - Always Free)

بدل الخطة الأصلية (Hetzner CPX31 مدفوع)، تم الاشتراك فعلياً في **Oracle Cloud Free Tier**. الخيار
المناسب هنا هو شكل **Ampere A1 (ARM)** ضمن Always Free، لأنه الوحيد بموارد كافية لهذا الحمل
(الأشكال الأخرى المجانية على OCI بـ1GB رام فقط غير كافية إطلاقاً لتحميل نماذج الذكاء الاصطناعي):

1. في OCI Console: **Compute → Instances → Create Instance**.
2. **Image and shape → Edit → Image**: اختر **Canonical Ubuntu 22.04** (تأكد من اختيار
   الإصدار **aarch64/ARM** وليس x86_64، لأن Ampere A1 معمارية ARM).
3. **Shape**: اضغط Change Shape → تبويب **Ampere** → **VM.Standard.A1.Flex** → اضبط
   **4 OCPUs / 24 GB Memory** (الحد الأقصى المجاني بالكامل — أعلى فعلياً من توصية التقرير
   الأصلي 8GB لأنه بلا أي تكلفة).
4. **Boot volume**: وسّعه إلى ~100GB على الأقل (ضمن حصة الـ200GB Always Free) — الافتراضي 50GB
   لا يكفي مع مكتبات torch + النماذج + نمو قاعدة البيانات.
5. **Add SSH keys**: ولّد زوج مفاتيح جديد من نفس الصفحة ونزّل المفتاح الخاص (أو الصق مفتاحك
   العام الموجود مسبقاً).
6. Networking: اترك VCN الافتراضي أو أنشئ واحداً جديداً (سنعدّل قواعد الجدار في الخطوة التالية).
7. Create.

<div></div>

> **ملاحظة معمارية:** كل صور Docker المستخدَمة هنا (`postgres:16-alpine`, `redis:7-alpine`,
> `nginx:alpine`, `python:3.11-slim`) رسمية ومتعددة المعمارية (تدعم arm64)، وفهرس torch CPU
> (`download.pytorch.org/whl/cpu`) يوفر عجلات (wheels) لـ `linux_aarch64` أيضاً — لا حاجة لتعديل
> `Dockerfile`. تحقق فقط بعد أول `docker compose build` أن التثبيت نجح دون العودة لبناء من المصدر.

## 2. تجهيز السيرفر

على عكس Hetzner (حيث الدخول مباشرة كـ`root`)، صور Ubuntu على OCI تُدخلك كمستخدم `ubuntu` مع
صلاحيات `sudo`:

```bash
ssh -i /path/to/private_key ubuntu@YOUR_SERVER_IP

sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin ufw rsync

sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable

sudo adduser deploy
sudo usermod -aG docker deploy
```

### تحذير خاص بـ OCI: جدار الحماية طبقتان، ليس ufw وحده

على Hetzner كان `ufw` كافياً. على Oracle Cloud هناك طبقتان إضافيتان يجب فتحهما، وإلا ستبقى
المنافذ 80/443 مغلقة رغم `ufw` رغم أنه يظهر "Up" في `docker compose ps`:

1. **Security List على مستوى الشبكة (VCN) — عبر الكونسول، ليس SSH:**
   `Networking → Virtual Cloud Networks → (VCN الخاصة بك) → Security Lists → Default Security
   List → Add Ingress Rules`. أضف قاعدتين: Source CIDR `0.0.0.0/0`، IP Protocol `TCP`،
   Destination Port `80`، وأخرى لـ `443` (المنفذ 22 عادة مفتوح افتراضياً عند إنشاء VCN بالخيار
   السريع — تحقق منه أيضاً).

2. **قواعد iptables الافتراضية على صورة Ubuntu نفسها:** صور Oracle الجاهزة تأتي بقاعدة
   `REJECT` مضبوطة مسبقاً في سلسلة `INPUT` تمنع أي منفذ غير SSH حتى لو سمح به `ufw`. تحقق أولاً:
   ```bash
   sudo iptables -L INPUT --line-numbers
   ```
   أدرج قاعدتي القبول **قبل** رقم سطر قاعدة REJECT (مثلاً إن كانت REJECT في السطر 6):
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```
   بدون هذه الخطوة تحديداً، أشهر مشكلة يواجهها مستخدمو OCI الجدد هي "docker يعمل لكن الموقع لا
   يفتح من الخارج".

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
- **تحذير خاص بـ Always Free:** Oracle قد تسترجع (reclaim) موارد Always Free تلقائياً إن بقي
  استهلاك CPU/الشبكة/الذاكرة منخفضاً جداً لمدة 7 أيام متتالية (سيرفر خامل تقريباً بلا زوار).
  إن كان السيرفر للعرض/المناقشة فقط بزيارات متقطعة، تأكد من هذا قبل يوم المناقشة، أو أبقِ عملية
  خفيفة (مثل فحص دوري كل بضع ساعات) تحافظ على نشاط ملحوظ.

## قائمة تحقق سريعة

- [ ] سيرفر Ampere A1 (4 OCPU/24GB) تم إنشاؤه بصورة Ubuntu 22.04 ARM
- [ ] قواعد Security List في OCI Console مفتوحة لمنفذي 80 و443 (بالإضافة لـ ufw)
- [ ] قاعدة iptables الافتراضية المانعة عُدِّلت للسماح بـ80/443
- [ ] الكود مرفوع عبر git clone
- [ ] النماذج مرفوعة عبر `scripts/upload_models.sh`
- [ ] `.env` معبّى بالكامل (SECRET_KEY جديد، DB_PASSWORD قوي، دومين صحيح)
- [ ] `docker compose up -d --build` يعمل وكل الخدمات Up
- [ ] migrate + collectstatic + createsuperuser تمّت
- [ ] الدومين موجّه وشهادة SSL صادرة
- [ ] `nginx/nginx.conf` مُحدَّث لنسخة SSL و `SECURE_PRODUCTION=True`
- [ ] نسخ احتياطي وتجديد SSL مُجدولان عبر cron
