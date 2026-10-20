import os
import mimetypes
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.conf import settings
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied

from ..applications.models import Application, ApplicationDocument, StatusLog
from .forms import AdminLoginForm, ApplicationReviewForm
from .services import organize_application_documents


def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def admin_login(request):
    """Administrator login view using Django's authentication system."""
    if is_admin_or_staff(request.user):
        return redirect('management:dashboard')

    form = AdminLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        if user.is_staff or user.is_superuser:
            login(request, user)
            next_url = request.GET.get('next') or request.POST.get('next') or 'management:dashboard'
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}.")
            return redirect(next_url)
        else:
            messages.error(request, "Access restricted. Only administrators may enter the management portal.")

    return render(request, 'management/login.html', {'form': form})


def admin_logout(request):
    """Administrator logout view."""
    logout(request)
    messages.info(request, "You have been logged out of the administrator portal.")
    return redirect('applications:landing')


@login_required(login_url='management:login')
@user_passes_test(is_admin_or_staff, login_url='management:login')
def dashboard(request):
    """Staff & Administrator dashboard with role-aware metrics and app-level permission checking."""
    can_view_applications = request.user.is_superuser or request.user.has_perm('applications.view_application')
    can_change_applications = request.user.is_superuser or request.user.has_perm('applications.change_application')
    can_view_users = request.user.is_superuser or request.user.has_perm('auth.view_user')
    can_view_groups = request.user.is_superuser or request.user.has_perm('auth.view_group') or request.user.has_perm('auth.add_group')

    if not can_view_applications:
        return render(request, 'management/dashboard.html', {
            'can_view_applications': False,
            'can_change_applications': False,
            'can_view_users': can_view_users,
            'can_view_groups': can_view_groups,
            'stats': None,
            'page_obj': None,
        })

    queryset = Application.objects.select_related('category').prefetch_related('documents').all()

    # Exact metrics from database records
    stats = {
        'total': queryset.count(),
        'pending': queryset.filter(status=Application.Status.PENDING).count(),
        'under_review': queryset.filter(status=Application.Status.UNDER_REVIEW).count(),
        'needs_info': queryset.filter(status=Application.Status.NEEDS_INFORMATION).count(),
        'approved': queryset.filter(status=Application.Status.APPROVED).count(),
        'rejected': queryset.filter(status=Application.Status.REJECTED).count(),
    }

    # Search by citizen name, reference, phone, or location
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(reference__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(location__icontains=search_query)
        )

    # Filter by status
    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter in dict(Application.Status.choices):
        queryset = queryset.filter(status=status_filter)

    # Document stats for organize button badge
    unorganized_docs_count = ApplicationDocument.objects.filter(
        organization_status__in=[
            ApplicationDocument.OrganizationStatus.UNORGANIZED,
            ApplicationDocument.OrganizationStatus.FAILED
        ]
    ).count()

    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'management/dashboard.html', {
        'can_view_applications': True,
        'can_change_applications': can_change_applications,
        'can_view_users': can_view_users,
        'can_view_groups': can_view_groups,
        'stats': stats,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Application.Status.choices,
        'unorganized_docs_count': unorganized_docs_count,
    })


@login_required(login_url='management:login')
@user_passes_test(is_admin_or_staff, login_url='management:login')
def application_detail(request, pk):
    """View application complete details, supporting documents, history, and update status/responses."""
    can_view_applications = request.user.is_superuser or request.user.has_perm('applications.view_application')
    if not can_view_applications:
        raise PermissionDenied("You do not have permission to view applications.")

    can_change_applications = request.user.is_superuser or request.user.has_perm('applications.change_application')

    app = get_object_or_404(
        Application.objects.select_related('category', 'reviewed_by').prefetch_related('documents', 'status_logs'),
        pk=pk
    )

    old_status = app.status
    form = ApplicationReviewForm(request.POST or None, instance=app)

    if request.method == 'POST':
        if not can_change_applications:
            raise PermissionDenied("You do not have permission to modify applications.")
        if form.is_valid():
            updated_app = form.save(commit=False)
            updated_app.reviewed_by = request.user
            updated_app.save()

            # If status changed, record status log
            if old_status != updated_app.status:
                StatusLog.objects.create(
                    application=updated_app,
                    from_status=old_status,
                    to_status=updated_app.status,
                    note=updated_app.internal_notes or updated_app.citizen_response or f"Status changed to {updated_app.get_status_display()}.",
                    changed_by=request.user
                )

            messages.success(request, f"Application {app.reference} updated successfully.")
            return redirect('management:application_detail', pk=app.pk)

    return render(request, 'management/detail.html', {
        'application': app,
        'form': form,
        'documents': app.documents.all(),
        'status_logs': app.status_logs.select_related('changed_by').all(),
        'can_change_applications': can_change_applications,
    })


@login_required(login_url='management:login')
@user_passes_test(is_admin_or_staff, login_url='management:login')
def document_download(request, doc_id):
    """Secure document download for administrators only."""
    doc = get_object_or_404(ApplicationDocument, pk=doc_id)

    if not doc.file:
        raise Http404("Document file reference missing.")

    file_path = Path(doc.file.path).resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()

    # Directory traversal prevention
    try:
        file_path.relative_to(media_root)
    except ValueError:
        return HttpResponseForbidden("Access to files outside media root is forbidden.")

    if not file_path.exists() or not file_path.is_file():
        raise Http404("File not found on storage.")

    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = 'application/octet-stream'

    response = FileResponse(open(file_path, 'rb'), content_type=content_type, as_attachment=False)
    filename = doc.original_filename or file_path.name
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required(login_url='management:login')
@user_passes_test(is_admin_or_staff, login_url='management:login')
def organize_documents_view(request):
    """Invoke allfileorg package to organize uploaded documents by extension."""
    can_change_applications = request.user.is_superuser or request.user.has_perm('applications.change_application')
    if not can_change_applications:
        raise PermissionDenied("You do not have permission to organize application documents.")

    if request.method == 'POST':
        result = organize_application_documents(user=request.user)
        if result['success']:
            messages.success(request, result['message'])
        else:
            messages.error(request, result['message'])

        return redirect('management:dashboard')

    return redirect('management:dashboard')
