"""Constants of Plooum CamPreview."""

from __future__ import annotations

DOMAIN = "plooum_campreview"
ENTRY_TITLE = "Plooum CamPreview"
SUBENTRY_CAMERA = "camera"  # one subentry per camera

CONF_CAMERA = "camera_entity"
CONF_CAMERAS = "cameras"  # first step: the cameras to start with
CONF_INTERVAL = "interval"  # s between two captures
CONF_BLACK_LEVEL = "black_level"
CONF_MIN_CONTRAST = "min_contrast"
CONF_MATCH_THRESHOLD = "match_threshold"
CONF_REBASE_COUNT = "rebase_count"
CONF_REBASE_MINUTES = "rebase_minutes"
CONF_MAX_AGE_HOURS = "max_age_hours"

DEFAULT_INTERVAL = 300
MIN_INTERVAL = 30
CAPTURE_TIMEOUT = 15  # s

SERVICE_UPDATE = "update"
ATTR_FORCE = "force"

EVENT_VIEW_CHANGED = f"{DOMAIN}_view_changed"

# Status (sensor state), see PreviewManager.status
STATUS_WAITING = "waiting"
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"
# ... plus the rejection reasons of decision.py: black, uniform, moved
STATUSES = [STATUS_WAITING, STATUS_OK, "black", "uniform", "moved", STATUS_UNAVAILABLE, STATUS_ERROR]

STORAGE_VERSION = 1
