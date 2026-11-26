"""Offline read-only readiness inspection: no HTTP, no keys, no broker orders."""
import json
from dashboard.twelve_data_readiness import readiness


def main():
    print(json.dumps(readiness(), indent=2, sort_keys=True))
    print('NO HTTP / NO ACCOUNTING CHANGES / NO BROKER ORDERS')


if __name__ == '__main__':
    main()
