from django.contrib import admin

from configuration.models import JournalConfiguration


@admin.register(JournalConfiguration)
class JournalConfigurationAdmin(admin.ModelAdmin):
    list_display = ['id', 'system_mode']
