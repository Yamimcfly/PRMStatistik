import requests


class AeroDataBoxAPIAviationandFlightAPIMCPClient:
    def __init__(self, api_key: str):
        self.endpoint = "https://prod.api.market/api/mcp/aedbx/aerodatabox"
        self.headers = {
            "Content-Type": "application/json",
            "x-api-market-key": api_key,
        }
        self.request_id = 0

    def _call(self, method: str, params: dict = None) -> dict:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        response = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=30)
        return response.json()

    def initialize(self) -> dict:
        return self._call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "Python Client", "version": "1.0.0"},
            },
        )

    def list_tools(self) -> dict:
        return self._call("tools/list")


if __name__ == "__main__":
    client = AeroDataBoxAPIAviationandFlightAPIMCPClient("cmlfusabp0001l204tjf7rf03")
    print(client.initialize())
    print(client.list_tools())
