import os
import shutil
import logging
from pathlib import Path
from django.conf import settings
from django.db import transaction
from fileorg import FileOrganizer

from ..applications.models import ApplicationDocument

logger = logging.getLogger(__name__)


def organize_application_documents(user=None):
    """
    Safely organize uploaded application documents using the published allfileorg package.
    
    1. Identifies unorganized application documents.
    2. Runs FileOrganizer from source directory to target organized directory.
    3. Updates ApplicationDocument records (file path, category, organization status).
    4. Preserves application-document relationships and Django storage compatibility.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    target_dir = media_root / 'documents' / 'organized'
    target_dir.mkdir(parents=True, exist_ok=True)

    unorganized_docs = ApplicationDocument.objects.filter(
        organization_status__in=[
            ApplicationDocument.OrganizationStatus.UNORGANIZED,
            ApplicationDocument.OrganizationStatus.FAILED,
            ApplicationDocument.OrganizationStatus.SKIPPED,
        ]
    )

    if not unorganized_docs.exists():
        return {
            'success': True,
            'message': 'All documents are already organized.',
            'total_scanned': 0,
            'total_moved': 0,
            'total_errors': 0,
            'category_counts': {},
            'records': []
        }

    # Create an isolated staging directory for this batch inside MEDIA_ROOT
    staging_dir = media_root / 'documents' / 'staging'
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Map file paths in staging to doc objects
    staged_map = {}
    
    for doc in unorganized_docs:
        try:
            if not doc.file or not os.path.exists(doc.file.path):
                doc.organization_status = ApplicationDocument.OrganizationStatus.FAILED
                doc.save(update_fields=['organization_status'])
                continue

            current_path = Path(doc.file.path).resolve()
            # Ensure path is strictly within media_root
            if not str(current_path).startswith(str(media_root)):
                logger.warning(f"Skipping document outside media root: {current_path}")
                continue

            # Stage the file using a safe filename preserving extension
            stem = Path(doc.original_filename).stem if doc.original_filename else current_path.stem
            ext = current_path.suffix
            staged_filename = f"{doc.application.reference}_{doc.id}_{stem}{ext}"
            staged_path = staging_dir / staged_filename

            # Move or copy to staging
            shutil.move(str(current_path), str(staged_path))
            staged_map[str(staged_path.resolve())] = doc

        except Exception as e:
            logger.error(f"Error staging document {doc.id}: {e}")
            doc.organization_status = ApplicationDocument.OrganizationStatus.FAILED
            doc.save(update_fields=['organization_status'])

    if not staged_map:
        return {
            'success': False,
            'message': 'No valid document files could be prepared for organization.',
            'total_scanned': 0,
            'total_moved': 0,
            'total_errors': unorganized_docs.count(),
            'category_counts': {},
            'records': []
        }

    # Run the real allfileorg FileOrganizer
    try:
        organizer = FileOrganizer(
            source_dir=staging_dir,
            target_dir=target_dir,
            conflict_strategy='rename',
            dry_run=False,
            recursive=False
        )
        summary = organizer.organize()
    except Exception as e:
        logger.exception(f"FileOrganizer execution failed: {e}")
        # Mark all staged as failed
        for doc in staged_map.values():
            doc.organization_status = ApplicationDocument.OrganizationStatus.FAILED
            doc.save(update_fields=['organization_status'])
        return {
            'success': False,
            'message': f'Organization failed: {str(e)}',
            'total_scanned': 0,
            'total_moved': 0,
            'total_errors': len(staged_map),
            'category_counts': {},
            'records': []
        }

    # Process allfileorg MoveRecord results
    moved_count = 0
    error_count = 0
    records_info = []

    with transaction.atomic():
        for record in summary.records:
            source_abs = str(Path(record.source).resolve())
            doc = staged_map.get(source_abs)

            rec_dict = {
                'source': Path(record.source).name,
                'category': record.category,
                'status': record.status,
                'error': record.error_message,
                'destination': Path(record.destination).name if record.destination else None
            }
            records_info.append(rec_dict)

            if not doc:
                continue

            if record.status == 'moved' and record.destination:
                dest_path = Path(record.destination).resolve()
                # Compute relative path to MEDIA_ROOT for Django FileField
                rel_media_path = dest_path.relative_to(media_root).as_posix()

                doc.file.name = rel_media_path
                doc.organized_category = record.category or 'General'
                doc.organized_path = rel_media_path
                doc.organization_status = ApplicationDocument.OrganizationStatus.ORGANIZED
                doc.save(update_fields=['file', 'organized_category', 'organized_path', 'organization_status'])
                moved_count += 1
            elif record.status == 'skipped':
                doc.organization_status = ApplicationDocument.OrganizationStatus.SKIPPED
                doc.save(update_fields=['organization_status'])
            else:
                doc.organization_status = ApplicationDocument.OrganizationStatus.FAILED
                doc.save(update_fields=['organization_status'])
                error_count += 1

    # Cleanup staging directory if empty
    try:
        for f in staging_dir.iterdir():
            if f.is_file():
                # If any file was left behind in staging, move to unorganized/failed
                pass
    except Exception:
        pass

    return {
        'success': True,
        'message': f"Organized {moved_count} document(s) successfully across {len(summary.category_counts)} categories.",
        'total_scanned': summary.total_files_scanned,
        'total_moved': moved_count,
        'total_errors': error_count + summary.total_errors,
        'category_counts': summary.category_counts,
        'records': records_info
    }
