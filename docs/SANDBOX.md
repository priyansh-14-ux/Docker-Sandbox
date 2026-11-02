# Project MediCode: Secure Code-Execution Sandbox Architecture & Operations Guide

## 1. System Overview & Architecture

Project MediCode provides an educational coding practice and lab assessment platform. Untrusted student Python code is evaluated asynchronously inside a sandboxed environment against predefined visible and hidden test cases, returning granular verdicts and execution telemetry.

### End-to-End Execution Flow (Mermaid Diagram)

```mermaid
flowchart TD
    subgraph Client ["Frontend / Client Layer"]
        User["Student / Browser"]
    end

    subgraph Gateway ["Edge & Ingress (Public Network)"]
        Caddy["Caddy Reverse Proxy (HTTPS / Port 80/443)"]
    end

    subgraph ControlPlane ["FastAPI Control Plane (medicode-api)"]
        API["FastAPI App (uvicorn workers)"]
        AuthGuard["JWT & Role Authorization Guard"]
        RateLimiter["Redis Sliding-Window Rate Limiter"]
        Validator["Pydantic v2 Payload Validator"]
        DBWriter["Durable DB Record: status=QUEUED"]
    end

    subgraph DataStore ["Persistence & Queuing"]
        AppDB[("PostgreSQL 16: App Database")]
        RedisQueue[("Redis 7: ARQ Queue, Rate Limits & Result Cache")]
    end

    subgraph WorkerPlane ["Async Processing (medicode-worker)"]
        Worker["ARQ Background Worker (Same Backend Image)"]
        CacheCheck{"SHA256 Result Cache Hit?"}
        BatchPrep["Batch Request Encoder (Base64)"]
    end

    subgraph SandboxBoundary ["Isolated Sandbox Network (Private Docker Bridge)"]
        JServer["Judge0 Server API (Pinned v1.13.1)"]
        JDB[("Judge0 Internal Postgres")]
        JRedis[("Judge0 Internal Redis")]
        JWorker["Judge0 Worker (Isolate Sandbox / Privileged)"]
    end

    User -->|POST /api/submissions| Caddy
    Caddy -->|Internal HTTP| API
    API --> AuthGuard
    AuthGuard --> RateLimiter
    RateLimiter --> Validator
    Validator --> DBWriter
    DBWriter --> AppDB
    API -->|Enqueue job (submission_id)| RedisQueue
    API -->|HTTP 202 Accepted| User

    RedisQueue -->|Dequeue job| Worker
    Worker --> CacheCheck
    CacheCheck -- Yes --> DBWriter
    CacheCheck -- No --> BatchPrep
    BatchPrep -->|POST /submissions/batch?base64=true| JServer
    JServer --> JDB
    JServer --> JRedis
    JRedis --> JWorker
    JWorker -->|Execute Python inside Isolate| JWorker
    Worker -->|Poll GET /submissions/batch?tokens=...| JServer
    Worker -->|Save results & status=COMPLETED| AppDB
    Worker -->|pg_notify / Redis update| User

    User -->|GET /api/submissions/:id (Polling/SSE)| API
    API -->|Return Verdict (Hidden Test Data Masked)| User
```

---

## 2. Security Model (Treating Student Code as Hostile)

All user-submitted Python code is executed in an untrusted sandbox with multiple defense-in-depth isolation layers:

