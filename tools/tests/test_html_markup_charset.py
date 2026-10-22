"""A page that declares Latin-1 but holds UTF-8 bytes reads as UTF-8 (rendered-DOM captures)."""

from bs4 import BeautifulSoup

from corpus.transforms.html import EL_PARSER_ID, markup, total_element_count

LIE = (
    '<html><head><meta charset="iso-8859-1"></head>'
    "<body><p>Kanda Sudachō · TÜV</p></body></html>"
)


def test_utf8_bytes_under_latin1_meta_decode_as_utf8():
    out = markup(LIE.encode("utf-8"))
    assert isinstance(out, str)
    assert "Kanda Sudachō · TÜV" in BeautifulSoup(out, EL_PARSER_ID).get_text()


def test_real_latin1_page_keeps_its_declaration():
    raw = LIE.replace("ō · ", "").encode("latin-1")  # "TÜV" as one Latin-1 byte: invalid UTF-8
    assert markup(raw) is raw
    assert "TÜV" in BeautifulSoup(raw, EL_PARSER_ID).get_text()


def test_other_declarations_and_ascii_pass_through_as_bytes():
    utf8 = LIE.replace("iso-8859-1", "utf-8").encode("utf-8")
    assert markup(utf8) is utf8
    ascii_page = (
        b'<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        b"<p>plain</p>"
    )
    assert markup(ascii_page) is ascii_page


def test_element_tree_is_the_same_either_way():
    raw = LIE.encode("utf-8")
    a = total_element_count(BeautifulSoup(raw, EL_PARSER_ID))
    b = total_element_count(BeautifulSoup(markup(raw), EL_PARSER_ID))
    assert a == b
