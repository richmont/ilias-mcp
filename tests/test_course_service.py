from unittest.mock import Mock

import pytest
import requests

from core.config import Settings
from services.auth_service import AuthService
from services.course_service import CourseService


def _service() -> CourseService:
    settings = Settings(
        ilias_user="test-user",
        ilias_pass="test-password",
        ilias_base_url="https://example.com",
        ilias_client_id="academy",
    )
    session = Mock(spec=requests.Session)
    return CourseService(settings, session, AuthService(settings, session))


@pytest.mark.parametrize(
    "href",
    [
        "/go/crs/123",
        "/go/grp/123/",
        "/goto.php/crs/123",
        "https://example.com/goto.php/grp/123",
        "/goto.php?target=crs_123&client_id=academy",
        "/goto.php?target=grp_123",
    ],
)
def test_course_and_group_link_formats(href: str) -> None:
    course = _service()._course_from_link(href, " Test membership ")
    assert course is not None
    assert course.title == "Test membership"
    assert course.ref_id == "123"
    assert course.url.startswith("https://example.com/")


@pytest.mark.parametrize(
    "href",
    ["/goto.php/fold/123", "/goto.php?target=file_123", "/go/crs/invalid", "/search"],
)
def test_unrelated_links_are_not_courses(href: str) -> None:
    assert _service()._course_from_link(href, "Not a course") is None


def test_membership_extraction_includes_groups_and_deduplicates() -> None:
    courses = _service()._extract_courses(
        '<div class="il-item-group-items">'
        '<a href="/goto.php/crs/123">Course</a>'
        '<a href="/goto.php/grp/456">Group</a>'
        '<a href="/goto.php/grp/456">Group</a>'
        '<a href="/goto.php/fold/789">Folder</a>'
        "</div>"
    )
    assert [(c.title, c.ref_id) for c in courses] == [
        ("Course", "123"),
        ("Group", "456"),
    ]
