import os
import mimetypes
from pathlib import Path
from django.conf import settings
from django.http import Http404, HttpResponseForbidden, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from .models import Application, ApplicationDocument, StatusLog, AssistanceCategory
from .forms import CitizenApplicationForm, StatusLookupForm


def landing_page(request):
    """Clean, welcoming landing page explaining Community Connect."""
    total_categories = AssistanceCategory.objects.filter(is_active=True).count()
    return render(request, 'applications/landing.html', {
        'total_categories': total_categories,
    })


def application_apply(request):
    """Citizen application submission form."""
    form = CitizenApplicationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        app = form.save(commit=False)
        app.status = Application.Status.PENDING
        app.save()

        # Handle optional uploaded document
        uploaded_doc = form.cleaned_data.get('document')
        if uploaded_doc:
            ext = os.path.splitext(uploaded_doc.name)[1].lower()
            ApplicationDocument.objects.create(
                application=app,
                file=uploaded_doc,
                original_filename=uploaded_doc.name,
                file_size=uploaded_doc.size,
                file_extension=ext,
                organization_status=ApplicationDocument.OrganizationStatus.UNORGANIZED
            )

        # Record initial status log
        StatusLog.objects.create(
            application=app,
            from_status='',
            to_status=Application.Status.PENDING,
            note="Application submitted by citizen."
        )

        messages.success(request, f"Your application {app.reference} was received successfully.")
        return redirect(f"/apply/confirmation/{app.reference}/?token={app.access_token}")

    return render(request, 'applications/apply.html', {'form': form})


def application_confirmation(request, reference):
    """Submission confirmation showing application reference and status link."""
    token = request.GET.get('token', '').strip()
    app = get_object_or_404(Application, reference=reference.upper())
    
    # Verify token to prevent arbitrary reference guessing
    is_authorized = bool(token and token == app.access_token)
    return render(request, 'applications/confirmation.html', {
        'application': app,
        'is_authorized': is_authorized,
        'token': token,
    })


def application_status(request):
    """Secure citizen status check."""
    ref_param = request.GET.get('reference', '').strip().upper()
    token_param = request.GET.get('token', '').strip().lower()

    app = None
    error = None

    if ref_param and token_param:
        try:
            app = Application.objects.select_related('category').prefetch_related('documents').get(
                reference=ref_param,
                access_token=token_param
            )
        except Application.DoesNotExist:
            error = "No application found matching that reference and security token. Please verify and try again."

    form = StatusLookupForm(initial={'reference': ref_param, 'access_token': token_param} if not app else None)

    if request.method == 'POST':
        form = StatusLookupForm(request.POST)
        if form.is_valid():
            ref = form.cleaned_data['reference']
            tok = form.cleaned_data['access_token']
            try:
                app = Application.objects.select_related('category').prefetch_related('documents').get(
                    reference=ref,
                    access_token=tok
                )
                error = None
            except Application.DoesNotExist:
                error = "No application found matching that reference and security token."

    return render(request, 'applications/status.html', {
        'form': form,
        'application': app,
        'error': error,
    })


def document_preview(request, doc_id):
    """
    Secure inline document preview for citizens and staff to verify content.
    Permitted if:
    - User is authenticated (staff/admin), or
    - Correct application access token is provided via ?token=...
    """
    doc = get_object_or_404(ApplicationDocument, pk=doc_id)
    token = request.GET.get('token', '').strip().lower()

    is_authorized = request.user.is_authenticated or (token and token == doc.application.access_token.lower())
    if not is_authorized:
        raise PermissionDenied("You do not have permission to view or preview this document.")

    if not doc.file:
        raise Http404("Document file reference missing.")

    file_path = Path(doc.file.path).resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()

    try:
        file_path.relative_to(media_root)
    except ValueError:
        return HttpResponseForbidden("Access to files outside media directory is forbidden.")

    if not file_path.exists() or not file_path.is_file():
        raise Http404("Document file not found on storage.")

    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = 'application/octet-stream'

    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    filename = doc.original_filename or file_path.name
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
