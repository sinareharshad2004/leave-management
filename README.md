# Employee Leave Management API

A Django REST Framework API where employees request leave and managers approve
or reject it. Built for the *Mid-Level Django Coding Practice Task*.

**Stack:** Python 3.12, Django 5.2, Django REST Framework, JWT (SimpleJWT),
django-filter, PostgreSQL (SQLite works for quick local runs), pytest.

---

## 1. Quick start

```bash
# 1) create & activate a virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2) install dependencies
pip install -r requirements-dev.txt

# 3) configure environment
cp .env.example .env               # defaults to SQLite, no DB setup needed

# 4) create tables and an admin user
python manage.py migrate
python manage.py createsuperuser   # asks for email, name, password -> role ADMIN

# 5) run
python manage.py runserver
```

### Using PostgreSQL (recommended stack)

```bash
docker compose up -d               # starts Postgres from docker-compose.yml
# in .env set:  DB_ENGINE=postgres
python manage.py migrate
```

### Run the tests

```bash
pytest
```

---

## 2. Project structure

```
leave_management/
├── config/            # settings, root urls, wsgi/asgi
├── common/            # shared code (pagination)
├── users/             # custom User model, register/login/me, user list
│   ├── models.py      #   User (email login + role)
│   ├── managers.py    #   UserManager (create_user / create_superuser)
│   ├── permissions.py #   IsAdminRole, IsManagerOrAdmin
│   ├── serializers.py
│   ├── views.py
│   └── tests/
├── leaves/            # leave domain
│   ├── models.py      #   Leave (+ DB check constraint + indexes)
│   ├── services.py    #   business rules (overlap, approve, reject, delete)
│   ├── serializers.py #   input validation (dates, overlap)
│   ├── permissions.py #   CannotReviewOwnLeave, IsLeaveOwnerOrAdmin
│   ├── filters.py     #   ?status= &leave_type= &employee=
│   ├── views.py       #   thin LeaveViewSet
│   └── tests/
├── conftest.py        # shared pytest fixtures
└── pytest.ini
```

Layering: **views** handle HTTP -> **serializers** validate input ->
**services** hold business rules and transactions -> **models** hold data.

---

## 3. API reference

| Method | URL | Who | Description |
| --- | --- | --- | --- |
| POST | `/api/auth/register/` | Public | Register (always created as EMPLOYEE) |
| POST | `/api/auth/login/` | Public | Body: `email`, `password` -> `access` + `refresh` JWT |
| POST | `/api/auth/token/refresh/` | Public | Body: `refresh` -> new `access` |
| GET | `/api/auth/me/` | Logged in | Current user |
| POST | `/api/leaves/` | Logged in | Create leave (status starts as PENDING) |
| GET | `/api/leaves/` | Logged in | Employee: own leaves. Manager/Admin: all leaves |
| GET | `/api/leaves/{id}/` | Logged in | Same visibility rule as the list |
| DELETE | `/api/leaves/{id}/` | Owner / Admin | Only while the leave is PENDING |
| GET | `/api/leaves/pending/` | Manager, Admin | Pending leaves of *other* people |
| PATCH | `/api/leaves/{id}/approve/` | Manager, Admin | Approve a PENDING leave |
| PATCH | `/api/leaves/{id}/reject/` | Manager, Admin | Reject a PENDING leave |
| GET | `/api/users/` | Admin | List users (`?role=`, `?search=`) |

Send the token as `Authorization: Bearer <access>`.

**Query parameters on `/api/leaves/`:**
`?status=PENDING` · `?leave_type=SICK` · `?employee=5` · `?search=emma` ·
`?ordering=-created_at` (also `start_date`, `end_date`, `status`) ·
`?page=2&page_size=20`

**Example**

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "emma@example.com", "password": "StrongPass123!"}'

curl -X POST http://localhost:8000/api/leaves/ \
  -H "Authorization: Bearer <access>" -H "Content-Type: application/json" \
  -d '{"leave_type": "SICK", "start_date": "2026-12-10", "end_date": "2026-12-12", "reason": "Fever"}'
