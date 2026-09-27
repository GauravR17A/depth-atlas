# Security

For a suspected vulnerability, contact the website operator at **ranadegaurav30@gmail.com**. Include the affected route, a minimal reproduction and the expected behavior. Do not attach credentials, private uploads or other users' information. Avoid posting an exploitable vulnerability in a public issue before the operator can assess it. No response deadline or bounty programme is promised.

The application enforces request-byte limits before parsing, finite upload time, concurrency limits and process-local rate budgets. It rejects cross-origin browser POST requests and supplies restrictive script and response policies. The app has no client-side provider key and does not accept arbitrary source URLs or uploaded plugin code.

The [implementation review](docs/P17_SECURITY.md) explains verified controls and their boundaries. Independent serverless workers have separate counters. These controls do not establish a global quota, DDoS protection, a native-parser sandbox or complete security. A separate institutional deployment needs its own HTTPS, access policy, trusted-proxy configuration and edge limits.

Dependency lockfiles describe the tested release. Reassess them before upgrading or exposing a separate deployment. Never commit `.env`, hosting state, authentication tokens, private observations or operational logs.
