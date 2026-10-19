# Deployment and Live Validation Status

Audit date: 2026-10-19

## Results completed in the audit environment

- Automated API suite includes explicit checks that live Lambda execution is locked without a server token, rejects an incorrect token, and remains disabled unless `ALLOW_LAMBDA_REMEDIATION=true`.
- Local synthetic mode is the default; the Render blueprint explicitly sets `CLOUD_MODE=local`.
- Python unit/API tests can run without AWS credentials or AWS resource creation.
- `render.yaml` is present for a repeatable Render deployment.

## What could not be verified from this environment

- Browser navigation to the local server is blocked by the managed browser environment (`ERR_BLOCKED_BY_ADMINISTRATOR`).
- The headless Chromium environment reports WebGL/WebGL2 unavailable, and outbound DNS/network access is unavailable; therefore it cannot fetch the Three.js CDN or verify the genuine WebGL scene. The dashboard's non-WebGL fallback is available, but this is not a substitute for verifying the real 3D renderer.
- A public URL cannot be created without an authenticated deployment account/repository connection. No URL should be treated as live until deployed and its `/api/health` endpoint is checked.
- No live AWS remediation was invoked. It requires a user-owned demo Lambda target, region, credentials available to the deployment/runtime, an allowlisted reversible action, a least-privilege execution role, CloudTrail, and a strong server-side approval token. Do not share AWS access keys in chat or commit them.

## Safe next steps

1. Connect the GitHub and Render accounts in ChatGPT, then create/publish a repository or select the existing repository.
2. Deploy with the included `render.yaml`; leave `CLOUD_MODE=local` and `ALLOW_LAMBDA_REMEDIATION=false` for the first public demo.
3. Open the deployed URL in a normal browser with internet access. Confirm `/api/health` returns HTTP 200, check browser console/network errors, and confirm the Three.js CDN import succeeds and `#topology` receives the `webgl-ready` class.
4. Validate AWS CloudWatch read-only sync against an existing instance first. Confirm account billing alerts and permissions before enabling any write action.
5. Only after read-only validation, configure a dedicated demo Lambda with one reversible, allowlisted action and explicitly approve a live test. Never use production resources for the test.
