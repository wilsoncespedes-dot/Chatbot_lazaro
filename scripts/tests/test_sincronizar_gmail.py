"""R15-R16: selección de canales Gmail y errores del scheduler."""
from __future__ import annotations

import httpx

from scripts.sincronizar_gmail import run


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, fail_id=None):
        self.fail_id = fail_id
        self.posts = []

    def get(self, *args, **kwargs):
        return FakeResponse({"channels": [
            {"id": "gmail-on", "adapter_type": "gmail_api", "active": True},
            {"id": "gmail-off", "adapter_type": "gmail_api", "active": False},
            {"id": "telegram", "adapter_type": "telegram", "active": True},
        ]})

    def post(self, url, **kwargs):
        self.posts.append(url)
        status = 500 if self.fail_id and url.endswith(self.fail_id + "/gmail/sync") else 200
        return FakeResponse({"processed": 1, "status": "synced"}, status)


def test_scheduler_syncs_only_active_gmail_channels():
    """R15: el scheduler selecciona solo adaptadores Gmail activos."""
    client = FakeClient()
    assert run(client, "http://gateway", "secret") is True
    assert client.posts == ["http://gateway/channels/gmail-on/gmail/sync"]


def test_scheduler_fails_when_one_gmail_channel_fails():
    """R16: un canal fallido produce resultado global fallido."""
    assert run(FakeClient(fail_id="gmail-on"), "http://gateway", "secret") is False
