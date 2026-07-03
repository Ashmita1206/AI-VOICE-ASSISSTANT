import time
import requests
import logging

import config

logger = logging.getLogger(__name__)

def plan_remote(text: str, context: dict | None = None) -> str:
    """Send transcription to the Colab endpoint and return the JSON string response."""
    print(f"[REMOTE LLM] Planning...")
    print(f"[REMOTE LLM] Request sent → {config.COLAB_API_URL}")
    logger.info(f"Remote Planner request sent: URL={config.COLAB_API_URL}")

    t_start = time.perf_counter()

    try:
        payload = {"text": text}
        if context:
            payload["context"] = context
        r = requests.post(
            config.COLAB_API_URL,
            json=payload,
            timeout=config.COLAB_TIMEOUT
        )

        latency = time.perf_counter() - t_start
        print(f"[REMOTE LLM] HTTP Status: {r.status_code}")
        print(f"[REMOTE LLM] Latency: {latency:.2f} sec")
        logger.info(f"Remote Planner response received: Status={r.status_code}  Latency={latency:.2f}s")

        r.raise_for_status()

        response_json = r.json()
        plan_text = response_json.get("response", "")
        print(f"[REMOTE LLM] Plan received ({len(plan_text)} chars)")
        return plan_text

    except requests.exceptions.Timeout:
        latency = time.perf_counter() - t_start
        print(f"[REMOTE LLM] TIMEOUT after {latency:.1f} sec → URL={config.COLAB_API_URL}")
        logger.error(f"Remote Planner Timeout: URL={config.COLAB_API_URL}")
        raise
    except requests.exceptions.RequestException as e:
        latency = time.perf_counter() - t_start
        print(f"[REMOTE LLM] ERROR after {latency:.1f} sec: {e}")
        logger.error(f"Remote Planner Error: {e}")
        raise

