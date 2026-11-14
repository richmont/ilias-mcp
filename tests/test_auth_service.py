from unittest.mock import Mock

import pytest
import requests

from core.config import Settings
from services.auth_service import AuthService, IliasAuthError

LOGGED_IN_PAGE = """
<html><body>
  <a href="/logout.php?cmd=doLogout">Abmelden</a>
  <h1>Angemeldet</h1>
</body></html>
"""

LOGIN_PAGE = """
<html><body>
  <form action="/login.php?cmd=force_login">
    <input name="username"><input name="password" type="password">
    <input name="cmd[doStandardAuthentication]" value="Anmelden">
  </form>
</body></html>
"""


def _response(body: str, content_type: str = "text/html; charset=UTF-8"):
    resp = requests.Response()
    resp.status_code = 200
    resp._content = body.encode()
    resp.headers["Content-Type"] = content_type
    return resp


def test_expired_session_page_is_recognised() -> None:
    # ILIAS answers an expired session with HTTP 200 and the login form.
    assert AuthService._looks_like_login_page(_response(LOGIN_PAGE)) is True


def test_authenticated_page_is_not_mistaken_for_login() -> None:
    assert AuthService._looks_like_login_page(_response(LOGGED_IN_PAGE)) is False


def test_binary_download_is_never_treated_as_login_page() -> None:
    # A PDF must not be decoded and sniffed for login markers.
    resp = _response("%PDF-1.7 nonsense", content_type="application/pdf")
    assert AuthService._looks_like_login_page(resp) is False


@pytest.mark.parametrize("legacy_submit", [False, True])
def test_login_selects_password_form_instead_of_search(legacy_submit: bool) -> None:
    submit = (
        '<input name="cmd[doStandardAuthentication]" value="Anmelden">'
        if legacy_submit
        else ""
    )
    page = _response(
        '<form action="/search"><input type="text" name="queryString"></form>'
        '<form action="ilias.php?fallbackCmd=doStandardAuthentication" method="post">'
        '<input type="hidden" name="csrf_token" value="test-token">'
        '<input type="text" name="login_form/user">'
        '<input type="password" name="login_form/password">'
        f"{submit}</form>"
    )
    page.url = "https://example.com/ilias/login.php"
    session = Mock(spec=requests.Session)
    session.get.side_effect = [page, _response(LOGGED_IN_PAGE)]
    session.post.return_value = _response(LOGGED_IN_PAGE)
    settings = Settings(
        ilias_user="test-user",
        ilias_pass="test-password",
        ilias_base_url="https://example.com/ilias",
        ilias_client_id="academy",
    )
    auth = AuthService(settings, session)

    assert auth.login() == "Login successful."
    args, kwargs = session.post.call_args
    assert args[0] == (
        "https://example.com/ilias/ilias.php?fallbackCmd=doStandardAuthentication"
    )
    expected = {
        "csrf_token": "test-token",
        "login_form/user": "test-user",
        "login_form/password": "test-password",
    }
    if legacy_submit:
        expected["cmd[doStandardAuthentication]"] = "Anmelden"
    assert kwargs["data"] == expected
    assert auth.login() == "Already logged in."
    assert session.post.call_count == 1


def test_login_rejects_search_only_page_without_posting_credentials() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = _response(
        '<form action="/search"><input type="text" name="queryString"></form>'
    )
    settings = Settings(
        ilias_user="test-user",
        ilias_pass="test-password",
        ilias_base_url="https://example.com",
        ilias_client_id="academy",
    )
    auth = AuthService(settings, session)

    with pytest.raises(IliasAuthError, match="Login form not found"):
        auth.login()
    session.post.assert_not_called()
