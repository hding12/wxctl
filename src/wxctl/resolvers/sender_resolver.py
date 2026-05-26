from __future__ import annotations

from pathlib import Path
from typing import Any

from wxctl.resolvers.target_resolver import ContactDB


class SenderResolver:
    """Resolve sender wxid to display name, enriched from contact.db if available.

    In group chats, message senders are identified by wxid in the sender_wxid field.
    This resolver provides:

    - display_name: best-effort remark / nickname / alias
    - profile fields from contact.db when available
    - Graceful degradation when contact.db is unavailable.
    """

    def __init__(self, decrypted_root: Path) -> None:
        self.contacts = ContactDB(decrypted_root)
        self._sender_cache: dict[str, dict[str, Any]] = {}

    def resolve(self, wxid: str | None) -> dict[str, Any]:
        if wxid is None:
            return {
                "wxid": None,
                "display_name": None,
                "nick_name": None,
                "remark": None,
                "alias": None,
                "verify_flag": None,
                "description": None,
                "big_head_url": None,
                "small_head_url": None,
                "head_img_md5": None,
            }

        # Check cache first
        cached = self._sender_cache.get(wxid)
        if cached is not None:
            return cached

        contact = self.contacts.normalize_contact(wxid)
        result = {
            "wxid": wxid,
            "display_name": contact.get("display_name"),
            "nick_name": contact.get("nick_name"),
            "remark": contact.get("remark"),
            "alias": contact.get("alias"),
            "verify_flag": contact.get("verify_flag"),
            "description": contact.get("description"),
            "big_head_url": contact.get("big_head_url"),
            "small_head_url": contact.get("small_head_url"),
            "head_img_md5": contact.get("head_img_md5"),
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
