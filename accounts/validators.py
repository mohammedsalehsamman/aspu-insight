from django.core.exceptions import ValidationError

def validate_image_size(value):
    if value.size > 2 * 1024 * 1024:
        raise ValidationError("الحد الأقصى لحجم الصورة الشخصية هو 2 ميجابايت فقط.")
