import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""
Webhook receiver example — FastAPI endpoint with signature verification,
event routing, and delivery-attempt inspection.

Prerequisites:
    pip install interactly fastapi uvicorn[standard]

Run:
    uvicorn webhook_receiver:app --reload --port 8080

Set environment variables:
    export INTERACTLY_API_KEY="your-api-key"
    export INTERACTLY_TEAM_ID="your-team-id"
    export INTERACTLY_USER_ID="your-user-id"
    export INTERACTLY_BASE_URL="https://your-instance.interactly.io"
    export INTERACTLY_WEBHOOK_SECRET="whsec_..."  # from the Interactly dashboard

Then register your endpoint URL (e.g. https://your-server/webhook) in the
Interactly dashboard and subscribe to the desired event types.
"""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from interactly import WorkflowClient
from interactly.webhooks import WebhookVerificationError, verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ["INTERACTLY_WEBHOOK_SECRET"]

client = WorkflowClient(
    api_key=os.environ["INTERACTLY_API_KEY"],
    team_id=os.environ["INTERACTLY_TEAM_ID"],
    user_id=os.environ["INTERACTLY_USER_ID"],
    base_url=os.environ.get("INTERACTLY_BASE_URL", "https://api.interactly.ai"),
)


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Webhook receiver starting up")
    yield
    logger.info("Webhook receiver shutting down")


app = FastAPI(title="Interactly Webhook Receiver", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Main webhook endpoint
# ---------------------------------------------------------------------------

@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive and verify an Interactly webhook delivery.

    Interactly sends:
      - Header: X-Interactly-Signature  (HMAC-SHA256 hex of the raw body)
      - Header: X-Interactly-Timestamp  (Unix timestamp in seconds)
      - Body: JSON payload describing the event
    """
    body = await request.body()

    # --- Step 1: Verify the signature ---
    signature = request.headers.get("X-Interactly-Signature")
    timestamp = request.headers.get("X-Interactly-Timestamp")

    try:
        verify_signature(
            payload=body,
            secret=WEBHOOK_SECRET,
            signature_header=signature,
            timestamp_header=timestamp,
            max_age_seconds=300,  # reject replays older than 5 minutes
        )
    except WebhookVerificationError as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    # --- Step 2: Parse the payload ---
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type", "unknown")
    logger.info("Received webhook event: type=%s", event_type)

    # --- Step 3: Route to a handler ---
    handler = EVENT_HANDLERS.get(event_type, handle_unknown)
    await handler(event)

    # Return 200 quickly — any non-2xx causes a retry
    return {"received": True}


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

async def handle_run_completed(event: dict):
    run_id = event.get("run_id")
    workflow_id = event.get("workflow_id")
    logger.info("Run completed: run_id=%s workflow_id=%s", run_id, workflow_id)

    if run_id:
        # Fetch the full run record for downstream processing
        run = client.runs.get(run_id)
        logger.info("  Status: %s, output keys: %s", run.status, list((run.output or {}).keys()))


async def handle_run_failed(event: dict):
    run_id = event.get("run_id")
    error = event.get("error")
    logger.error("Run failed: run_id=%s error=%s", run_id, error)

    if run_id:
        # Add a comment noting the failure for audit purposes
        client.runs.add_comment(run_id, content=f"Automated alert: run failed — {error}")


async def handle_webhook_event_failed(event: dict):
    """Re-queue a failed delivery attempt."""
    event_id = event.get("event_id")
    if event_id:
        logger.warning("Webhook event %s failed delivery, retrying...", event_id)
        result = client.webhooks.retry_event(event_id)
        logger.info("Retry triggered: %s", result)


async def handle_unknown(event: dict):
    logger.info("Unhandled event type: %s", event.get("type"))


EVENT_HANDLERS = {
    "run.completed": handle_run_completed,
    "run.failed": handle_run_failed,
    "webhook.delivery.failed": handle_webhook_event_failed,
}


# ---------------------------------------------------------------------------
# Management endpoints (optional — for debugging)
# ---------------------------------------------------------------------------

@app.get("/webhooks")
def list_subscriptions():
    """List all webhook subscriptions for the team."""
    page = client.webhooks.list(size=50)
    return {
        "total": page.total,
        "subscriptions": [
            {
                "id": w.id,
                "url": w.url,
                "events": w.events,
                "is_active": w.is_active,
            }
            for w in page
        ],
    }


@app.get("/webhooks/events")
def list_recent_events(page: int = 1, size: int = 20):
    """List recent webhook delivery events."""
    events_page = client.webhooks.list_events(page=page, size=size)
    return {
        "total": events_page.total,
        "events": [
            {
                "id": e.id,
                "type": e.event_type,
                "status": e.status,
                "created_at": str(e.created_at),
            }
            for e in events_page
        ],
    }


@app.get("/webhooks/events/{event_id}/attempts")
def get_delivery_attempts(event_id: str):
    """List all delivery attempts for a specific event."""
    attempts = client.webhooks.list_delivery_attempts(event_id)
    return {
        "event_id": event_id,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "status_code": a.status_code,
                "attempted_at": str(a.attempted_at),
            }
            for a in attempts
        ],
    }
