"""Peer lookup."""

from stock_rhetoric import peers


def test_peer_tickers_for_known_industry():
    tickers = peers.peer_tickers_for("Semiconductors")
    assert "NVDA" in tickers
    assert "AMD" in tickers
    assert len(tickers) >= 5


def test_peer_tickers_case_insensitive():
    a = peers.peer_tickers_for("semiconductors")
    b = peers.peer_tickers_for("Semiconductors")
    assert a == b


def test_peer_tickers_unknown_industry():
    assert peers.peer_tickers_for("Unobtainium Mining") == []
    assert peers.peer_tickers_for(None) == []
