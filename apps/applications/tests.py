import os
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import AssistanceCategory, Application, ApplicationDocument, StatusLog


class ApplicationWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = AssistanceCategory.objects.create(
            name="Emergency Food Assistance",
            description="Urgent food provisions for households."
        )

    def test_landing_page_loads(self):
        response = self.client.get(reverse('applications:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Connect")
        self.assertContains(response, "Apply for Help")
        self.assertContains(response, "Staff Login")

    def test_apply_page_loads(self):
        response = self.client.get(reverse('applications:apply'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application for Community Assistance")
        self.assertContains(response, "Full Name")

    def test_application_submission_without_document(self):
        post_data = {
            'full_name': 'Jane Citizen',
            'phone': '555-0199',
            'email': 'jane@example.com',
            'location': 'West Ward, District 3',
            'category': self.category.id,
            'description': 'Family needs temporary assistance with staple groceries.',
        }
        response = self.client.post(reverse('applications:apply'), post_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify saved record
        app = Application.objects.get(full_name='Jane Citizen')
        self.assertEqual(app.status, Application.Status.PENDING)
        self.assertTrue(app.reference.startswith('APP-'))
        self.assertTrue(len(app.access_token) >= 32)
        self.assertEqual(app.documents.count(), 0)

        # Status log should exist
        log = StatusLog.objects.filter(application=app).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.to_status, Application.Status.PENDING)

        # Confirmation redirection
        self.assertIn(f"/apply/confirmation/{app.reference}/", response.url)

    def test_application_submission_with_document(self):
        dummy_file = SimpleUploadedFile(
            "utility_bill.pdf",
            b"%PDF-1.4 dummy pdf content for verification",
            content_type="application/pdf"
        )
        post_data = {
            'full_name': 'Robert Citizen',
            'phone': '555-0188',
            'location': 'Downtown',
            'category': self.category.id,
            'description': 'Utility support needed due to unexpected illness.',
            'document': dummy_file,
        }
        response = self.client.post(reverse('applications:apply'), post_data)
        self.assertEqual(response.status_code, 302)

        app = Application.objects.get(full_name='Robert Citizen')
        self.assertEqual(app.documents.count(), 1)
        doc = app.documents.first()
        self.assertEqual(doc.original_filename, 'utility_bill.pdf')
        self.assertEqual(doc.file_extension, '.pdf')
        self.assertEqual(doc.organization_status, ApplicationDocument.OrganizationStatus.UNORGANIZED)

    def test_secure_status_lookup_requires_token(self):
        app = Application.objects.create(
            full_name="Alice Citizen",
            phone="555-0122",
            location="East Valley",
            category=self.category,
            description="Need medical transit voucher.",
            status=Application.Status.PENDING,
            citizen_response="We are reviewing with local transit authority."
        )

        # Attempting lookup with reference alone should not display application details
        url = reverse('applications:status')
        resp = self.client.get(f"{url}?reference={app.reference}")
        self.assertNotContains(resp, "Alice Citizen")

        # Lookup with reference and incorrect token should fail
        resp = self.client.get(f"{url}?reference={app.reference}&token=wrongtoken123")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Alice Citizen")
        self.assertContains(resp, "No application found matching that reference and security token")

        # Lookup with correct reference and token should display details
        resp = self.client.get(f"{url}?reference={app.reference}&token={app.access_token}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, app.reference)
        self.assertContains(resp, "Alice Citizen")
        self.assertContains(resp, "We are reviewing with local transit authority.")
        # Private internal notes must never be exposed
        self.assertNotContains(resp, "Private Administrator Notes")

    def test_document_preview_with_valid_token(self):
        dummy_file = SimpleUploadedFile(
            "test_preview.pdf",
            b"%PDF-1.4 test document content for preview verification",
            content_type="application/pdf"
        )
        app = Application.objects.create(
            full_name="Preview Tester",
            phone="555-0155",
            location="Center City",
            category=self.category,
            description="Testing document preview.",
            status=Application.Status.PENDING
        )
        doc = ApplicationDocument.objects.create(
            application=app,
            file=dummy_file,
            original_filename="test_preview.pdf",
            file_size=len(b"%PDF-1.4 test document content for preview verification"),
            file_extension=".pdf"
        )

        preview_url = reverse('applications:document_preview', kwargs={'doc_id': doc.id})

        # Without token -> 403 Forbidden
        resp_unauth = self.client.get(preview_url)
        self.assertEqual(resp_unauth.status_code, 403)

        # With wrong token -> 403 Forbidden
        resp_wrong = self.client.get(f"{preview_url}?token=badtoken")
        self.assertEqual(resp_wrong.status_code, 403)

        # With valid token -> 200 OK with inline disposition
        resp_ok = self.client.get(f"{preview_url}?token={app.access_token}")
        self.assertEqual(resp_ok.status_code, 200)
        self.assertIn('inline', resp_ok['Content-Disposition'])
        self.assertIn('test_preview.pdf', resp_ok['Content-Disposition'])

        # Check status page displays preview button
        status_url = f"{reverse('applications:status')}?reference={app.reference}&token={app.access_token}"
        resp_status = self.client.get(status_url)
        self.assertEqual(resp_status.status_code, 200)
        self.assertContains(resp_status, "Preview Document")
        self.assertContains(resp_status, f"preview_modal_{doc.id}")

