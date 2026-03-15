GAMMA_API  = "https://gamma-api.polymarket.com"
CLOB_API   = "https://clob.polymarket.com"
PAGE_LIMIT = 100

PROB_MIN = 0.05  # 5%
PROB_MAX = 0.10  # 10%

import os
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

VIRTUAL_BUDGET = 10000.0  # starting virtual dollars
BET_SIZE_MIN   = 5.0      # min bet per pick
BET_SIZE_MAX   = 15.0     # max bet per pick
