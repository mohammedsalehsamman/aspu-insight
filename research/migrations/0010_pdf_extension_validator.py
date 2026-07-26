
import django.core.validators
import research.validators
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('research', '0009_researchpaper_assigned_editor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='researchpaper',
            name='pdf_file',
            field=models.FileField(blank=True, null=True, upload_to='papers_pdf/', validators=[research.validators.validate_file_size, django.core.validators.FileExtensionValidator(allowed_extensions=['pdf'])]),
        ),
    ]
