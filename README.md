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
│   ├── selectors.py   #   WHO can see WHICH leaves (queryset-level authorization)
│   ├── services.py    #   business rules (create, edit, delete, approve, reject, overlap)
│   ├── serializers.py #   input validation (dates, overlap)
│   ├── permissions.py #   CannotReviewOwnLeave, IsLeaveOwner
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
| POST | `/api/auth/login/` | Public | Body: `email`, `password` -> `access` + `refresh` JWT (any role) |
| POST | `/api/auth/employee/login/` | Public | Employee-only login. Managers/admins get 403 |
| POST | `/api/auth/manager/login/` | Public | Manager/admin-only login. Employees get 403 |
| POST | `/api/auth/token/refresh/` | Public | Body: `refresh` -> new `access` |
| GET | `/api/auth/me/` | Logged in | Current user |
| POST | `/api/leaves/` | Employee, Manager | Create your own leave (status starts as PENDING). Admins get 403 |
| GET | `/api/leaves/` | Logged in | Employee: own. Manager: employees' + own. Admin: all (managers' too) |
| GET | `/api/leaves/{id}/` | Logged in | Same visibility rule as the list |
| PATCH | `/api/leaves/{id}/` | Owner only | Edit your leave, only while PENDING (else **409**) |
| DELETE | `/api/leaves/{id}/` | Owner only | Only while PENDING (else **409**). **Soft delete:** the row stays, status becomes `DELETED`, and `deleted_by` / `deleted_at` are recorded |
| GET | `/api/leaves/pending/` | Manager, Admin | Pending leaves *you* can review (not your own) |
| PATCH | `/api/leaves/{id}/approve/` | Manager, Admin | Approve a PENDING leave. Managers: employee leaves only. Admin: any |
| PATCH | `/api/leaves/{id}/reject/` | Manager, Admin | Reject a PENDING leave (same rule as approve) |
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

### Web pages (open in the browser)
| URL | Who |
| --- | --- |
| `http://127.0.0.1:8000/` | Redirects to the login page |
| `/login/` | ONE login page for everyone. Employees land on `/employee/`, managers on `/manager/` |
| `/employee/` | Employee: request leave, see own leaves, **Delete** button (enabled only while PENDING) |
| `/manager/` | Manager: request own leave, then **two tables**: **Own leave** (with Delete) and **Employee leave** (with Approve/Reject). Each table has its own filters and paging. Admin: one table with everything, including managers' leaves |
| `/employee/register/` | Any number of employees can register |
| `/manager/register/` | Any number of managers can register |
| `/admin/` | Admin: create users and set their Role |

### Two separate logins (API)
* **Employee login:** `POST /api/auth/employee/login/` - use it to create leaves
  (`POST /api/leaves/`) and view your own. Employees can never approve or reject (403).
* **Manager login:** `POST /api/auth/manager/login/` - use it to see pending leaves
  (`GET /api/leaves/pending/`) and approve/reject
  (`PATCH /api/leaves/{id}/approve/` or `/reject/`).
* Logging in on the wrong portal returns **403**; a wrong password returns **401**.
* Both return `access`, `refresh` and a `user` object. Send `Authorization: Bearer <access>`.
* Security does not depend on which portal was used: every approve/reject
  endpoint also checks the role in the token.

### Leave rejection notifications
When a leave is approved or rejected, the reviewer sees a confirmation pop-up
and the employee receives an in-app pop-up the next time they visit. An email
is sent to the employee's registered address. Set the
`EMAIL_*` values in `.env` to your SMTP provider's settings to deliver emails;
with `DEBUG=True` and no SMTP backend configured, Django prints emails in the
server terminal instead.

### Creating managers and admins
Employees register at `/employee/register/`; managers can register at
`/manager/register/`, and multiple manager accounts are allowed. Admin
accounts cannot be created through public registration. Create the first admin
with `python manage.py createsuperuser`; an existing admin can create or promote
users through `/admin/` and set their **Role**.

---

## 4. Business rules and assumptions

* **Overlap:** a new leave conflicts with the same employee's PENDING or
  APPROVED leaves when date ranges share any day (end date is inclusive).
  REJECTED leaves do not block new requests.
* **Start date** cannot be in the past (today is allowed).
* **Who sees what** (`leaves/selectors.py`, applied in the database query):
  employees see only their own leaves; managers see employees' leaves + their own
  (not other managers'); admins see every leave, including managers' leaves.
* **`approved_by`** stores the reviewer for both approve *and* reject decisions.
* **Employees and managers create their own leave.** Admins cannot create leave.
* **Who approves what:** an employee's leave is approved/rejected by a manager or an
  admin. A **manager's leave is approved/rejected by an admin only.**
* **Nobody can review their own leave.**
* **Edit and delete:** only the owner, and only while the leave is PENDING. Admins
  and managers can view other people's leaves but cannot change or delete them.
* **Delete is a soft delete.** When an employee or manager deletes their own pending leave,
  nothing is removed from the database. The leave gets status `DELETED` and stores who
  deleted it (`deleted_by`) and when (`deleted_at`). It stays visible in the lists (tagged
  "Deleted", with the name of who deleted it), no longer blocks the calendar, and disappears
  from the pending inbox. It can be filtered with `?status=DELETED`.
* **Approved/rejected/deleted leaves are final:** edit, delete, approve and reject all return **409**.
* **Button state:** every leave in the API carries `can_modify` (owner may still edit or
  delete it) and `can_review` (the current user may still approve or reject it). Both
  become `false` once a decision is made. The web pages use the same rules to disable the
  buttons; the server enforces them again, so a disabled button cannot be bypassed.

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
* Role checks: `IsManagerOrAdmin`, `IsEmployeeOrManager`, `IsAdminRole` (`users/permissions.py`).
* Object checks: `CannotReviewOwnLeave`, `IsLeaveOwner` (`leaves/permissions.py`), plus the role rules in `leaves/services.py`.
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
`employee=request.user` (see `selectors.visible_leaves`), so every action (list,
retrieve, edit, delete, ...) works only on their rows. Another employee's id gives **404**, not data. The employee
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
approve/reject, manager cannot approve own leave, manager cannot approve another
manager's leave, admin approves a manager's leave, manager creates own leave, admin sees
all (managers' too), overlapping leave rejected (several shapes), invalid dates
rejected, approved/rejected leave cannot be edited, deleted or reviewed again (409),
soft delete (row kept, who/when recorded), the two manager tables and their independent
filters, the `can_modify` / `can_review` button flags, disabled buttons on the web pages,
filtering/search/ordering/pagination, and the no-N+1 query check.

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
