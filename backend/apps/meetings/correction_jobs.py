"""Short-lived state for optional AI correction suggestions."""

CORRECTION_JOB_TTL = 7200


def active_key(meeting_id, version):
    return f"correction:active:{meeting_id}:{version}"


def result_key(job_id):
    return f"correction:result:{job_id}"
