from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.config import Settings
from domain.models import Course
from services.auth_service import AuthService


class IliasCourseError(RuntimeError):
    pass


class CourseService:
    def __init__(
        self, settings: Settings, session: requests.Session, auth_service: AuthService
    ) -> None:
        self.settings = settings
        self.session = session
        self.auth_service = auth_service

    def list_courses(self) -> list[Course]:
        try:
            resp = self.auth_service.get(self.settings.memberships_url)
        except requests.RequestException as exc:
            raise IliasCourseError(f"Failed to fetch memberships page: {exc}") from exc
        return self._extract_courses(resp.text)

    def _extract_courses(self, html: str) -> list[Course]:
        soup = BeautifulSoup(html, "html.parser")
        found: list[Course] = []
        containers = soup.select("div.il-item-group-items")

        if containers:
            for container in containers:
                for a in container.find_all("a", href=True):
                    course = self._course_from_link(
                        a.get("href", ""), a.get_text(" ", strip=True)
                    )
                    if course:
                        found.append(course)
        else:
            for a in soup.find_all("a", href=True):
                course = self._course_from_link(
                    a.get("href", ""), a.get_text(" ", strip=True)
                )
                if course:
                    found.append(course)

        dedup: dict[str, Course] = {}
        for course in found:
            dedup[course.url] = course

        return list(dedup.values())

    def _course_from_link(self, href: str, text: str) -> Course | None:
        href = href.strip()
        parsed = urlparse(href)
        path_match = re.search(r"/(?:go|goto\.php)/(?:crs|grp)/(\d+)/?$", parsed.path)
        target = parse_qs(parsed.query).get("target", [""])[0]
        target_match = re.fullmatch(r"(?:crs|grp)_(\d+)", target)
        if not path_match and not target_match:
            return None

        title = " ".join(text.split()).strip()
        if len(title) < 3:
            return None

        url = (
            href
            if href.startswith("http")
            else urljoin(self.settings.ilias_base_url, href)
        )
        ref_id = self._extract_ref_id(url)
        return Course(title=title, url=url, ref_id=ref_id)

    @staticmethod
    def _extract_ref_id(url: str) -> str:
        parsed = urlparse(url)
        target = parse_qs(parsed.query).get("target", [""])[0]
        target_match = re.fullmatch(r"(?:crs|grp)_(\d+)", target)
        if target_match:
            return target_match.group(1)
        path = parsed.path.rstrip("/")
        return path.split("/")[-1] if path else ""
