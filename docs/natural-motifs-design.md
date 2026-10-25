# Natural motifs — visual and motion specification v1.0

Status: approved design, implementation branch `feat/natural-motifs-v1`. Source of truth: the five-round design discussion and the final distant-bird correction.

## Visual vocabulary
- **Distant bluebird:** an original, simple solid silhouette inspired by *Liz and the Blue Bird*. Rounded head and body, smoothly joined broad wing, slender tail; no eyes, cheek, beak, feather texture, or internal markings.
- **Opening flock:** nine distant bluebirds in two depth rows, with four focus targets; preserve entering, tracking, departing, and pixel dispersal.
- **Orbit birds:** same silhouette family; 14 on landscape and 8 on portrait layouts, with varied wing posture. Glide instead of flapping. Orient along their orbit without full rotation that would turn them upside down.
- **Paper butterflies:** two simplified swallowtail-like butterflies, with soft forewings, modest hindwing tail, restrained fine veins, and short wingbeat periods separated by glides.
- **Pinned specimen:** the Lorenz-attractor wing trace, measurement marks, and pin remain mathematical line work, not a filled decorative butterfly.
- **Feathers:** exactly two asymmetric, curved quills with light vanes and sparse down. Their slow oscillating fall is preserved.

## Color and hierarchy
Use the site's existing palette: accent `#1c8ad7`, deeper `#1871c2`, lighter `#59bff7`, and white where masked over dark image regions. Bluebirds are silhouettes, not character portraits. Butterfly/feather line work should be lighter than the main scene; avoid additional decorative colors or intensive gradients.

## Motion and accessibility
Keep the existing timeline, cinematic framing, autofocus, HELLO ring, and camera fall; adjust only the natural motifs. Respect `prefers-reduced-motion` and preserve replay, skip, tab navigation, day/dusk/night, and existing pointer behavior. Do not add new animation dependencies. Keep decorative SVGs noninteractive.

## Implementation hotspots
- `site/main.js`: `bluebirdPath`, `FLOCK`, `poseBird`, `drawFlock`, `MEET.bird`, `drawBirds`, `BUTTERFLY`, `FEATHER`, `layoutMotifs`.
- `site/styles.css`: natural motif fills and fine strokes.

## Visual acceptance
Seek reproducible frames using `?debug&t=600`, `t=1100`, `t=2600`, `t=4300`, and `t=9300`. Check 1440x900, 768x1024, 390x844 in day/dusk/night. Verify bird silhouette and tracking, clean two-pose transitions, no upside-down orbit birds, light butterfly and feather silhouettes, correct count, mathematical specimen, non-obstruction on portrait, replay/skip, reduced motion, and absence of new console errors.

Local preview: `python tools/serve.py 8766` then visit `http://127.0.0.1:8766/?debug&t=4300&size=390x844&time=night`.

**Release discipline:** stage changes on a feature branch and use a PR for review. Do not push to or merge into `main` automatically.
