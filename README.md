# Plooum CamPreview

*[Version française](README.fr.md)*

A Home Assistant integration that keeps a **regular, filtered preview picture** of a camera: every few minutes it takes a picture, and keeps it only if it is a good one. A black picture, a uniform "no signal" frame, or a picture of a camera that turned (PTZ, a knock) is ignored: the preview keeps the last good picture.

The preview is an ordinary `image` entity, kept across restarts. Cards can use it where a camera picture must stay meaningful, for example the projection of a camera onto a facade or a room in the [floorplan card](https://github.com/plooum/HA-Plooum-Cards/blob/main/docs/floorplan.md) (`preview_entity`), or as a fallback picture when the camera's stream is unavailable.

## Installation

HACS → Integrations → ⋮ → Custom repositories → `https://github.com/plooum/HA-Plooum-CamPreview` (category *Integration*), install **Plooum CamPreview**, restart Home Assistant. Then **Settings → Devices & services → Add integration → Plooum CamPreview**, and pick the cameras to start with.

## Several cameras

The integration is set up once; each camera is a part of it with its own settings:

- **Add camera** on the integration's page adds one, with its settings;
- the ⚙ of a camera changes its settings;
- ⋮ → **Delete** on a camera removes it, its entities and its kept picture.

Upgrading from 0.1.0 (one integration entry per camera): each entry becomes a Plooum CamPreview entry holding its camera, with the same entities, settings and picture. New cameras can be added to any of them.

## Entities

For a camera `camera.garden`:

| Entity | What |
| :--- | :--- |
| `image.garden_preview` | The preview: the last good picture. Its state is the time of that picture. Attributes: `camera_entity`, `status`, `moved` (true while pictures are ignored because the camera turned), `last_reason`, `score` (similarity with the usual view, 0–1), `mode` (`color` or `ir`), `brightness`, `contrast`, `rejections` (in a row), `last_attempt`, `view_since` (since when the camera shows its current view), `moved_since`, `references`, `error`. |
| `sensor.garden_preview_status` | Result of the last capture: `ok`, `black`, `uniform`, `moved`, `unavailable`, `error`, `waiting`. |
| `button.garden_preview_force_update` | **Force update**: takes the current picture whatever it shows, and makes it the camera's new usual view (after you turned the camera on purpose). |

Action `plooum_campreview.update` (target: any of these entities, a device or an area): captures a picture now; with `force: true`, same as the button.

Event `plooum_campreview_view_changed` (`camera_entity`, `reason`: `rebased`, `stale` or `forced`): the camera's usual view changed. Handy to get a notification that a camera was turned.

## How pictures are filtered

Each picture is reduced to the **edges** of a small gray copy. Edges hardly change with the light of the day or in a gray infrared night view, whereas a turn of a few degrees moves them all. A picture is compared with the camera's **usual view**:

- **black**: its brightest parts are darker than the *black level* → ignored.
- **uniform**: almost no contrast (gray or blue "no signal" screen) → ignored.
- **moved**: its edges no longer look like the usual view (*similarity threshold*, 0.5 by default: a turn of about 3 % of the picture) → ignored.

### Never ignoring everything

A filter that compares with a fixed picture can end up rejecting every picture forever (night, infrared, seasons, a camera turned for good). Safeguards:

1. **One usual view per mode**: color (day) and infrared (night) each have their own reference. The first infrared picture is compared leniently and becomes the night reference.
2. **References follow slow changes**: a picture that matches confidently becomes the new reference of its mode (light, seasons, a parked car).
3. **A new stable view is adopted**: when several ignored pictures in a row (3 by default) look alike over at least 10 minutes, the camera really points somewhere else now: that view becomes the usual one (`plooum_campreview_view_changed`, reason `rebased`). A PTZ camera on patrol, whose pictures keep changing, is not adopted.
4. **Last resort**: after 12 hours without any accepted picture while informative ones keep coming, the latest one is accepted (`stale`).
5. **Force update** (button or action) always takes the picture.

Black and uniform pictures never count towards 3 and 4: a camera without infrared keeps its last daylight picture at night, which is what a preview should show.

## Options

Set when adding a camera, changed later with its ⚙ (**Settings → Devices & services → Plooum CamPreview**). Cameras picked when setting the integration up start with the defaults:

| Option | Default | |
| :--- | :--- | :--- |
| Capture interval | 300 s | Time between two captures (at least 30 s). |
| Black level | 25 | 0–255. A picture whose brightest parts (98th percentile of the luminance) are darker is black. |
| Minimum contrast | 3 | Luminance standard deviation under which a picture is uniform. |
| Similarity threshold | 0.5 | 0–1. Lower tolerates more (a shaky camera), higher catches smaller turns. |
| Pictures alike to adopt a new view | 3 | 0 never adopts a new view by itself. |
| ...over at least | 10 min | |
| Accept anyway after | 12 h | 0: never. |

## Development

The filter (`analysis.py`, `decision.py`) does not depend on Home Assistant; its tests run with Pillow only:

```bash
python -m unittest discover tests
```
