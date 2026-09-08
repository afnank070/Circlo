"""Admin user management on /admin/settings — access control + role flips."""
from app.extensions import db
from app.models import User
from app.models.user import ROLE_ADMIN, ROLE_USER
from app.services import admin_users as admin_users_service
from app.services import auth as auth_service


def _user(email, *, admin=False):
    u = auth_service.create_user(email.split("@")[0], email, "supersecret",
                                 phone="03001234567")
    if admin:
        u.role = ROLE_ADMIN
    db.session.commit()
    return u


def _login(client, email):
    client.post("/login", data={"email": email, "password": "supersecret"})


# --- access control ------------------------------------------------------
def test_non_admin_cannot_view_settings_or_hit_role_routes(client, app):
    with app.app_context():
        _user("user@example.com")
        target = _user("target@example.com")
        tid = target.id
    _login(client, "user@example.com")

    assert client.get("/admin/settings").status_code == 403
    assert client.post(f"/admin/users/{tid}/promote").status_code == 403
    assert client.post(f"/admin/users/{tid}/revoke").status_code == 403
    with app.app_context():
        assert db.session.get(User, tid).role == ROLE_USER


def test_anonymous_is_redirected_to_login(client, app):
    with app.app_context():
        tid = _user("t@example.com").id
    assert client.get("/admin/settings").status_code == 302
    assert client.post(f"/admin/users/{tid}/promote").status_code == 302


def test_admin_sees_user_list(client, app):
    with app.app_context():
        _user("admin@example.com", admin=True)
        _user("alice@example.com")
    _login(client, "admin@example.com")
    body = client.get("/admin/settings").data
    assert b"User management" in body
    assert b"alice@example.com" in body
    assert b"Promote to admin" in body


# --- promote / revoke ---------------------------------------------------
def test_admin_promotes_and_revokes(client, app):
    with app.app_context():
        _user("admin@example.com", admin=True)
        bob = _user("bob@example.com")
        bid = bob.id
    _login(client, "admin@example.com")

    client.post(f"/admin/users/{bid}/promote", follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, bid).role == ROLE_ADMIN

    client.post(f"/admin/users/{bid}/revoke", follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, bid).role == ROLE_USER


def test_admin_cannot_revoke_their_own_access_via_route(client, app):
    with app.app_context():
        me = _user("admin@example.com", admin=True)
        mid = me.id
    _login(client, "admin@example.com")

    resp = client.post(f"/admin/users/{mid}/revoke", follow_redirects=True)
    assert resp.status_code == 200
    assert b"can&#39;t revoke your own admin access" in resp.data
    with app.app_context():
        assert db.session.get(User, mid).role == ROLE_ADMIN


def test_self_revoke_blocked_at_service_layer(app):
    with app.app_context():
        me = _user("admin@example.com", admin=True)
        try:
            admin_users_service.revoke_admin(me, me.id)
            assert False, "expected CannotChangeOwnRole"
        except admin_users_service.CannotChangeOwnRole:
            pass
        assert db.session.get(User, me.id).role == ROLE_ADMIN


def test_service_search_filters_by_name_or_email(app):
    with app.app_context():
        _user("admin@example.com", admin=True)
        _user("charlie@example.com")
        _user("dave@elsewhere.test")

        by_email = admin_users_service.list_users("elsewhere")
        assert [u.email for u in by_email] == ["dave@elsewhere.test"]

        by_name = admin_users_service.list_users("charlie")
        assert [u.email for u in by_name] == ["charlie@example.com"]

        # admins sort first
        everyone = admin_users_service.list_users()
        assert everyone[0].role == ROLE_ADMIN
