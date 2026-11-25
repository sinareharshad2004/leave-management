# Requirements checklist: Mid-Level Django Coding Practice Task

Source: `Mid_Level_Django_Coding_Practice_Task.docx` (Employee Leave Management API).
Status: Done = implemented in this project. Tests are in `users/tests`, `leaves/tests`, `web/tests`.

| # | Requirement | Status | Where |
| --- | --- | --- | --- |
| 1 | User model (id, name, email, role EMPLOYEE/MANAGER/ADMIN) | Done | `users/models.py` (custom user, email login) |
| 1 | Leave model (employee, type, dates, reason, status, approved_by, created_at) | Done | `leaves/models.py` |
| 2 | JWT: register, login, me | Done | `users/auth_urls.py` (+ token refresh, + separate employee/manager logins) |
| 3 | Employee APIs: POST/GET list/GET one/DELETE | Done | `leaves/views.py` |
| 3 | Manager APIs: pending, approve, reject | Done | `leaves/views.py` |
| 3 | Admin APIs: GET /api/users/, GET /api/leaves/ | Done | `users/views.py`, `leaves/views.py` |
| 4 | Employee sees only own leaves (queryset level) | Done | `LeaveViewSet.get_queryset()` |
| 4 | Delete only own PENDING leave | Done | `services.delete_pending_leave` |
| 4 | Employee cannot approve/reject | Done | `IsManagerOrAdmin` |
| 4 | Manager cannot approve own leave | Done | `CannotReviewOwnLeave` + service check |
| 4 | Approved/rejected leave cannot change again (409) | Done | `services._review_leave` |
| 4 | Custom DRF permission classes | Done | `users/permissions.py`, `leaves/permissions.py` |
| 5 | start <= end, no past start, no overlap, clear errors | Done | `LeaveSerializer.validate` + `services.create_leave` + DB constraint |
| 6 | Filters status / leave_type / employee, pagination, ordering | Done | `leaves/filters.py`, `common/pagination.py` |
| 7 | select_related for employee and approved_by | Done | `get_queryset()`, N+1 test |
| 8 | transaction.atomic + row lock on approve | Done | `services._review_leave` |
| 9 | All 11 listed tests | Done | see test files |
| 12 | The 9 "explain" questions | Answered | `README.md` section 5 |
| 14 | No business logic in views, no is_authenticated-only checks | Done | `services.py` holds the rules |

## Role rules (updated)
| Rule | Where |
| --- | --- |
| Employee creates own leave, sees only own leaves | `selectors.visible_leaves`, `IsEmployeeOrManager` |
| Employee deletes own leave only while PENDING | `services.delete_pending_leave`, `IsLeaveOwner` |
| Deleting keeps the row (soft delete) and records who and when | `Leave.status = DELETED`, `deleted_by`, `deleted_at`; migration `0002_soft_delete` |
| Manager page shows two tables: Own leave and Employee leave | `web/views.py` `manager_dashboard`, `selectors.own_leaves` / `other_leaves`, `_leave_table.html` |
| Manager creates own leave | `IsEmployeeOrManager`, `services.create_leave` |
| Manager's leave approved/rejected by an admin only | `services.review_denial_reason` |
| Manager approves/rejects employees' leaves, never their own | `services.review_denial_reason`, `CannotReviewOwnLeave` |
| Admin sees every leave, including managers' | `selectors.visible_leaves` |
| Approved/rejected/deleted leave cannot be edited, deleted or reviewed again (409) | `services.ensure_pending`, `services._review_leave` |
| Button enabled only while PENDING | `can_modify` / `can_review` in `LeaveSerializer`; `web/templates/web/_delete_button.html` |

## Decisions that go beyond or differ from the document
1. **Employees and managers can create leave; admins cannot.** A manager's own leave is
   reviewed by an admin only.
2. **Managers do not see other managers' leaves** (an admin does). Remove the
   `Q(employee__role=...)` rule in `selectors.visible_leaves` to change this.
3. **Admins can view every leave but cannot edit or delete someone else's request.**
4. **Nobody can review their own leave** (admins included).
5. **`approved_by` stores the reviewer for rejections too** (the model has no
   separate rejected_by field).
6. **Extras not in the document:** separate employee/manager login endpoints, web pages
   (`/`, `/employee/`, `/manager/`), and `PATCH /api/leaves/{id}/` to edit a pending leave.
7. **SQLite ignores `select_for_update`.** Use PostgreSQL to get real row locking
   for the two-reviewers-at-once case.
