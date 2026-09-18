from app.kdocs import KdocsError, parse_share_id
from app.status import infer_code_from_text, is_delivered_text, label_for
from app.sheet import extract_tracking_numbers
from app.trackers.router import normalize_carrier
import pytest


def test_parse_share_id():
    assert parse_share_id("https://www.kdocs.cn/l/ccWzub8j0jIm") == "ccWzub8j0jIm"
    assert parse_share_id("ccWzub8j0jIm") == "ccWzub8j0jIm"
    with pytest.raises(KdocsError):
        parse_share_id("https://example.com/sheet")


def test_extract_tracking_numbers():
    assert extract_tracking_numbers("9214490422577138214308") == ["9214490422577138214308"]
    assert extract_tracking_numbers("84120000348073换84120000348098") == [
        "84120000348073",
        "84120000348098",
    ]
    text = "头盔单号：84120000350967\n鞋子+玩具单号：84120000350968"
    assert extract_tracking_numbers(text) == ["84120000350967", "84120000350968"]
    assert extract_tracking_numbers(" \nEWSUC260905001119YQ") == ["EWSUC260905001119YQ"]
    assert extract_tracking_numbers("1Z1B0D750301336987") == ["1Z1B0D750301336987"]


def test_delivered_and_labels():
    assert is_delivered_text("签收")
    assert is_delivered_text("Delivered")
    assert not is_delivered_text("运输中")
    assert label_for("in_transit") == "运输中"
    assert infer_code_from_text("Label Created") == "label_created"
    assert infer_code_from_text("USPS Awaiting Item") == "awaiting_carrier"
    assert infer_code_from_text("成功签收") == "delivered"


def test_normalize_carrier():
    assert normalize_carrier("EWSMM260824000268YQ") == "8dt"
    assert normalize_carrier("1Z1B0D750301336987") == "ups"
    assert normalize_carrier("9214490401713208515907") == "usps"
    assert normalize_carrier("876289347460") == "fedex"
    assert normalize_carrier("84120000352967") == "dpd"
    assert normalize_carrier("816004263130") == "tgx"
    assert normalize_carrier("7321315926128844", "Canada Post") == "canada_post"
