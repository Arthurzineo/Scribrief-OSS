import pytest

from apps.audit.models import AuditEvent


@pytest.mark.django_db
def test_successful_login_records_computer_ip_without_credentials(client, user):
    response = client.post(
        "/api/v1/login/",
        data='{"username":"ana","password":"Strong-Test-Password-123"}',
        content_type="application/json",
        REMOTE_ADDR="172.18.0.4",
        HTTP_X_REAL_IP="192.168.1.42",
        HTTP_X_FORWARDED_FOR="198.51.100.9",
    )
    assert response.status_code == 200
    event = AuditEvent.objects.get(action="login", outcome="success")
    assert event.actor == user
    assert event.client_ip == "192.168.1.42"
    assert event.peer_ip == "172.18.0.4"
    assert event.sector_id == user.membership.sector_id
    assert "Strong-Test-Password-123" not in str(event.details)


@pytest.mark.django_db
def test_failed_login_does_not_trust_direct_client_ip_header(client):
    response = client.post(
        "/api/v1/login/",
        data='{"username":"unknown","password":"wrong-password"}',
        content_type="application/json",
        REMOTE_ADDR="203.0.113.25",
        HTTP_X_REAL_IP="10.0.0.99",
    )
    assert response.status_code == 401
    event = AuditEvent.objects.get(action="login", outcome="failed")
    assert event.client_ip == "203.0.113.25"
    assert event.actor_id is None


@pytest.mark.django_db
def test_failed_unknown_logins_do_not_lock_other_user_behind_same_proxy(client, user):
    proxy_ip = "172.18.0.4"
    for index in range(5):
        response = client.post(
            "/api/v1/login/",
            data=f'{{"username":"unknown_{index}","password":"wrong-password"}}',
            content_type="application/json",
            REMOTE_ADDR=proxy_ip,
        )
        assert response.status_code in (401, 429)

    valid = client.post(
        "/api/v1/login/",
        data='{"username":"ana","password":"Strong-Test-Password-123"}',
        content_type="application/json",
        REMOTE_ADDR=proxy_ip,
    )
    assert valid.status_code == 200


@pytest.mark.django_db
def test_password_change_audit_has_ip_but_no_secret(client, user):
    client.force_login(user)
    response = client.post(
        "/api/v1/account/password/",
        data='{"currentPassword":"Strong-Test-Password-123",'
             '"newPassword":"Different-Strong-Password-456"}',
        content_type="application/json",
        REMOTE_ADDR="192.0.2.55",
    )
    assert response.status_code == 200
    event = AuditEvent.objects.get(action="password_changed")
    assert event.client_ip == "192.0.2.55"
    assert event.subject_user == user
    assert "Different-Strong-Password-456" not in str(event.details)
