#!/usr/bin/env bash
# يرفع فقط نماذج ML الضرورية فعلياً للإنتاج (~1.6GB) من جهازك المحلي إلى السيرفر،
# ويتجاهل عمداً مجلدات التجارب القديمة والـ checkpoints (~10GB غير مستخدمة في الإنتاج).
# يُشغَّل من جهازك المحلي (Git Bash / WSL)، لا من السيرفر.
#
# الاستخدام:
#   ./scripts/upload_models.sh deploy@YOUR_SERVER_IP /home/deploy/aspu-insight
#
# المتطلب: rsync متوفر محلياً (مرفق مع Git for Windows / WSL)، ومفتاح SSH مُعدّ مسبقاً.

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "الاستخدام: $0 user@server_ip /path/to/project/on/server" >&2
  exit 1
fi

REMOTE="$1"
REMOTE_PATH="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> إنشاء المجلدات المطلوبة على السيرفر..."
ssh "$REMOTE" "mkdir -p '$REMOTE_PATH/ai_service/ml_models/experiments' '$REMOTE_PATH/my-model'"

echo "==> رفع نموذج كشف الانتحال المُعتمَد (exp9-balanced-domain-APPROVED-BACKUP)..."
rsync -avz --progress \
  "$PROJECT_ROOT/ai_service/ml_models/experiments/exp9-balanced-domain-APPROVED-BACKUP" \
  "$REMOTE:$REMOTE_PATH/ai_service/ml_models/experiments/"

echo "==> رفع نموذج الـ embeddings العام (MiniLM)..."
rsync -avz --progress \
  "$PROJECT_ROOT/ai_service/ml_models/paraphrase-multilingual-MiniLM-L12-v2-base" \
  "$REMOTE:$REMOTE_PATH/ai_service/ml_models/"

echo "==> رفع نماذج الترجمة (opus-mt ar<->en)..."
rsync -avz --progress \
  "$PROJECT_ROOT/ai_service/ml_models/opus-mt-ar-en" \
  "$PROJECT_ROOT/ai_service/ml_models/opus-mt-en-ar" \
  "$REMOTE:$REMOTE_PATH/ai_service/ml_models/"

echo "==> رفع مرجع كشف التكرار (commonness_reference_arpd.npy)..."
rsync -avz --progress \
  "$PROJECT_ROOT/ai_service/ml_models/commonness_reference_arpd.npy" \
  "$REMOTE:$REMOTE_PATH/ai_service/ml_models/"

echo "==> رفع نموذج استخراج الكلمات المفتاحية (my-model)..."
rsync -avz --progress \
  "$PROJECT_ROOT/my-model/" \
  "$REMOTE:$REMOTE_PATH/my-model/"

echo "==> تم رفع جميع النماذج المطلوبة (~1.6GB). تجاهلنا عمداً experiments الأخرى وملفات checkpoints."