```

**Status codes used:** 200/201/204 success · 400 validation error ·
401 not logged in · 403 not allowed · 404 not found / not yours ·
409 the leave is not PENDING any more.

### Creating a manager
Registration always creates an EMPLOYEE so nobody can make themselves admin.
To promote someone, log in to `/admin/` as the superuser and change their
**Role** to MANAGER (or ADMIN).

---

## 4. Business rules and assumptions

* **Overlap:** a new leave conflicts with the same employee's PENDING or
  APPROVED leaves when date ranges share any day (end date is inclusive).
  REJECTED leaves do not block new requests.
* **Start date** cannot be in the past (today is allowed).
* **Who sees what:** employees see only their own leaves. Managers and admins see
  all leaves (the model has no team/department, so there is nothing to narrow it by).
* **`approved_by`** stores the reviewer for both approve *and* reject decisions.
* **Nobody can review their own leave**, including admins.
* **Delete:** owner (or admin) can delete a leave only while it is PENDING.
* Approved/rejected leaves are final: approve, reject and delete return **409**.

---

## 5. Questions you should be able to explain

**1. Why a custom User model?**
The task needs `role` on the user and email-based login. Django's docs
recommend defining a custom user at the *start* of a project because switching
later is painful. `AUTH_USER_MODEL = "users.User"` is used everywhere (FKs use
`settings.AUTH_USER_MODEL`).

**2. Where is business validation?**
Three layers, each with a job:
* *Serializer* (`LeaveSerializer.validate`): date order, past dates, overlap -> clear 400 errors.
* *Service* (`leaves/services.py`): rules that depend on current DB state (status checks, overlap re-check, self-approval).
* *Database* (`CheckConstraint start_date <= end_date`): last line of defence.

Views contain no business rules.

**3. Where is authorization?**
* Role checks: `IsManagerOrAdmin`, `IsAdminRole` (`users/permissions.py`).
* Object checks: `CannotReviewOwnLeave`, `IsLeaveOwnerOrAdmin` (`leaves/permissions.py`).
* Data scope: `LeaveViewSet.get_queryset()`.
* `get_permissions()` maps each action to its permission classes, and the default is `IsAuthenticated`.

**4. Why `select_related()`?**
The list returns employee name/email and the approver's name. Without it,
Django runs extra queries for every row (N+1). `select_related("employee",
"approved_by")` uses SQL JOINs, so it is 1 query for data (+1 for pagination
count) regardless of page size. It fits because both are ForeignKeys (one related row
each). `prefetch_related` would be for reverse/many-to-many relations. A test
(`test_list_has_no_n_plus_one_queries`) enforces it.

**5. How is other employees' data protected?**
At the queryset level: for an employee, `get_queryset()` filters
`employee=request.user`, so every action (list, retrieve, delete, ...) works
only on their rows. Another employee's id gives **404**, not data. The employee
on a new leave comes from the JWT user, never from the request body. Even
`?employee=<other id>` returns nothing because the filter runs on the already
restricted queryset.

**6. How are overlapping leaves prevented?**
`find_overlapping_leaves()` uses `existing.start <= new.end AND existing.end >= new.start`.
The serializer calls it for a friendly error, and `create_leave()` calls it again
inside `transaction.atomic()` after locking the employee row with
`select_for_update()`, so two simultaneous requests can't both slip through.
*Possible improvement:* a PostgreSQL `ExclusionConstraint` on a date range for a
database-enforced guarantee.

**7. Two managers approve the same leave at the same time?**
`_review_leave()` runs in a transaction and loads the row with
`select_for_update()`. The first request locks it, approves and commits. The
second waits for the lock, then re-reads the row, sees it is no longer PENDING
and returns **409 Conflict**. Exactly one approval wins and `approved_by` is
never overwritten.

**8. Why `transaction.atomic()`?**
The check ("is it still PENDING?") and the write (set status + approved_by)
must act as one unit. The transaction keeps the row lock for that whole span
and rolls everything back if any step fails, so we never end up with half-updated data.

**9. How would I add Redis or Celery later?**
* *Celery:* move slow side effects (emailing the employee after a decision) into a
  task, triggered from the service after the transaction commits
  (`transaction.on_commit(lambda: notify.delay(leave_id))`). The service layer already
  isolates this logic.
* *Redis:* use it as the Celery broker, and as a Django cache backend for
  read-heavy endpoints (e.g. cache the pending list briefly, invalidate on
  approve/reject) or for DRF throttling counters.

---

## 6. Test coverage

`pytest` runs tests for: login, unauthorized access (401), employee create,
employee sees only own leaves, employee cannot approve/reject, manager can
approve/reject, manager cannot approve own leave, admin sees all, overlapping
leave rejected (several shapes), invalid dates rejected, approved/rejected leave
cannot be modified again (409), delete rules, filtering/search/ordering/pagination,
and the no-N+1 query check.

## 7. Possible next steps
Swagger docs (drf-spectacular), Docker for the app, PostgreSQL `ExclusionConstraint`,
leave balance per employee, e-mail notifications via Celery.

---

## 8. One-command run on your laptop

A virtual environment cannot be shipped inside a zip (it contains machine- and
OS-specific paths and binaries), so these scripts build it for you:

**Windows**
```bat
setup_and_run.bat
```
**Mac / Linux**
```bash
bash setup_and_run.sh
```
They create `.venv`, install requirements, create `.env`, run migrations and start
the server at http://127.0.0.1:8000/. Create your admin login once (new terminal,
venv active): `python manage.py createsuperuser`.

Next time, just run:
```bash
# Windows
.venv\Scripts\activate && python manage.py runserver
# Mac / Linux
source .venv/bin/activate && python manage.py runserver
```

## 9. Connecting your own database

Database settings live in `.env` (read by `config/settings.py`).

**SQLite (default, no setup):** `DB_ENGINE=sqlite` creates a `db.sqlite3` file.

**PostgreSQL (recommended stack):**
1. Install PostgreSQL and make sure it is running.
2. Create a database and user (in `psql` or pgAdmin):
   ```sql
   CREATE DATABASE leave_db;
   CREATE USER leave_user WITH PASSWORD 'leave_pass';
   GRANT ALL PRIVILEGES ON DATABASE leave_db TO leave_user;
   \c leave_db
   GRANT ALL ON SCHEMA public TO leave_user;
   ```
   (Or skip this and run `docker compose up -d`, which creates exactly these.)
3. Edit `.env`:
   ```
   DB_ENGINE=postgres
   DB_NAME=leave_db
   DB_USER=leave_user
   DB_PASSWORD=leave_pass
   DB_HOST=localhost
   DB_PORT=5432
   ```
4. Create the tables: `python manage.py migrate`, then `python manage.py createsuperuser`.

Common errors: *password authentication failed* -> wrong `DB_USER`/`DB_PASSWORD`;
*connection refused* -> PostgreSQL is not running or `DB_PORT` is wrong;
*permission denied for schema public* -> run the `GRANT ALL ON SCHEMA public` line above.

**MySQL or another database:** change the `DATABASES` block in `config/settings.py`
and install its driver (e.g. `pip install mysqlclient`). Note that row locking
(`select_for_update`) is what protects concurrent approvals, and it is fully
supported on PostgreSQL and MySQL (InnoDB) but ignored by SQLite.
