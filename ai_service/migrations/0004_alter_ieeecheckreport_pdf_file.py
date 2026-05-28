# Migration to fix pdf_file max_length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_service', '0003_alter_ieeecheckreport_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ieeecheckreport',
            name='pdf_file',
            field=models.FileField(
                upload_to='ieee_documents/%Y/%m/',
                max_length=500,
                verbose_name='ملف البحث (PDF/DOCX)',
            ),
        ),
    ]
