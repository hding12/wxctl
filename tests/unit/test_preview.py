from __future__ import annotations

from wxctl.services.preview import format_preview_blocks, select_representative_snippets, summarize_record


def test_select_representative_snippets_prefers_latest_and_older_text():
    records = [
        {
            "ts": 1,
            "datetime": "2026-01-01 10:00:00",
            "is_self": False,
            "kind": "text",
            "text": "早一点的识别信息",
            "decoded": {},
        },
        {
            "ts": 2,
            "datetime": "2026-01-01 10:10:00",
            "is_self": True,
            "kind": "image",
            "text": None,
            "decoded": {},
        },
        {
            "ts": 3,
            "datetime": "2026-01-01 10:20:00",
            "is_self": False,
            "kind": "text",
            "text": "中间消息",
            "decoded": {},
        },
        {
            "ts": 4,
            "datetime": "2026-01-01 10:30:00",
            "is_self": True,
            "kind": "text",
            "text": "最近的一条文本消息",
            "decoded": {},
        },
    ]

    snippets = select_representative_snippets(records, count=2)

    assert len(snippets) == 2
    assert snippets[0]["summary"] == "最近的一条文本消息"
    assert snippets[1]["summary"] == "早一点的识别信息"


def test_summarize_record_falls_back_to_decoded_fields():
    record = {
        "kind": "share_card",
        "text": None,
        "decoded": {
            "title": "一篇文章",
            "description": "不应该优先拿这里",
        },
    }

    assert summarize_record(record) == "一篇文章"


def test_summarize_record_redacts_urls_emails_and_passwords():
    record = {
        "kind": "text",
        "text": "登陆邮箱：foo@example.com 密码: Secret123 https://example.com/reset",
        "decoded": {},
    }

    summary = summarize_record(record)
    assert summary == "登陆邮箱：[email] 密码: [redacted] [url]"


def test_format_preview_blocks_includes_group_sender_wxid():
    previews = [
        {
            "target_id": "123@chatroom",
            "kind": "group",
            "total_count": 10,
            "text_count": 8,
            "first_datetime": "2026-05-01 10:00:00",
            "last_datetime": "2026-05-02 10:00:00",
            "snippets": [
                {
                    "datetime": "2026-05-02 10:00:00",
                    "is_self": False,
                    "sender_wxid": "wxid_member_1",
                    "kind": "text",
                    "summary": "大家中午吃什么",
                },
                {
                    "datetime": "2026-05-02 10:01:00",
                    "is_self": True,
                    "sender_wxid": "wxid_self",
                    "kind": "text",
                    "summary": "我都可以",
                },
            ],
        }
    ]

    rendered = format_preview_blocks(previews)
    assert "wxid_member_1 text: 大家中午吃什么" in rendered
    assert "me(wxid_self) text: 我都可以" in rendered
