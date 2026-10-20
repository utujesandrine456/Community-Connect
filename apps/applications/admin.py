from django.contrib import admin
from .models import AssistanceCategory, Application, ApplicationDocument, StatusLog


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    readonly_fields = ('original_filename', 'file_size', 'file_extension', 'organization_status', 'organized_category', 'organized_path', 'uploaded_at')


class StatusLogInLine(admin.TabularInline):
    model = StatusLog
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'note', 'changed_by', 'timestamp')


@admin.register(AssistanceCategory)
class AssistanceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'full_name', 'phone', 'location', 'category', 'status', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('reference', 'full_name', 'phone', 'location')
    readonly_fields = ('reference', 'access_token', 'created_at', 'updated_at')
    inlines = [ApplicationDocumentInline, StatusLogInLine]


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'application', 'organization_status', 'organized_category', 'uploaded_at')
    list_filter = ('organization_status', 'organized_category')
    search_fields = ('original_filename', 'application__reference')
