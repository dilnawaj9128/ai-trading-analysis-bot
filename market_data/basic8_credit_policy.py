"""Conservative Basic 8 provider-credit policy."""

# Require one credit for the request and leave one credit unused.
PROVIDER_RESERVE_CREDITS = 1

# Independent local minute/day limits remain in twelve_data_client.py.
# Unknown or expired provider state must still block requests.
