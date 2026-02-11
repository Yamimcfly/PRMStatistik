import argparse
import json
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

from app.db.session import init_db, SessionLocal
from app.db.models import PrmAnnouncement, ImportFile


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

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._call("tools/call", {"name": name, "arguments": arguments})


def load_api_key() -> Optional[str]:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "config.json"
    if not config_path.exists():
        return None
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("Test Airline", {}).get("API FlightNr")
    except Exception:
        return None


def build_flight_number(airline_code: Optional[str], flight_no: Optional[str]) -> Optional[str]:
    if not flight_no:
        return None
    text = str(flight_no).strip().replace(" ", "")
    if airline_code:
        airline = str(airline_code).strip().replace(" ", "")
        if text.upper().startswith(airline.upper()):
            return text
        return f"{airline}{text}"
    return text


def find_iata_destination(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        # Common AeroDataBox structures
        for key in ("arrival", "destination", "movement"):
            if key in payload and isinstance(payload[key], dict):
                for k in ("airport", "arrivalAirport", "destinationAirport"):
                    if k in payload[key] and isinstance(payload[key][k], dict):
                        for code_key in ("iata", "iataCode", "iataCodeShort"):
                            code = payload[key][k].get(code_key)
                            if code:
                                return str(code).upper()
                for code_key in ("arrivalAirportIata", "destinationAirportIata", "iata"):
                    code = payload[key].get(code_key)
                    if code:
                        return str(code).upper()
        for k in ("arrivalAirportIata", "destinationAirportIata", "iata"):
            code = payload.get(k)
            if code:
                return str(code).upper()
        for value in payload.values():
            found = find_iata_destination(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = find_iata_destination(item)
            if found:
                return found
    return None


def call_flight_api(client: AeroDataBoxAPIAviationandFlightAPIMCPClient, flight_number: str, flight_date) -> dict:
    if flight_date:
        date_local = flight_date.strftime("%Y-%m-%d")
        return client.call_tool(
            "getflight_flightonspecificdate",
            {
                "searchBy": "number",
                "searchParam": flight_number,
                "dateLocal": date_local,
                "query": {"dateLocalRole": "Both"},
            },
        )
    return client.call_tool(
        "getflight_flightnearest",
        {
            "searchBy": "number",
            "searchParam": flight_number,
            "query": {"dateLocalRole": "Both"},
        },
    )


def export_unmapped_flights_with_api(output_path: Path, limit: Optional[int] = None) -> int:
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("API key not found in config.json under 'Test Airline' -> 'API FlightNr'.")

    client = AeroDataBoxAPIAviationandFlightAPIMCPClient(api_key)
    client.initialize()

    init_db()
    session = SessionLocal()
    try:
        query = (
            session.query(
                PrmAnnouncement.airline_code,
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.flight_no,
                PrmAnnouncement.flight_date,
                PrmAnnouncement.in_out,
                PrmAnnouncement.airport,
                ImportFile.month_key,
                ImportFile.source_file,
            )
            .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
            .filter(PrmAnnouncement.flight_no.isnot(None))
            .filter(PrmAnnouncement.flight_no != "")
            .filter(PrmAnnouncement.airport_code.is_(None))
        )

        rows = query.all()
        if limit:
            rows = rows[:limit]

        results = []
        for row in rows:
            flight_number = build_flight_number(row.airline_code, row.flight_no)
            if not flight_number:
                continue

            api_destination = None
            api_status = "ok"
            api_error = None
            try:
                response = call_flight_api(client, flight_number, row.flight_date)
                api_destination = find_iata_destination(response)
            except Exception as exc:
                api_status = "error"
                api_error = str(exc)

            results.append(
                {
                    "flight_number": flight_number,
                    "flight_date": row.flight_date,
                    "airline_code": row.airline_code,
                    "airline_raw": row.airline_raw,
                    "in_out": row.in_out,
                    "airport_raw": row.airport,
                    "month_key": row.month_key,
                    "source_file": row.source_file,
                    "api_destination": api_destination,
                    "api_status": api_status,
                    "api_error": api_error,
                }
            )

            time.sleep(0.2)

        df = pd.DataFrame(results)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="API_Compare", index=False)

        return len(df)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare unmapped flights with AeroDataBox API")
    parser.add_argument("--output", required=True, help="Output Excel path")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit of rows")
    args = parser.parse_args()

    count = export_unmapped_flights_with_api(Path(args.output), args.limit)
    print(f"Exported {count} rows to {args.output}")


if __name__ == "__main__":
    main()
