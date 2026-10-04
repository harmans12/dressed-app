# DRESSED v16

Stable DRESSED personal event + outfit planner.

- Server-side PDF/image/video invitation reader; no OpenAI API key required.
- PDF embedded text first, OCR fallback.
- Image OCR with multiple passes.
- Video frame sampling with FFmpeg + OCR.
- Profiles, events and editable looks are stored locally in IndexedDB.
- Home screen has a static fallback so it is visible even if the browser delays app boot.

## Render
Create a Web Service using Docker. The included `render.yaml` is ready for this.
No environment variables are required.
