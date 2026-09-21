# frontend

The citizen-facing app. Owned by **Dias (C4)**. Talks to the gateway only.

The current screen is a placeholder that exercises the full request path so the team
can see the system working end to end. The real interface is C4's to design.

**Open decision:** C4 uses haptics and voice for elderly and low-literacy users. A
browser build (this scaffold: React + Vite + TypeScript) cannot do real haptics. If
the team needs them, this becomes React Native or Flutter.

```bash
npm install
npm run dev          # http://localhost:5173
```

Set `VITE_GATEWAY_URL` in `.env` if the gateway is not on `http://localhost:8000`.
