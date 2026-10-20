import os
import shutil
from pathlib import Path
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from ..applications.models import AssistanceCategory, Application, ApplicationDocument, StatusLog
from .services import organize_application_documents


class ManagementWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='Password123!'
        )
        self.normal_user = User.objects.create_user(
            username='citizen_user',
            password='Password123!'
        )
        self.category = AssistanceCategory.objects.create(name="Housing Support")
        self.app = Application.objects.create(
            full_name="Mark Citizen",
            phone="555-9988",
            location="Center Ward",
            category=self.category,
            description="Rental assistance application.",
            status=Application.Status.PENDING
        )

    def test_dashboard_access_restricted_to_staff(self):
        # Unauthenticated redirect
        resp = self.client.get(reverse('management:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('management:login'), resp.url)

        # Authenticated non-staff redirected
        self.client.login(username='citizen_user', password='Password123!')
        resp = self.client.get(reverse('management:dashboard'))
        self.assertEqual(resp.status_code, 302)

        # Staff can access
        self.client.login(username='admin_test', password='Password123!')
        resp = self.client.get(reverse('management:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Administrator Dashboard")
        self.assertContains(resp, self.app.reference)
        self.assertContains(resp, "Mark Citizen")

    def test_dashboard_metrics(self):
        # Add another application in APPROVED state
        Application.objects.create(
            full_name="Sarah Resident",
            phone="555-1122",
            location="South Ward",
            category=self.category,
            description="Approved heating grant.",
            status=Application.Status.APPROVED
        )

        self.client.login(username='admin_test', password='Password123!')
        resp = self.client.get(reverse('management:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['stats']['total'], 2)
        self.assertEqual(resp.context['stats']['pending'], 1)
        self.assertEqual(resp.context['stats']['approved'], 1)

    def test_application_detail_and_status_update(self):
        self.client.login(username='admin_test', password='Password123!')
        detail_url = reverse('management:application_detail', args=[self.app.pk])

        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.app.reference)

        # Update status to UNDER_REVIEW
        post_data = {
            'status': Application.Status.UNDER_REVIEW,
            'citizen_response': 'Your request is currently being assessed by our housing coordinator.',
            'internal_notes': 'Verified residency with municipal registrar.'
        }
        resp = self.client.post(detail_url, post_data)
        self.assertEqual(resp.status_code, 302)

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.UNDER_REVIEW)
        self.assertEqual(self.app.citizen_response, post_data['citizen_response'])
        self.assertEqual(self.app.internal_notes, post_data['internal_notes'])
        self.assertEqual(self.app.reviewed_by, self.admin_user)

        # Verify status log recorded
        log = StatusLog.objects.filter(application=self.app).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.to_status, Application.Status.UNDER_REVIEW)

    def test_status_rejection_requires_citizen_explanation(self):
        self.client.login(username='admin_test', password='Password123!')
        detail_url = reverse('management:application_detail', args=[self.app.pk])

        # Attempt to reject without explanation
        post_data = {
            'status': Application.Status.REJECTED,
            'citizen_response': '',
            'internal_notes': 'Internal note only.'
        }
        resp = self.client.post(detail_url, post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(
            resp.context['form'],
            'citizen_response',
            'Please provide a citizen-facing response explaining the reason for rejection.'
        )

    def test_organize_documents_with_allfileorg(self):
        # Create a document file on disk within MEDIA_ROOT
        media_root = Path(settings.MEDIA_ROOT).resolve()
        uploads_dir = media_root / 'documents' / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)

        sample_file_path = uploads_dir / f"{self.app.reference}_test_doc.txt"
        sample_file_path.write_text("Verification supporting note.")

        doc = ApplicationDocument.objects.create(
            application=self.app,
            file=str(sample_file_path.relative_to(media_root).as_posix()),
            original_filename="residency_proof.txt",
            file_size=sample_file_path.stat().st_size,
            file_extension=".txt",
            organization_status=ApplicationDocument.OrganizationStatus.UNORGANIZED
        )

        result = organize_application_documents(user=self.admin_user)
        self.assertTrue(result['success'])
        self.assertGreaterEqual(result['total_moved'], 1)

        doc.refresh_from_db()
        self.assertEqual(doc.organization_status, ApplicationDocument.OrganizationStatus.ORGANIZED)
        self.assertTrue(bool(doc.organized_category))
        self.assertTrue(os.path.exists(doc.file.path))
