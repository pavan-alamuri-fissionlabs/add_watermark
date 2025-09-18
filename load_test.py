import aiohttp
import asyncio
import time
import openpyxl

# API endpoints
WATERMARK_API = "http://localhost:8000/watermark/batch/"
STATUS_API = "http://localhost:8000/status/"
DOWNLOAD_API = "http://localhost:8000/download/"

# Payload for upload API
UPLOAD_PAYLOAD = {
    "file_paths": [
        "/home/fl-lpt-690/Downloads/add_watermark/input/100_mb.pdf"
    ],
    "source": "PREPROD"
}


async def run_task(session, request_id):
    """Async task: call upload API, poll status, download file, log timings."""
    try:
        # --- Step 1: Upload (measure API latency) ---
        api_start = time.time()
        async with session.post(WATERMARK_API, json=UPLOAD_PAYLOAD) as resp:
            api_time = time.time() - api_start
            if resp.status != 200:
                return request_id, resp.status, api_time, None, "Watermark API Failed"
            data = await resp.json()
            task_id = data.get("task_id")

        if not task_id:
            return request_id, resp.status, api_time, None, "No task_id"

        # --- Step 2: Poll status until task complete ---
        task_start = time.time()
        status = "PENDING"
        while status not in ("SUCCESS", "FAILURE"):
            await asyncio.sleep(1)
            STATUS_API_URL = f"{STATUS_API}?task_id={task_id}"
            async with session.get(STATUS_API_URL) as status_resp:
                if status_resp.status != 200:
                    return request_id, status_resp.status, api_time, None, "Status check failed"
                status_data = await status_resp.json()
                status = status_data.get("status")

        total_time = time.time() - task_start

        if status == "FAILURE":
            return request_id, resp.status, api_time, total_time, "Task failed"

        # --- Step 3: Download file ---
        DOWNLOAD_API_URL = f"{DOWNLOAD_API}?task_id={task_id}"
        download_start = time.time()
        async with session.get(DOWNLOAD_API_URL) as download_resp:
            if download_resp.status != 200:
                return request_id, download_resp.status, api_time, total_time, None, "Download Failed"
            
            # Read the file content (zipped folder in bytes)
            content = await download_resp.read()

            # Save as zip file
            output_file = f"../../Downloads/{task_id}.zip"
            with asyncio.to_thread(open, output_file, "wb") as f:
                await asyncio.to_thread(f.write, content)

        download_time = time.time() - download_start

        return request_id, resp.status, api_time, total_time, download_time, "SUCCESS"



    except Exception as e:
        return request_id, None, None, None, str(e)


async def main():
    num_requests = 1
    max_workers = 1

    connector = aiohttp.TCPConnector(limit=max_workers)  # concurrency limit
    results = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [run_task(session, i) for i in range(num_requests)]
        for future in asyncio.as_completed(tasks):
            results.append(await future)

    # Print results
    print("\n--- Load Test Results ---")
    for row in results:
        print(row)

    # Save to Excel
    save_to_excel(results)


def save_to_excel(results, filename="output/load_test_results.xlsx"):
    """Save results to Excel file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"

    ws.append([
        "Request ID",
        "Status Code",
        "API Response Time (s)",
        "Task Completion Time (s)",
        "Download Time (s)",
        "Final Status"
    ])

    for row in results:
        ws.append(row)

    wb.save(filename)
    print(f"\nResults saved to {filename}")


if __name__ == "__main__":
    asyncio.run(main())
