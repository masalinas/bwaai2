#!/usr/bin/env python3
"""Asynchronous load testing utility for the Bwaai PDF Processing API.

Fires N concurrent uploads, tracks upload latency percentiles, polls jobs
to terminal state, tracks end-to-end completion latency, peak in-flight
concurrency, and outputs summary statistics.
"""

import argparse
import asyncio
import statistics
import time
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("httpx is required. Run via 'uv run python scripts/load_test.py' or install httpx.")
    raise


def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * (p / 100.0))
    return sorted_data[min(idx, len(sorted_data) - 1)]


class LoadTester:
    def __init__(
        self,
        base_url: str,
        total_requests: int,
        concurrency: int,
        sample_path: Path,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.total_requests = total_requests
        self.concurrency = concurrency
        self.sample_path = sample_path
        self.pdf_bytes = sample_path.read_bytes()

        self.upload_latencies_ms: list[float] = []
        self.e2e_latencies_s: list[float] = []
        self.errors = 0
        self.successes = 0

        self.current_in_flight = 0
        self.max_in_flight = 0
        self.lock = asyncio.Lock()

    async def _track_in_flight(self, delta: int) -> None:
        async with self.lock:
            self.current_in_flight += delta
            if self.current_in_flight > self.max_in_flight:
                self.max_in_flight = self.current_in_flight

    async def _process_single_document(
        self, client: httpx.AsyncClient, doc_index: int, sem: asyncio.Semaphore
    ) -> None:
        async with sem:
            await self._track_in_flight(1)
            t0 = time.perf_counter()

            # 1. Upload request
            try:
                files = {"files": (self.sample_path.name, self.pdf_bytes, "application/pdf")}
                data = {"parser": "pypdf"}
                up_start = time.perf_counter()
                resp = await client.post(f"{self.base_url}/documents", files=files, data=data)
                up_elapsed_ms = (time.perf_counter() - up_start) * 1000.0
                self.upload_latencies_ms.append(up_elapsed_ms)

                if resp.status_code != 202:
                    self.errors += 1
                    await self._track_in_flight(-1)
                    return

                doc_id = resp.json()[0]["document_id"]
            except Exception as ex:
                self.errors += 1
                await self._track_in_flight(-1)
                return

            # 2. Polling loop
            terminal_status = None
            while True:
                await asyncio.sleep(1.0)
                try:
                    s_resp = await client.get(f"{self.base_url}/documents/{doc_id}/status")
                    if s_resp.status_code == 200:
                        status_val = s_resp.json().get("status")
                        if status_val in ("done", "failed"):
                            terminal_status = status_val
                            break
                except Exception:
                    pass

            total_elapsed_s = time.perf_counter() - t0
            self.e2e_latencies_s.append(total_elapsed_s)
            self.successes += 1
            await self._track_in_flight(-1)

    async def run(self) -> dict[str, Any]:
        print(f"Starting load test against: {self.base_url}")
        print(f"Total Requests: {self.total_requests} | Concurrency: {self.concurrency}")
        print(f"Sample PDF:     {self.sample_path} ({len(self.pdf_bytes)} bytes)")
        print("-" * 75)

        start_time = time.perf_counter()
        sem = asyncio.Semaphore(self.concurrency)
        limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)

        async with httpx.AsyncClient(limits=limits, timeout=60.0) as client:
            tasks = [
                asyncio.create_task(self._process_single_document(client, i, sem))
                for i in range(self.total_requests)
            ]
            await asyncio.gather(*tasks)

        total_wall_time = time.perf_counter() - start_time
        throughput = self.successes / total_wall_time if total_wall_time > 0 else 0

        results = {
            "total_requests": self.total_requests,
            "concurrency": self.concurrency,
            "successes": self.successes,
            "errors": self.errors,
            "error_rate_pct": (self.errors / self.total_requests * 100) if self.total_requests else 0,
            "total_wall_time_s": total_wall_time,
            "throughput_docs_sec": throughput,
            "max_in_flight": self.max_in_flight,
            "upload_p50_ms": percentile(self.upload_latencies_ms, 50),
            "upload_p90_ms": percentile(self.upload_latencies_ms, 90),
            "upload_p95_ms": percentile(self.upload_latencies_ms, 95),
            "upload_p99_ms": percentile(self.upload_latencies_ms, 99),
            "e2e_p50_s": percentile(self.e2e_latencies_s, 50),
            "e2e_p90_s": percentile(self.e2e_latencies_s, 90),
            "e2e_p95_s": percentile(self.e2e_latencies_s, 95),
            "e2e_p99_s": percentile(self.e2e_latencies_s, 99),
        }

        self.print_results(results)
        return results

    def print_results(self, r: dict[str, Any]) -> None:
        print("=" * 75)
        print(" LOAD TEST EXECUTION RESULTS")
        print("=" * 75)
        print(f"Total Completed:      {r['successes']}/{r['total_requests']} (Errors: {r['errors']}, Error Rate: {r['error_rate_pct']:.1f}%)")
        print(f"Total Elapsed Time:   {r['total_wall_time_s']:.2f} seconds")
        print(f"Throughput:           {r['throughput_docs_sec']:.2f} docs/second")
        print(f"Peak Concurrent Jobs: {r['max_in_flight']}")
        print("-" * 75)
        print("Upload Latency (HTTP 202 Ingestion):")
        print(f"  p50: {r['upload_p50_ms']:.1f} ms | p90: {r['upload_p90_ms']:.1f} ms | p95: {r['upload_p95_ms']:.1f} ms | p99: {r['upload_p99_ms']:.1f} ms")
        print("End-to-End Latency (Upload + Parsing to Terminal State):")
        print(f"  p50: {r['e2e_p50_s']:.2f} s  | p90: {r['e2e_p90_s']:.2f} s  | p95: {r['e2e_p95_s']:.2f} s  | p99: {r['e2e_p99_s']:.2f} s")
        print("=" * 75)


def main() -> None:
    parser = argparse.ArgumentParser(description="Async PDF Processor Load Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base API URL")
    parser.add_argument("--total", type=int, default=30, help="Total documents to upload")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent uploads")
    parser.add_argument(
        "--sample",
        default=str(Path(__file__).resolve().parent.parent / "samples" / "normal.pdf"),
        help="Sample PDF path",
    )
    args = parser.parse_args()

    sample_path = Path(args.sample)
    if not sample_path.exists():
        print(f"Sample file not found at {sample_path}", file=sys.stderr)
        sys.exit(1)

    tester = LoadTester(
        base_url=args.base_url,
        total_requests=args.total,
        concurrency=args.concurrency,
        sample_path=sample_path,
    )
    asyncio.run(tester.run())


if __name__ == "__main__":
    main()
