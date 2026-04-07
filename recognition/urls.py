"""
urls.py  –  attendance app
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Auth ─────────────────────────────────────────────────
    path("auth/superadmin/login/", views.SuperAdminLoginView.as_view()),
    path("auth/hr/login/",         views.HRLoginView.as_view()),

    # ── SuperAdmin → HR management ────────────────────────────
    path("admin/hr/",              views.HRUserListCreateView.as_view()),
    path("admin/hr/<int:pk>/",     views.HRUserDetailView.as_view()),

    # ── HR → Employee management ──────────────────────────────
    path("employees/",             views.EmployeeListCreateView.as_view()),
    path("employees/<int:pk>/",    views.EmployeeDetailView.as_view()),

    # ── HR → Face enrollment ──────────────────────────────────
    path("faces/enroll/",                       views.FaceEnrollView.as_view()),
    path("faces/<int:employee_id>/",            views.FaceListView.as_view()),
    path("faces/<int:pk>/delete/",              views.FaceDeleteView.as_view()),

    # ── Face verification (camera / kiosk) ────────────────────
    path("faces/verify/",          views.FaceVerifyView.as_view()),

    # ── Attendance ────────────────────────────────────────────
    path("attendance/check-in/",             views.CheckInView.as_view()),
    path("attendance/check-out/",            views.CheckOutView.as_view()),
    path("attendance/",                      views.AttendanceListView.as_view()),
    path("attendance/<int:employee_id>/",    views.EmployeeAttendanceView.as_view()),

    # ── Verification logs ─────────────────────────────────────
    path("logs/",                  views.VerificationLogListView.as_view()),
]