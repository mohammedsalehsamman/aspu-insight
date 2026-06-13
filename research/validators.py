from django.core.exceptions import ValidationError

def validate_file_size(value):
    filesize = value.size
    if filesize > 5242880:
        raise ValidationError("الحد الأقصى لحجم الملف هو 5 ميجابايت فقط.")