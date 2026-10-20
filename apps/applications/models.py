import os
import uuid
from django.db import models
from django.contrib.auth.models import User


def generate_reference():
    """Generate human-readable unique reference like APP-7F3A2B."""
    return f"APP-{uuid.uuid4().hex[:6].upper()}"


def generate_access_token():
    """Generate a secure unguessable access token for citizen status check."""
    return uuid.uuid4().hex


def _document_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return f"documents/uploads/{safe_name}"


class AssistanceCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Assistance Categories'

    def __str__(self):
        return self.name


class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
        NEEDS_INFORMATION = 'NEEDS_INFORMATION', 'Needs Information'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    VALID_TRANSITIONS = {
        Status.PENDING: [Status.UNDER_REVIEW, Status.NEEDS_INFORMATION, Status.APPROVED, Status.REJECTED],
        Status.UNDER_REVIEW: [Status.NEEDS_INFORMATION, Status.APPROVED, Status.REJECTED],
        Status.NEEDS_INFORMATION: [Status.UNDER_REVIEW, Status.APPROVED, Status.REJECTED],
        Status.APPROVED: [Status.UNDER_REVIEW],
        Status.REJECTED: [Status.UNDER_REVIEW],
    }

    reference = models.CharField(max_length=20, unique=True, default=generate_reference, editable=False)
    access_token = models.CharField(max_length=64, default=generate_access_token, editable=False, db_index=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True, default='')
    location = models.CharField(max_length=100, help_text="District, town, or neighborhood")
    category = models.ForeignKey(AssistanceCategory, on_delete=models.PROTECT, related_name='applications')
    description = models.TextField(help_text="Detailed description of the required assistance")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    
    # Citizen response (visible on public status lookup)
    citizen_response = models.TextField(
        blank=True, default='',
        help_text="Official response or request for more information visible to citizen"
    )
    # Private notes (administrator eyes only)
    internal_notes = models.TextField(
        blank=True, default='',
        help_text="Private internal administrator notes not visible to citizen"
    )
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_applications')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.full_name} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])


class ApplicationDocument(models.Model):
    class OrganizationStatus(models.TextChoices):
        UNORGANIZED = 'UNORGANIZED', 'Unorganized'
        ORGANIZED = 'ORGANIZED', 'Organized'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped'

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=_document_upload_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    file_extension = models.CharField(max_length=20, blank=True, default='')
    organization_status = models.CharField(
        max_length=20, choices=OrganizationStatus.choices, default=OrganizationStatus.UNORGANIZED
    )
    organized_category = models.CharField(max_length=100, blank=True, default='')
    organized_path = models.CharField(max_length=500, blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_filename} ({self.application.reference})"


class StatusLog(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='status_logs')
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    note = models.TextField(blank=True, default='')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.application.reference}: {self.from_status} → {self.to_status}"