| Vector | Threat | Mitigation |
| :--- | :--- | :--- |
| **Network Access** | Port scanning, internal service compromise, botnet calling | Sandbox launched with `enable_network: false`. Container network interface blocked via Linux namespace isolation (`isolate`). |
| **Infinite Loops** | CPU starvation, hanging worker threads | Hard CPU time limit (`1.0s`) and wall-clock timeout (`3.0s`). Judge0 automatically issues `SIGKILL` if runtime is exceeded, returning `TLE`. |
| **Memory Bombs** | OOM crashing the host kernel (`x = [0] * 10**9`) | Cgroup v1 memory limit capped at `128 MB` (`128,000 KB`). Exceeding memory raises `MemoryError` or `SIGSEGV`, mapped to `MLE`. |
| **Fork Bombs** | Process table exhaustion (`while True: os.fork()`) | Process and thread count capped at `30` (`max_processes_and_or_threads`). OS raises `BlockingIOError: Resource temporarily unavailable`, cleanly mapped to `RE`. |
| **Disk Exhaustion** | Filling host disk via giant output or temp files | `max_file_size` capped at `1 MB` (`1024 KB`). Output generation triggers `SIGXFSZ` (`OLE`). Filesystem is mounted read-only except an isolated sandbox `/tmp`. |
| **Stdout Memory Explosion** | Crashing API / worker via `print("A"*100_000_000)` | Backend truncates and sanitizes all stdout/stderr captures to a hard ceiling of `2 KB` (`2048 chars`) before saving to PostgreSQL or logging. |
| **Secret Exfiltration** | Inspecting host environment variables (`os.environ`) | Worker and sandbox run in independent Docker containers. Judge0 does not inherit `DATABASE_URL` or `AUTH_SECRET_KEY` from `medicode-api`. |
| **Hidden Test Data Leakage** | Students scraping hidden inputs/outputs to cheat | The API strictly strips `stdout`, `stderr`, and `error_message` from all hidden test cases (`is_hidden: true`) for student roles. |

---

## 3. Host Requirements & Known Judge0 Constraints

