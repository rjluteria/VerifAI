"""Content-free authoritative job progress; stages never imply a verdict."""

import time

STAGES = ("claims", "citations", "independent", "evaluation")
EVENTS = {
    "Analyzing claims": "claims",
    "Checking citations": "citations",
    "Searching independent sources": "independent",
    "Verifying evidence": "evaluation",
    "Finalizing results": "evaluation",
}


class JobProgress:
    def __init__(self, job_id, response_id=None):
        self.started = time.monotonic()
        self.value = {
            "version": 1,
            "job_id": job_id,
            "response_id": response_id,
            "sequence": 0,
            "stages": dict.fromkeys(STAGES, "pending"),
            "outcome": "pending",
            "server_elapsed_ms": 0,
            "events": [],
            "tracks": {},
        }
        self.update("Analyzing claims")

    def update(self, event):
        if self.value["outcome"] != "pending":
            return
        before = (
            dict(self.value["stages"]),
            dict(self.value["tracks"]),
            self.value.get("claim_count"),
            self.value["outcome"],
        )
        if isinstance(event, dict):
            count = event.get("claim_count")
            if type(count) is int and 0 <= count <= 60:
                self.value["claim_count"] = count
                self.value["stages"]["claims"] = "complete"
            for stage, state in event.get("stages", {}).items():
                if stage in STAGES and state in ("active", "complete", "unavailable"):
                    current = self.value["stages"][stage]
                    if current not in ("complete", "unavailable"):
                        self.value["stages"][stage] = state
            for track, counts in event.get("tracks", {}).items():
                if track in ("citation", "independent") and isinstance(counts, dict):
                    values = [
                        counts.get(k) for k in ("completed", "total", "accessible")
                    ]
                    if (
                        all(type(v) is int for v in values)
                        and 0 <= values[2] <= values[0] <= values[1] <= 1000
                    ):
                        self.value["tracks"][track] = dict(
                            zip(("completed", "total", "accessible"), values)
                        )
        elif event in EVENTS:
            stage = EVENTS[event]
            if self.value["stages"][stage] == "pending":
                self.value["stages"][stage] = "active"
        elif event in ("Complete", "Failed"):
            self.value["outcome"] = event.lower()
            for stage, state in self.value["stages"].items():
                if state != "complete":
                    self.value["stages"][stage] = (
                        "complete" if event == "Complete" else "unavailable"
                    )
        after = (
            self.value["stages"],
            self.value["tracks"],
            self.value.get("claim_count"),
            self.value["outcome"],
        )
        if before == after:
            return
        self.value["sequence"] += 1
        self.value["events"].append(
            {
                "sequence": self.value["sequence"],
                "server_elapsed_ms": round((time.monotonic() - self.started) * 1000),
                "stages": dict(self.value["stages"]),
            }
        )
        self.value["events"] = self.value["events"][-256:]

    def snapshot(self):
        return {
            **self.value,
            "stages": dict(self.value["stages"]),
            "events": list(self.value["events"]),
            "tracks": {key: dict(value) for key, value in self.value["tracks"].items()},
            "server_elapsed_ms": round((time.monotonic() - self.started) * 1000),
        }
