"""Comprehensive unit tests for all decoder types.

Tests each message kind with golden XML fixtures where available,
verifying kind classification, text extraction, and decoded structure.
"""

from wxctl.decoders.registry import decode_message

from tests.unit.conftest import assert_decode_result, decode_ctx, load_golden  # noqa: F401


class TestTextDecoder:
    def test_basic_text(self, decode_ctx):
        result = decode_message(1, "hello world", None, decode_ctx)
        assert_decode_result(result, kind="text")
        assert result.text == "hello world"
        assert result.decoded["text"] == "hello world"

    def test_empty_text(self, decode_ctx):
        result = decode_message(1, "", None, decode_ctx)
        assert_decode_result(result, kind="text")
        assert result.text == ""

    def test_unicode_text(self, decode_ctx):
        text = "你好世界 🌍"
        result = decode_message(1, text, None, decode_ctx)
        assert_decode_result(result, kind="text")
        assert result.text == text

    def test_bytes_text(self, decode_ctx):
        result = decode_message(1, b"hello bytes", None, decode_ctx)
        assert_decode_result(result, kind="text")
        assert result.text == "hello bytes"


class TestImageDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("image_msg.xml")
        result = decode_message(3, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="image")
        assert "aeskey" in result.decoded
        assert "md5" in result.decoded
        assert result.decoded["md5"] == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

    def test_null_content(self, decode_ctx):
        result = decode_message(3, None, None, decode_ctx)
        assert_decode_result(result, kind="image")
        assert result.decoded == {}


class TestVoiceDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("voice_msg.xml")
        result = decode_message(34, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="voice")
        assert result.decoded.get("voicelength") == "3421"

    def test_null_content(self, decode_ctx):
        result = decode_message(34, None, None, decode_ctx)
        assert_decode_result(result, kind="voice")
        assert result.decoded == {}


class TestVideoDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("video_msg.xml")
        result = decode_message(43, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="video")
        assert result.decoded.get("cdnvideolength") == "987654"

    def test_null_content(self, decode_ctx):
        result = decode_message(43, None, None, decode_ctx)
        assert_decode_result(result, kind="video")
        assert result.decoded == {}


class TestEmojiDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("emoji_msg.xml")
        result = decode_message(47, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="emoji")
        assert result.decoded.get("md5") == "e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6"

    def test_null_content(self, decode_ctx):
        result = decode_message(47, None, None, decode_ctx)
        assert_decode_result(result, kind="emoji")
        assert result.decoded == {}


class TestVoipDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("voip_msg.xml")
        result = decode_message(50, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="voip")

    def test_null_content(self, decode_ctx):
        result = decode_message(50, None, None, decode_ctx)
        assert_decode_result(result, kind="voip")
        assert result.decoded == {}


class TestSystemDecoder:
    def test_revoke_message(self, decode_ctx):
        xml_text = load_golden("system_revoke_msg.xml")
        result = decode_message(10000, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="system")
        assert "recalled" in (result.text or "")
        assert "xml" in result.decoded

    def test_null_content(self, decode_ctx):
        result = decode_message(10000, None, None, decode_ctx)
        assert_decode_result(result, kind="system")
        assert result.decoded == {}

    def test_generic_system_xml(self, decode_ctx):
        xml = "<sysmsg type='some_event'>Someone joined the group</sysmsg>"
        result = decode_message(10000, xml.encode(), None, decode_ctx)
        assert_decode_result(result, kind="system")


class TestShareCardDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("share_card_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="share_card")
        assert result.text == "A Great Article"
        assert result.decoded.get("appid") == "wx1234567890abcdef"


class TestFileShareDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("file_share_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="file_share")
        assert result.text == "document.pdf"

    def test_file_metadata(self, decode_ctx):
        xml_text = load_golden("file_share_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert int(result.decoded["appattach"]["totallen"]) > 0
        assert result.decoded["appattach"]["fileext"] == "pdf"


class TestQuoteReplyDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("quote_reply_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="quote_reply")
        assert result.text == "Original Message"

    def test_refermsg_content(self, decode_ctx):
        xml_text = load_golden("quote_reply_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        refermsg = result.decoded.get("refermsg", {})
        assert refermsg.get("content") == "this is the original quoted message"


class TestMiniProgramDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("mini_program_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="mini_program")
        assert result.text == "Mini Program Demo"

    def test_weappinfo(self, decode_ctx):
        xml_text = load_golden("mini_program_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert result.decoded.get("appid") == "wx1234567890abcdef"


class TestLocationDecoder:
    def test_golden_fixture(self, decode_ctx):
        xml_text = load_golden("location_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert_decode_result(result, kind="location")
        assert result.text == "My Location"

    def test_location_coordinates(self, decode_ctx):
        xml_text = load_golden("location_msg.xml")
        result = decode_message(21474836529, xml_text.encode(), None, decode_ctx)
        assert "map.qq.com" in (result.decoded.get("url") or "")
        assert result.decoded.get("type") == "36"


class TestAppmsgTypeVariants:
    def test_url_card_type_1(self, decode_ctx):
        """Type 1 URL card should be share_card."""
        xml = '<msg><appmsg><type>1</type><title>News</title><url>https://example.com</url></appmsg></msg>'
        result = decode_message(21474836529, xml.encode(), None, decode_ctx)
        assert_decode_result(result, kind="share_card")
        assert result.text == "News"

    def test_transfer_type_63(self, decode_ctx):
        """Type 63 transfer notification."""
        xml = '<msg><appmsg><type>63</type><title>Money Transfer</title></appmsg></msg>'
        result = decode_message(21474836529, xml.encode(), None, decode_ctx)
        assert_decode_result(result, kind="transfer")

    def test_payment_type_10000000(self, decode_ctx):
        """Type 10000000 payment notification."""
        xml = '<msg><appmsg><type>10000000</type><title>Payment Received</title></appmsg></msg>'
        result = decode_message(21474836529, xml.encode(), None, decode_ctx)
        assert_decode_result(result, kind="payment")

    def test_unknown_appmsg_type(self, decode_ctx):
        """Unknown appmsg type should fall back to appmsg kind."""
        xml = '<msg><appmsg><type>9999</type><title>Weird Type</title></appmsg></msg>'
        result = decode_message(21474836529, xml.encode(), None, decode_ctx)
        assert_decode_result(result, kind="appmsg")

    def test_other_appmsg_raw_types(self, decode_ctx):
        """Different raw_type values that all decode to appmsg."""
        xml = '<msg><appmsg><type>5</type><title>Hello</title></appmsg></msg>'
        for raw_type in [244813135921, 25769803825, 318767153, 436207661, 822083633, 1000000000]:
            result = decode_message(raw_type, xml.encode(), None, decode_ctx)
            assert result.kind in ("share_card", "appmsg"), f"raw_type={raw_type} gave kind={result.kind}"


class TestUnknownDecoder:
    def test_unknown_type(self, decode_ctx):
        result = decode_message(999, b"some data", None, decode_ctx)
        assert_decode_result(result, kind="unknown")
        assert result.decoded["raw_type"] == 999


class TestEdgeCases:
    def test_null_all_fields(self, decode_ctx):
        result = decode_message(1, None, None, decode_ctx)
        assert_decode_result(result, kind="text")
        assert result.text == ""

    def test_malformed_xml(self, decode_ctx):
        result = decode_message(3, b"<broken>xml<", None, decode_ctx)
        assert_decode_result(result, kind="image")
        assert result.decoded == {}

    def test_empty_xml(self, decode_ctx):
        result = decode_message(34, b"", None, decode_ctx)
        assert_decode_result(result, kind="voice")
        # empty bytes decompiles to empty string, which safe_xml returns None

    def test_unknown_type_with_content(self, decode_ctx):
        result = decode_message(8888, b"<some>random</some>", None, decode_ctx)
        assert_decode_result(result, kind="unknown")
        assert result.decoded["raw_type"] == 8888