Judge0 CE uses [isolate](https://github.com/ioi/isolate) (the international standard for contest sandboxing), which imposes two critical host kernel requirements:

1. **Linux cgroup v1 Hierarchy:**
   - Judge0 CE standard releases require **cgroup v1** for memory and CPU accounting.
   - Modern Linux distributions (Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12) default to cgroup v2.
   - **Remedy for Ubuntu 22.04+ Hosts:**
     Add `systemd.unified_cgroup_hierarchy=0` to `/etc/default/grub`:
     ```bash
     sudo sed -i 's/GRUB_CMDLINE_LINUX="/GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0 /g' /etc/default/grub
     sudo update-grub
     sudo reboot
     ```
2. **Swap Accounting:**
   - Ensure `swapaccount=1` is enabled in GRUB:
     ```bash
     GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0 cgroup_enable=memory swapaccount=1"
     ```
3. **Automated Host Check Script:**
   MediCode includes an automated host verification script:
   ```bash
   ./scripts/check_sandbox_host.sh
   ```
   This script inspects kernel flags, cgroup v1 mount points, and Docker privileged isolate readiness before stack boot.

---

## 4. API Contract & Swagger Integration

The execution pipeline exposes auto-generated OpenAPI documentation accessible at `/docs` or `/redoc`.

### 1. Submit Solution for Judging
- **Method / Path:** `POST /api/submissions`
- **Headers:** `Authorization: Bearer <JWT>`
- **Request Body:**
  ```json
  {
    "problem_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "source_code": "a, b = map(int, input().split())\nprint(a + b)",
    "language": "python"
  }
  ```
- **Response (`202 Accepted`):**
  ```json
  {
    "submission_id": "d3b07384-d113-4ec6-8dd3-e5d7749171b3",
    "status": "queued",
    "message": "Submission queued for isolated sandbox execution."
  }
  ```

### 2. Get Submission Result
- **Method / Path:** `GET /api/submissions/{id}`
- **Headers:** `Authorization: Bearer <JWT>`
- **Response (`200 OK`):**
  ```json
  {
    "id": "d3b07384-d113-4ec6-8dd3-e5d7749171b3",
    "problem_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "status": "COMPLETED",
    "verdict": "AC",
    "language": "python",
    "score": 100.00,
    "time_ms": 25,
    "memory_kb": 12400,
    "passed_test_cases": 5,
    "total_test_cases": 5,
    "error_message": null,
    "results": [
      {
        "test_number": 1,
        "verdict": "AC",
        "time_ms": 15,
        "memory_kb": 12100,
        "is_hidden": false,
        "stdout": "5\n",
        "stderr": "",
        "error_message": null
      },
      {
        "test_number": 2,
        "verdict": "AC",
        "time_ms": 25,
        "memory_kb": 12400,
        "is_hidden": true,
        "stdout": null,
        "stderr": null,
        "error_message": null
      }
    ],
    "created_at": "2026-11-02T16:30:00Z"
  }
  ```
  *(Note: For test 2, `stdout` and `stderr` are strictly `null` because `is_hidden: true`)*

### 3. Quick Run (Unscored / "Run" Button)
- **Method / Path:** `POST /api/run` (or `POST /api/submissions/run`)
- **Headers:** `Authorization: Bearer <JWT>`
- **Request Body:**
  ```json
  {
    "source_code": "print(int(input()) ** 2)",
    "custom_input": "8\n",
    "language": "python"
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "status": "completed",
    "verdict": "AC",
    "stdout": "64\n",
    "stderr": null,
    "error_message": null,
    "time_ms": 14,
    "memory_kb": 10240,
    "results": [...]
  }
  ```

### 4. Live Server-Sent Events (SSE) Stream
- **Method / Path:** `GET /api/submissions/{id}/events?token=<JWT>`
- **Stream Format:**
  ```text
  event: update
  data: {"submission_id": "...", "status": "RUNNING", "verdict": null, "score": null}

  event: update
  data: {"submission_id": "...", "status": "COMPLETED", "verdict": "AC", "score": "100.00", "time_ms": 25, "memory_kb": 12400}

  event: done
  data: {"submission_id": "...", "status": "COMPLETED", "verdict": "AC", "score": "100.00"}
  ```

---

## 5. Sizing Math & Single VPS Capacity Planning

MediCode is architected to run economically on a single low-cost VPS instance (**2 vCPU / 4 GB RAM**).

### Mathematical Sizing Breakdown

1. **Memory Allocation:**
   - Operating System & Docker daemon: **~400 MB**
   - PostgreSQL (Application DB + Judge0 DB): **~350 MB**
   - Redis (MediCode Queue + Judge0 Queue): **~150 MB**
   - `medicode-api` (2 uvicorn workers): **~200 MB**
   - `medicode-worker` (ARQ async worker): **~120 MB**
   - `judge0-server` (Ruby on Rails API): **~350 MB**
   - `judge0-workers` (Active sandboxes): **~128 MB × concurrent sandboxes**
   - Total base footprint without submissions: **~1.57 GB RAM**
   - Remaining headroom for active execution and OS page cache: **~2.43 GB RAM**

2. **Concurrency & Throughput:**
   - Judge0 workers (`COUNT`): set to `2` (matching host vCPUs).
   - ARQ worker `max_jobs`: set to `10`.
   - Average execution runtime per Python test case: **~20 ms – 50 ms**.
   - With 5 test cases per problem submitted via single HTTP batch:
     - Sandbox processing time per submission: `~150 ms`.
     - Single worker throughput: `1000 ms / 150 ms ≈ 6.6 submissions/sec`.
     - 2 workers throughput: `~13 submissions/sec ≈ 780 submissions/minute`.

3. **Burst Absorption via Redis Queue:**
   - If an entire cohort of 100 students clicks **Submit** in the same 5-second window:
     - FastAPI accepts all 100 requests in `< 100 ms`, returns `202 Accepted`, and enqueues 100 IDs.
     - Workers process the queue sequentially at ~13 submissions/sec.
     - Entire burst is graded in **~7.5 seconds** without crashing the VPS or dropping requests.

---

## 6. Cost Comparison Table & Recommendations

| Option | Approximate Monthly Cost | Concurrency & Specs | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **(A) Self-Hosted Judge0 on Low-Cost VPS (Hetzner / DigitalOcean / Linode)** | **~$6 – $12 / mo** | 2 vCPU, 4 GB RAM, 40 GB NVMe | Unlimited submissions; zero per-run fees; private internal network security; data sovereignty. | Requires host configuration (cgroups v1). | **RECOMMENDED FOR CURRENT STAGE.** Lowest TCO for educational workloads with recurring bursts. |
| **(B) Hosted Judge0 on RapidAPI** | **~$20 – $150 / mo** (Starts free for 50/day; ~$10/mo for 10k runs; overages apply) | Hosted infrastructure | Zero server management; no cgroup requirements. | High variable cost during exams (100 students × 10 submissions × 5 tests = 5,000 runs per lab session); latency across public internet. | Recommended only if infrastructure team is unavailable or hosting provider forbids privileged Docker containers. |
| **(C) Dedicated High-Spec Cloud Instance (AWS c6i.2xlarge / GCP c3-standard-8)** | **~$120 – $250 / mo** | 8 vCPU, 16 GB RAM | Massive simultaneous concurrency (50+ sandboxes simultaneously). | Drastically over-provisioned for a small student platform; ~90% idle capacity off-peak. | Upgrade when active concurrent student base exceeds **2,500 active concurrent users**. |

> *Note: Prices above are approximate baseline estimates (Hetzner Cloud CX22 / DigitalOcean Droplet 4GB) as of late 2026 and should be re-verified against provider pricing calculators.*

### When to Upgrade from Option A to Option C:
1. **CPU Saturation:** When average 5-minute CPU load consistently exceeds 80% during normal lab hours.
2. **Queue Lag:** When average submission queue wait time exceeds 10 seconds.
3. **Multi-Host Separation:** Scale out by moving `judge0-workers` to a separate dedicated runner node while keeping the API on the primary node.

---

## 7. Production Deployment & Hardening Guide

### Step 1: Firewall Rules (UFW)
Only expose SSH and web traffic (80/443). Never publish PostgreSQL, Redis, or Judge0:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP (Caddy)'
sudo ufw allow 443/tcp comment 'HTTPS (Caddy)'
sudo ufw enable
```

### Step 2: Cgroup Configuration
Ensure the host uses cgroup v1 as detailed in Section 3:
```bash
sudo sed -i 's/GRUB_CMDLINE_LINUX="/GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0 cgroup_enable=memory swapaccount=1 /g' /etc/default/grub
sudo update-grub
sudo reboot
```

### Step 3: Environment Configuration
Copy and configure production secrets:
```bash
cp .env.example .env
nano .env  # Populate AUTH_SECRET_KEY, POSTGRES_ADMIN_PASSWORD, MEDICODE_DB_PASSWORD
```

### Step 4: Launch Stack
```bash
docker compose up -d --build
```

### Step 5: Run Database Migrations & Seeds
```bash
docker compose exec medicode-api alembic upgrade head
docker compose exec medicode-api python scripts/seed_problems.py
```

### Step 6: Verify Stack Health
```bash
./scripts/smoke.sh http://localhost
```

---

## 8. Troubleshooting & Operational Runbook

| Symptom | Probable Cause | Diagnostic Command | Remediation |
| :--- | :--- | :--- | :--- |
| **Submissions stuck in `QUEUED`** | ARQ worker container is stopped or cannot reach Redis. | `docker compose logs medicode-worker` | Verify Redis health: `docker compose exec medicode-redis redis-cli ping`. Restart worker: `docker compose restart medicode-worker`. |
| **Verdict always returns `IE` (Internal Error)** | Judge0 worker lacks privileged access or cgroup v1 is disabled on host. | `docker compose logs judge0-workers` | Run `./scripts/check_sandbox_host.sh`. Ensure `privileged: true` is set on `judge0-workers` in `docker-compose.yml`. |
| **API returns 429 Too Many Requests** | Student exceeded burst rate limit (1 per 3s) or hourly quota. | Check client response header `Retry-After`. | Wait for `Retry-After` seconds. Adjust `RATE_LIMIT_BURST_WINDOW_SEC` in `.env` if desired. |
| **OOMKilled on Judge0 Container** | Host system ran out of swap/memory. | `docker inspect judge0-workers --format '{{.State.OOMKilled}}'` | Ensure host has swap enabled (`sudo swapon --show`) and verify `default_memory_limit_kb` is not exceeding physical limits. |
