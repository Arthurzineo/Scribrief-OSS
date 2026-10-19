from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.audit.health import _http_ok, save_health_sample
from apps.audit.models import AuditEvent, HealthSample, SystemEvent
from apps.audit.retention import prune_expired_audit_events
from apps.audit.usage import record_openai_usage
from apps.meetings.models import Meeting


def test_internal_http_probe_uses_fixed_host_and_does_not_follow_redirects():
    with patch('apps.audit.health.HTTPConnection') as connection:
        connection.return_value.getresponse.return_value.status = 302
        assert not _http_ok('http://backend:8000/health/', host_header='127.0.0.1')
    connection.assert_called_once_with('backend', 8000, timeout=1.5)
    connection.return_value.request.assert_called_once_with(
        'GET', '/health/', headers={'Host': '127.0.0.1'}
    )


@pytest.mark.django_db
def test_health_is_staff_only_and_reports_observed_not_fabricated_uptime(api, user, other_user):
    api.force_authenticate(user=other_user)
    assert api.get('/api/admin/health/').status_code == 403
    api.force_authenticate(user=user)
    assert api.get('/api/admin/health/').status_code == 403
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    sample = HealthSample.objects.create(
        services={'backend': 'ok', 'database': 'ok', 'redis': 'down',
                  'frontend': 'ok', 'worker': 'ok', 'storage': 'ok'},
        disk_total_bytes=1000, disk_used_bytes=400, disk_free_bytes=600,
    )
    SystemEvent.objects.create(component='worker', event_code='job_failed', severity='error')
    live = {'checked_at': timezone.now(), 'services': {
        'backend': 'ok', 'database': 'ok', 'redis': 'ok', 'frontend': 'ok',
        'worker': 'ok', 'storage': 'ok'},
        'disk': {'total_bytes': 1000, 'used_bytes': 400, 'free_bytes': 600}}
    with patch('apps.admin_panel.views.health.collect_live_health', return_value=live):
        response = api.get('/api/admin/health/')
    assert response.status_code == 200
    assert response.data['services']['sampling'] == 'ok'
    assert response.data['availability_24h']['redis'] == {
        'online_minutes_observed': 0, 'minutes_observed': 5,
        'sample_count': 1, 'expected_sample_count': 288,
    }
    assert response.data['errors_24h']['system_events'] == 1
    assert response.data['latest_sample_at'] == sample.created_at
    assert 'usage' not in response.data


@pytest.mark.django_db
def test_stale_sample_is_not_reported_as_uptime(api, user):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    sample = HealthSample.objects.create(services={'backend': 'ok'})
    HealthSample.objects.filter(pk=sample.pk).update(created_at=timezone.now() - timedelta(days=2))
    live = {'checked_at': timezone.now(), 'services': {'backend': 'ok'},
            'disk': {'total_bytes': None, 'used_bytes': None, 'free_bytes': None}}
    with patch('apps.admin_panel.views.health.collect_live_health', return_value=live):
        response = api.get('/api/admin/health/')
    assert response.data['services']['sampling'] == 'down'
    assert response.data['availability_24h']['backend']['minutes_observed'] == 0


@pytest.mark.django_db
def test_sample_task_persists_only_sanitized_telemetry_and_retention(user):
    live = {'checked_at': timezone.now(), 'services': {'backend': 'ok'},
            'disk': {'total_bytes': 1000, 'used_bytes': 400, 'free_bytes': 600}}
    with patch('apps.audit.health.collect_live_health', return_value=live) as probe:
        sample = save_health_sample()
    probe.assert_called_once_with(from_worker=True)
    assert sample.services == {'backend': 'ok'}
    assert sample.disk_free_bytes == 600
    HealthSample.objects.filter(pk=sample.pk).update(created_at=timezone.now() - timedelta(days=91))
    result = prune_expired_audit_events()
    assert result['health_deleted'] == 1
    assert not HealthSample.objects.filter(pk=sample.pk).exists()
    assert AuditEvent.objects.filter(action='health_retention_purge').exists()


@pytest.mark.django_db
def test_usage_summary_tokens_are_measured_and_missing_is_not_zero(api, user):
    meeting = Meeting.objects.create(owner=user, title='Tokens')
    context = {'sector_id': meeting.sector_id, 'user_id': user.pk,
               'meeting_id': meeting.pk, 'operation': 'minutes', 'key_version': 1}
    record_openai_usage(SimpleNamespace(
        usage={'input_tokens': 100, 'output_tokens': 20}, _request_id='health-token-1'
    ), context, 'gpt-6-luna')
    record_openai_usage(SimpleNamespace(
        usage={'seconds': 300}, _request_id='health-token-2'
    ), context, 'gpt-4o-transcribe-diarize')
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    response = api.get('/api/admin/usage/summary/')
    assert response.status_code == 200
    assert response.data['totals']['calls'] == 2
    assert response.data['totals']['total_tokens'] == 120
    assert response.data['totals']['token_calls'] == 1
    assert response.data['totals']['unavailable'] == 1
    assert response.data['by_sector'][0]['total_tokens'] == 120
