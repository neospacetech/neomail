from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from neomail.app import create_app, create_service
from neomail.calendar_facts import InMemoryCalendarFacts
from neomail.service import MailService
from neomail.settings import Settings
from neomail.transport import InMemoryTransport


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", stream_interval_seconds=0, tenant="acme")


@pytest.fixture
def service(settings: Settings) -> MailService:
    return create_service(settings)


@pytest.fixture
def transport(service: MailService) -> InMemoryTransport:
    assert isinstance(service.transport, InMemoryTransport)
    return service.transport


@pytest.fixture
def calendar(service: MailService) -> InMemoryCalendarFacts:
    assert isinstance(service.calendar, InMemoryCalendarFacts)
    return service.calendar


@pytest.fixture
def client(settings: Settings, service: MailService) -> Iterator[TestClient]:
    with TestClient(create_app(settings, service)) as test_client:
        yield test_client
