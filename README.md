# DRESSED — Clean iPhone PWA

Personal social calendar + outfit planner.

Supports PDF, image, and video invitations with browser-side extraction. No OpenAI API key required.

This clean-start build avoids `localStorage` for core data and does not register a service worker, reducing iPhone/Safari storage and stale-cache issues. App data uses IndexedDB with a safe in-memory fallback when browser storage is unavailable.

## Deploy on Render
- Static Site
- Branch: main
- Build Command: `echo "DRESSED is a static PWA"`
- Publish Directory: `public`
- No environment variables required.
