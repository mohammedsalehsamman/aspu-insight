from django.db import models
from django.db import models

class JournalConfiguration(models.Model):
    ACCESS_MODES = [
        ('full_open', 'وصول مفتوح بالكامل (جميع الأبحاث مجانية للجميع)'),
        ('full_closed', 'وصول مغلق بالكامل (اشتراك إجباري للـ PDF لجميع الأبحاث)'),
        ('hybrid', 'نموذج هجين (الوصول مغلق، باستثناء الأبحاث التي دفع مؤلفها رسوم النشر الحر)'),
        ('abstract_only', 'عرض المستخلص فقط (حجب الـ PDF عن الجميع باستثناء الإدارة والكاتب)'),
    ]
    
    system_mode = models.CharField(
        max_length=20, 
        choices=ACCESS_MODES, 
        default='full_open',
        verbose_name="نمط الوصول العام للمجلة"
    )

    class Meta:
        db_table = 'JournalConfiguration'
        verbose_name = "إعدادات الوصول للمجلة"
        verbose_name_plural = "إعدادات الوصول للمجلة"

    def str(self):
        return f"النمط الحالي للمجلة: {self.get_system_mode_display()}"
