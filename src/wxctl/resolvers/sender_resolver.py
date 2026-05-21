from __future__ import annotations

from pathlib import Path
from typing import Any

from wxctl.resolvers.target_resolver import ContactDB


class SenderResolver:
    """Resolve sender wxid to display name, enriched from contact.db if available.

    In group chats, message senders are identified by wxid in the sender_wxid field.
    This resolver provides:

    - display_name: best-effort nickname or alias
    - avatar: candidate avatar path if available
    - Graceful degradation when contact.db is unavailable.
    """

    def __init__(self, decrypted_root: Path) -> None:
        self.contacts = ContactDB(decrypted_root)
        self._sender_cache: dict[str, dict[str, Any]] = {}

    def resolve(self, wxid: str | None) -> dict[str, Any]:
        if wxid is None:
            return {"wxid": None, "display_name": None, "avatar": None}

        # Check cache first
        cached = self._sender_cache.get(wxid)
        if cached is not None:
            return cached

        # Look up from contact.db
        contact = self.contacts.lookup(wxid)
        if contact:
            display_name = (
                contact.get("remark")
                or contact.get("nick_name")
                or wxid
            )
            result = {
                "wxid": wxid,
                "display_name": display_name,
                "nick_name": contact.get("nick_name"),
                "remark": contact.get("remark"),
            }
        else:
            result = {
                "wxid": wxid,
                "display_name": wxid,
                "nick_name": None,
                "remark": None,
            }

        self._sender_cache[wxid] = result
        return result

    def batch_resolve(self, wxids: list[str]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for wxid in wxids:
            if wxid:
                results[wxid] = self.resolve(wxid)
        return results

    @property
    def available(self) -> bool:
        return self.contacts.available

    def close(self) -> None:
        self.contacts.close()
