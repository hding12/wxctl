from wxctl.decoders.registry import decode_message, DecodeContext


def test_text_decoder_round_trip():
    result = decode_message(
        1,
        "hello world",
        None,
        DecodeContext(conversation_hash="abc", xwechat_root="/tmp", self_wxid="wxid_self"),
    )
    assert result.kind == "text"
    assert result.text == "hello world"
    assert result.decoded["text"] == "hello world"
