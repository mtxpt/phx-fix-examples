from typing import Tuple, Set

ExchangeId = str
SymbolId = str

# exchange, symbol pair
Ticker = Tuple[ExchangeId, SymbolId]

SymbolSet = Set[SymbolId]
TickerSet = Set[Ticker]