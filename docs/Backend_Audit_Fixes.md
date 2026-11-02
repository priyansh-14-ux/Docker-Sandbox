# Backend Architecture Audit & Fixes

## 1. Identified Problems in `Medicode_Backend.md`

1. **Ephemeral WebSocket Gateway Exhaustion**: 
   - Opening a new WebSocket per submission (`/ws/submissions/{id}`) exhausts file descriptors under 500 concurrent students.
2. **Worker Memory Bomb via Stdout**: 
   - Celery worker reading unbounded stdout (`print("A"*50M)`) triggers worker Out-Of-Memory (OOM) host crashes.
3. **Cold Docker Container Startup Lag**: 
   - `docker run` per submission incurs 800ms-1500ms lag. 150 students x 5 test cases = 750 containers in 5 mins, causing Docker daemon socket lockups.
4. **Missing Submission Idempotency Keys**: 
   - Fast double-clicks on submit enqueue duplicate executions, wasting queue compute.
5. **Lack of Submission Rate Limiting**: 
   - Absence of Redis token-bucket middleware on `POST /submissions` allows script/curl loop DOS attacks.
6. **Unauthenticated Gateway-Worker Communication**: 
   - Lacks internal service authentication (mTLS / API secret) between API Gateway and Celery Sandbox Workers.
7. **Missing Essential Endpoints**: 
   - Missing routes for AI BYOK validation, live invigilation telemetry, PDF generation, bulk zip ingestion, and IP locking.

---

## 2. Required Fixes / Action Plan

1. **Persistent Global WebSocket**: 
   - Replace submission-specific WS with a single connection per session (`/ws/session?token=...`) and multiplex events over it.
2. **Cap Worker Stdout Output**: 
   - Apply strict 512KB hard-caps (`head -c 524288`) on all worker stdout buffer captures.
3. **Pre-Warmed Sandbox Environment**: 
   - Abandon cold `docker run` per execution. Implement a **pre-warmed worker pool** or switch the runner to **nsjail / gVisor** (15ms execution).
4. **Add Idempotency Locks**: 
   - Frontend must send a UUID idempotency key; Backend must set a 5-second Redis lock (`SET lock:submit:{student_id} NX EX 5`).
5. **Implement Rate Limiting**: 
   - Add Redis-backed API rate limiting for submissions and heavy operations (e.g., max 10 submissions per minute per user).
6. **Internal Service Secrets**: 
   - Implement inter-service API keys or mTLS to secure communication between the API Gateway and Celery workers.
7. **Create Missing Endpoints**: 
   - Build REST endpoints for `ai/socratic-hint`, `labs/{id}/telemetry`, `test-cases/bulk-zip`, and `reports/practical-record`.


## 3. Complete List of 25 Backend Architecture Flaws (from Master Report)

1. **Ephemeral WebSocket Gateway Exhaustion**: Opening a new WebSocket per submission (`/ws/submissions/{id}`) exhausts file descriptors under 500 concurrent students.
2. **Worker Memory Bomb via Stdout**: Celery worker reading unbounded stdout (`print("A"*50M)`) triggers worker OOM host crashes.
3. **Missing Submission Idempotency Keys**: Fast double-clicks on submit enqueue duplicate executions, wasting queue compute.
4. **Cold Docker Container Startup Lag**: `docker run` per submission incurs 800ms-1500ms lag, causing queue starvation under 150-student exam load.
5. **Lack of Submission Rate Limiting**: Absence of Redis token-bucket middleware on `POST /submissions` allows script/curl loop DOS attacks.
6. **No Automated Runner Workspace Cleanup**: Missing background worker cleanup for `/tmp` or `/dev/shm` sandbox files leads to host disk exhaustion.
7. **Missing CORS Origin Restrictions**: Initial FastAPI boilerplate lacks strict CORS origin whitelisting for Next.js frontend production domains.
8. **Unauthenticated Gateway-Worker Communication**: Lacks internal service authentication (mTLS / API secret) between API Gateway and Celery Sandbox Workers.
9. **Absence of Liveness/Readiness Probes**: No `/healthz` or `/readyz` endpoints for container orchestrator health monitoring.
10. **Database Connection Pool Multiplier Oversight**: Asyncpg pool size (50) multiplied by Uvicorn workers (4) exceeds PostgreSQL `max_connections` (200 > 100 limit).
11. **Absence of Database Transaction Rollbacks**: Pipeline lacks transactional rollback hooks if multi-step submission fails midway.
12. **Raw String Query Injection Risk**: Potential SQL injection vulnerabilities if ORM bypass is used for high-frequency analytics queries.
13. **Missing Request Payload Size Constraints**: FastAPI routes lack maximum body byte limits, allowing mega-payload memory consumption attacks.
14. **No Redis Queue Fallback or Dead-Letter Queue (DLQ)**: Queue crashes result in permanently lost submission jobs with zero retry mechanism.
15. **Infinite Worker Retry Loops**: Celery tasks lack `max_retries=3` limits, causing endless execution cycles on unhandled compiler crashes.
16. **Inability to Terminate Detached Worker Sub-processes**: Detached background daemons spawned inside containers cannot be killed via standard container timeouts.
17. **Abrupt WebSocket Disconnections**: Unhandled exceptions in WebSocket stream handlers disconnect clients without sending JSON error frames.
18. **Missing Security Audit Telemetry Logs**: Failed authentication and 403 authorization rejections are not written to security audit logs.
19. **Hardcoded Configuration Defaults**: `JWT_SECRET` and `POSTGRES_PASSWORD` fall back to insecure static defaults instead of enforcing env variables.
20. **Absence of DB Read-Replica Routing**: High-traffic GET queries (Leaderboards, Course lists) hit the primary write database instance.
21. **Synchronous Password Hashing Event-Loop Blocking**: Running `bcrypt` or `argon2` synchronously inside async routes blocks the asyncio event loop.
22. **Lack of Dynamic Worker Auto-Scaling**: Worker pools cannot automatically scale out during peak morning exam hours (9 AM - 12 PM).
23. **Missing Custom Checker Execution Environment**: Sandbox lacks support for custom output checker binaries (e.g. floating-point tolerance, regex).
24. **Unblocked DNS Resolution in Worker Network Space**: Containers can perform DNS lookups, leaking internal domain naming structures.
25. **Absence of CPU Time vs Wall-Clock Metric Distinction**: Telemetry fails to separate thread CPU execution time from wall-clock wait time.
