"""
Messaging API — conversations and messages.

All endpoints use finn-gw-service: MESSAGING-API.

Endpoints:
  GET  /public/users/{userId}/unreadmessagecount
  GET  /public/users/{userId}/conversationgroups
  GET  /public/users/{userId}/conversationgroups/recommerce/{adId}
  POST /public/users/{userId}/conversations/check
  GET  /public/users/{userId}/conversations/{convId}
  GET  /public/users/{userId}/conversations/{convId}/messages
  POST /public/users/{userId}/conversations/{convId}/messages
  POST /public/users/{userId}/conversations
  GET  /public/users/{userId}/blocks/{targetUserId}
  GET  /contact/ads/{adId}                        (AD-CONTACT-CONFIG)
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .client import ToriClient

_SVC = "MESSAGING-API"


class MessagingAPI:
    def __init__(self, client: "ToriClient"):
        self._c = client

    @property
    def _uid(self) -> int:
        return self._c.user_id

    def unread_count(self) -> int:
        """Total unread messages across all conversations."""
        data = self._c.get(
            f"/public/users/{self._uid}/unreadmessagecount", _SVC
        )
        return data.get("unreadMessageCount") or data.get("counter", 0)

    def list_conversations(
        self,
        limit: int = 20,
        offset: int = 0,
        conversations_per_group: int = 10,
    ) -> list:
        """
        Paginated list of conversation groups (grouped by listing).

        Each group has:
          groupBasis.itemInfo — listing title, thumbnail, price
          conversations[]     — individual conversations within the group
        """
        qs = urllib.parse.urlencode({
            "limit": limit,
            "offset": offset,
            "numberOfConversationsInGroup": conversations_per_group,
        })
        return self._c.get(
            f"/public/users/{self._uid}/conversationgroups?{qs}", _SVC
        )

    def conversations_for_listing(
        self, ad_id: int, limit: int = 20, offset: int = 0
    ) -> dict:
        """All conversations for a specific listing."""
        qs = urllib.parse.urlencode({"limit": limit, "offset": offset})
        return self._c.get(
            f"/public/users/{self._uid}/conversationgroups/recommerce/{ad_id}?{qs}",
            _SVC,
        )

    def get_conversation(self, conversation_id: int) -> dict:
        """Full conversation metadata."""
        return self._c.get(
            f"/public/users/{self._uid}/conversations/{conversation_id}", _SVC
        )

    def list_messages(
        self, conversation_id: str, limit: int = 50, offset: int = 0
    ) -> list:
        """
        Messages in a conversation, newest-first by default.

        Each message has: id, body, type, sent, outgoing (bool)
        """
        qs = urllib.parse.urlencode({"limit": limit, "offset": offset})
        data = self._c.get(
            f"/public/users/{self._uid}/conversations/{conversation_id}/messages?{qs}",
            _SVC,
        )
        if isinstance(data, list):
            return data
        return data.get("messageResponseList", data.get("messages", []))

    def send(self, conversation_id: str, text: str) -> dict:
        """
        Send a text message in an existing conversation.

        Returns the created message object.
        """
        return self._c.post(
            f"/public/users/{self._uid}/conversations/{conversation_id}/messages",
            _SVC,
            {"messageType": "textMessage", "text": text},
        )

    def start_conversation(self, ad_id: int, text: str, item_type: str = "recommerce") -> dict:
        """
        Start a new conversation with a seller (first message).

        item_type: "recommerce" for recommerce listings, "Ad" for classifieds
        """
        return self._c.post(
            f"/public/users/{self._uid}/conversations",
            _SVC,
            {
                "adId": ad_id,
                "itemType": item_type,
                "messageType": "textMessage",
                "text": text,
            },
        )

    def is_blocked(self, target_user_id: int) -> bool:
        """Check whether you have blocked another user."""
        data = self._c.get(
            f"/public/users/{self._uid}/blocks/{target_user_id}", _SVC
        )
        return data.get("blocked", False)

    def seller_info(self, ad_id: int) -> dict:
        """
        Seller/contact info for an ad before starting a conversation.
        Uses finn-gw-service: AD-CONTACT-CONFIG.
        """
        return self._c.get(f"/contact/ads/{ad_id}", "AD-CONTACT-CONFIG")
