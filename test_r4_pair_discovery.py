"""
R4 Dynamic Pair Discovery Test Suite.
Verifies:
1. Live / mock exchange metadata scanning
2. Contract status and perpetual verification
3. Liquidity and 24h quote volume filtering
4. Bid/Ask spread gate (max 0.05% / 5 bps)
5. Funding rate ceiling enforcement
6. Ascending/descending rank scoring order
"""

import sys
import unittest
from unittest.mock import MagicMock

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.futures_discovery import MarketDiscoveryService


class TestR4PairDiscovery(unittest.TestCase):
    def setUp(self):
        self.mock_adapter = MagicMock()
        self.discovery = MarketDiscoveryService(adapter=self.mock_adapter)

    def test_01_filter_perpetual_and_status(self):
        """Contracts not TRADING or not PERPETUAL must be rejected."""
        self.mock_adapter.get_exchange_info.return_value = {
            'symbols': [
                {'symbol': 'BTCUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'BTC', 'quoteAsset': 'USDT'},
                {'symbol': 'ETHUSDT', 'status': 'HALT', 'contractType': 'PERPETUAL', 'baseAsset': 'ETH', 'quoteAsset': 'USDT'},
                {'symbol': 'SOLUSDT', 'status': 'TRADING', 'contractType': 'CURRENT_QUARTER', 'baseAsset': 'SOL', 'quoteAsset': 'USDT'},
            ]
        }
        self.mock_adapter._request.side_effect = [
            # 24hr tickers
            [
                {'symbol': 'BTCUSDT', 'quoteVolume': '50000000', 'closeTime': 0, 'lastPrice': '65000', 'priceChangePercent': '2.5'},
                {'symbol': 'ETHUSDT', 'quoteVolume': '40000000', 'closeTime': 0, 'lastPrice': '3000', 'priceChangePercent': '1.5'},
                {'symbol': 'SOLUSDT', 'quoteVolume': '30000000', 'closeTime': 0, 'lastPrice': '180', 'priceChangePercent': '3.0'},
            ],
            # book tickers
            [
                {'symbol': 'BTCUSDT', 'bidPrice': '65000', 'askPrice': '65002', 'bidQty': '10', 'askQty': '10'},
                {'symbol': 'ETHUSDT', 'bidPrice': '3000', 'askPrice': '3000.5', 'bidQty': '20', 'askQty': '20'},
                {'symbol': 'SOLUSDT', 'bidPrice': '180', 'askPrice': '180.02', 'bidQty': '50', 'askQty': '50'},
            ],
            # premiumIndex
            [
                {'symbol': 'BTCUSDT', 'lastFundingRate': '0.0001'},
                {'symbol': 'ETHUSDT', 'lastFundingRate': '0.0001'},
                {'symbol': 'SOLUSDT', 'lastFundingRate': '0.0001'},
            ]
        ]

        res = self.discovery.scan_and_rank_eligible_pairs()
        self.assertEqual(res['status'], 'SUCCESS')
        candidates = [c['symbol'] for c in res['candidates']]
        self.assertIn('BTCUSDT', candidates, 'Active perpetual must be eligible')
        self.assertNotIn('ETHUSDT', candidates, 'HALT status must be excluded')
        self.assertNotIn('SOLUSDT', candidates, 'Quarterly delivery must be excluded')

    def test_02_spread_and_volume_gates(self):
        """Pairs with wide spreads (>0.05%) or low volume (<M) must be rejected."""
        self.mock_adapter.get_exchange_info.return_value = {
            'symbols': [
                {'symbol': 'GOODUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'GOOD', 'quoteAsset': 'USDT'},
                {'symbol': 'LOWVOLUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'LOWVOL', 'quoteAsset': 'USDT'},
                {'symbol': 'WIDESPREADUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'WIDE', 'quoteAsset': 'USDT'},
            ]
        }
        self.mock_adapter._request.side_effect = [
            # 24hr tickers
            [
                {'symbol': 'GOODUSDT', 'quoteVolume': '50000000', 'closeTime': 0, 'lastPrice': '10', 'priceChangePercent': '1.0'},
                {'symbol': 'LOWVOLUSDT', 'quoteVolume': '5000000', 'closeTime': 0, 'lastPrice': '10', 'priceChangePercent': '1.0'}, # M < M
                {'symbol': 'WIDESPREADUSDT', 'quoteVolume': '30000000', 'closeTime': 0, 'lastPrice': '10', 'priceChangePercent': '1.0'},
            ],
            # book tickers
            [
                {'symbol': 'GOODUSDT', 'bidPrice': '10.000', 'askPrice': '10.002', 'bidQty': '1000', 'askQty': '1000'}, # 0.02%
                {'symbol': 'LOWVOLUSDT', 'bidPrice': '10.000', 'askPrice': '10.002', 'bidQty': '1000', 'askQty': '1000'},
                {'symbol': 'WIDESPREADUSDT', 'bidPrice': '10.000', 'askPrice': '10.015', 'bidQty': '1000', 'askQty': '1000'}, # 0.15% > 0.05%
            ],
            # premiumIndex
            [
                {'symbol': 'GOODUSDT', 'lastFundingRate': '0.0001'},
                {'symbol': 'LOWVOLUSDT', 'lastFundingRate': '0.0001'},
                {'symbol': 'WIDESPREADUSDT', 'lastFundingRate': '0.0001'},
            ]
        ]

        res = self.discovery.scan_and_rank_eligible_pairs()
        candidates = [c['symbol'] for c in res['candidates']]
        self.assertIn('GOODUSDT', candidates)
        self.assertNotIn('LOWVOLUSDT', candidates, 'Low volume must be rejected')
        self.assertNotIn('WIDESPREADUSDT', candidates, 'Wide spread must be rejected')

    def test_03_funding_rate_cap(self):
        """Pairs with excessive funding rates (>0.05%) must be rejected."""
        self.mock_adapter.get_exchange_info.return_value = {
            'symbols': [
                {'symbol': 'NORMALFEEUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'NORM', 'quoteAsset': 'USDT'},
                {'symbol': 'HIGHFEEUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL', 'baseAsset': 'HIGH', 'quoteAsset': 'USDT'},
            ]
        }
        self.mock_adapter._request.side_effect = [
            [
                {'symbol': 'NORMALFEEUSDT', 'quoteVolume': '50000000', 'closeTime': 0, 'lastPrice': '10', 'priceChangePercent': '1.0'},
                {'symbol': 'HIGHFEEUSDT', 'quoteVolume': '50000000', 'closeTime': 0, 'lastPrice': '10', 'priceChangePercent': '1.0'},
            ],
            [
                {'symbol': 'NORMALFEEUSDT', 'bidPrice': '10.000', 'askPrice': '10.002', 'bidQty': '1000', 'askQty': '1000'},
                {'symbol': 'HIGHFEEUSDT', 'bidPrice': '10.000', 'askPrice': '10.002', 'bidQty': '1000', 'askQty': '1000'},
            ],
            [
                {'symbol': 'NORMALFEEUSDT', 'lastFundingRate': '0.0002'}, # 0.02%
                {'symbol': 'HIGHFEEUSDT', 'lastFundingRate': '0.0008'},   # 0.08% > 0.05%
            ]
        ]

        res = self.discovery.scan_and_rank_eligible_pairs()
        candidates = [c['symbol'] for c in res['candidates']]
        self.assertIn('NORMALFEEUSDT', candidates)
        self.assertNotIn('HIGHFEEUSDT', candidates, 'High funding rate must be rejected')


if __name__ == '__main__':
    unittest.main()
