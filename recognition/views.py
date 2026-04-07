"""
views.py
────────
All API views grouped by domain:
  1. Auth (login)
  2. SuperAdmin → HR management
  3. HR → Employee management
  4. HR → Face enrollment & listing
  5. System → Face verification
  6. System → Attendance check-in / check-out / listing
  7. System → Verification logs
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import (
    IsSuperAdmin, IsHRUser, IsHROrSuperAdmin,
    JWTAuthentication, login_superadmin, login_hr,
)
from .face_service import (
    extract_embedding, verify_face,
    MAX_FACE_SAMPLES_PER_EMPLOYEE, CONFIDENCE_THRESHOLD,
)
from .models import HRUser, Employee, Face, Attendance, VerificationLog
from .serializers import (
    HRUserCreateSerializer, HRUserReadSerializer,
    EmployeeSerializer,
    FaceEnrollSerializer, FaceReadSerializer,
    FaceVerifySerializer,
    AttendanceSerializer, CheckInOutSerializer,
    VerificationLogSerializer,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. AUTH
# ─────────────────────────────────────────────

class SuperAdminLoginView(APIView):
    """POST /api/auth/superadmin/login/"""

    def post(self, request):
        email = request.data.get("email", "")
        password = request.data.get("password", "")
        from rest_framework.exceptions import AuthenticationFailed
        try:
            token = login_superadmin(email, password)
        except AuthenticationFailed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": token, "role": "superadmin"})


class HRLoginView(APIView):
    """POST /api/auth/hr/login/"""

    def post(self, request):
        email = request.data.get("email", "")
        password = request.data.get("password", "")
        from rest_framework.exceptions import AuthenticationFailed
        try:
            token = login_hr(email, password)
        except AuthenticationFailed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": token, "role": "hr"})


# ─────────────────────────────────────────────
# 2. SUPERADMIN → HR MANAGEMENT
# ─────────────────────────────────────────────

class HRUserListCreateView(APIView):
    """
    GET  /api/admin/hr/        – list all HR users
    POST /api/admin/hr/        – create HR user
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = HRUser.objects.all()
        return Response(HRUserReadSerializer(qs, many=True).data)

    def post(self, request):
        ser = HRUserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        hr_user = ser.save()
        return Response(HRUserReadSerializer(hr_user).data, status=status.HTTP_201_CREATED)


class HRUserDetailView(APIView):
    """
    GET    /api/admin/hr/{id}/
    PUT    /api/admin/hr/{id}/
    DELETE /api/admin/hr/{id}/
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def _get_object(self, pk):
        try:
            return HRUser.objects.get(pk=pk)
        except HRUser.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(HRUserReadSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = HRUserCreateSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(HRUserReadSerializer(obj).data)

    def delete(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# 3. HR → EMPLOYEE MANAGEMENT
# ─────────────────────────────────────────────

class EmployeeListCreateView(APIView):
    """
    GET  /api/employees/
    POST /api/employees/
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def get(self, request):
        dept = request.query_params.get("department")
        qs = Employee.objects.prefetch_related("faces")
        if dept:
            qs = qs.filter(department__iexact=dept)
        return Response(EmployeeSerializer(qs, many=True).data)

    def post(self, request):
        ser = EmployeeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        emp = ser.save()
        return Response(EmployeeSerializer(emp).data, status=status.HTTP_201_CREATED)


class EmployeeDetailView(APIView):
    """
    GET    /api/employees/{id}/
    PUT    /api/employees/{id}/
    DELETE /api/employees/{id}/
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def _get_object(self, pk):
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EmployeeSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = EmployeeSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(EmployeeSerializer(obj).data)

    def delete(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# 4. HR → FACE ENROLLMENT
# ─────────────────────────────────────────────

class FaceEnrollView(APIView):
    """
    POST /api/faces/enroll/
    Body: multipart/form-data  { employee_id, image }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]
    parser_classes = [MultiPartParser]

    def post(self, request):
        ser = FaceEnrollSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        employee_id = ser.validated_data["employee_id"]
        image_file = ser.validated_data["image"]
        employee = Employee.objects.get(pk=employee_id)

        # Enforce max samples
        current_count = employee.faces.count()
        if current_count >= MAX_FACE_SAMPLES_PER_EMPLOYEE:
            return Response(
                {
                    "detail": (
                        f"Maximum {MAX_FACE_SAMPLES_PER_EMPLOYEE} face samples allowed. "
                        f"Delete an existing sample first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            embedding = extract_embedding(image_file)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        face = Face(employee=employee)
        face.set_embedding(embedding)
        face.save()

        return Response(
            {
                "face_id": face.pk,
                "employee_id": employee.pk,
                "employee_name": employee.name,
                "samples_enrolled": current_count + 1,
                "max_samples": MAX_FACE_SAMPLES_PER_EMPLOYEE,
            },
            status=status.HTTP_201_CREATED,
        )


class FaceListView(APIView):
    """GET /api/faces/{employee_id}/"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def get(self, request, employee_id):
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        faces = employee.faces.all()
        return Response(FaceReadSerializer(faces, many=True).data)


class FaceDeleteView(APIView):
    """DELETE /api/faces/{id}/"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def delete(self, request, pk):
        try:
            face = Face.objects.get(pk=pk)
        except Face.DoesNotExist:
            return Response({"detail": "Face not found."}, status=status.HTTP_404_NOT_FOUND)
        face.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# 5. FACE VERIFICATION (no auth needed – camera endpoint)
# ─────────────────────────────────────────────

class FaceVerifyView(APIView):
    """
    POST /api/faces/verify/
    Body: multipart/form-data { image }

    Returns employee info on match, 401 on failure.
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        ser = FaceVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        image_file = ser.validated_data["image"]

        # Load all enrolled faces (id, name, embedding_bytes)
        face_rows = Face.objects.select_related("employee").filter(
            employee__is_active=True
        ).values_list("employee_id", "employee__name", "embedding")

        result = verify_face(image_file, list(face_rows))

        # Log the attempt
        VerificationLog.objects.create(
            employee_id=result.employee_id,
            success=result.matched,
            confidence=result.confidence,
            action="verify",
            ip_address=self._get_ip(request),
        )

        if result.matched:
            return Response(
                {
                    "employee_id": result.employee_id,
                    "name": result.employee_name,
                    "confidence": result.confidence,
                }
            )

        return Response(
            {"detail": "not verified", "confidence": result.confidence}
        )

    def _get_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        return x_forwarded.split(",")[0] if x_forwarded else request.META.get("REMOTE_ADDR")


# ─────────────────────────────────────────────
# 6. ATTENDANCE
# ─────────────────────────────────────────────

class CheckInView(APIView):
    """
    POST /api/attendance/check-in/
    Body: multipart/form-data { image }
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        ser = CheckInOutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        face_rows = list(
            Face.objects.select_related("employee").filter(
                employee__is_active=True
            ).values_list("employee_id", "employee__name", "embedding")
        )

        result = verify_face(ser.validated_data["image"], face_rows)

        if not result.matched:
            VerificationLog.objects.create(
                success=False, confidence=result.confidence, action="check_in",
                ip_address=self._get_ip(request),
            )
            return Response(
                {"detail": "Face not recognized.", "confidence": result.confidence},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        today = timezone.localdate()

        # ✅ Prevent double check-in
        attendance, created = Attendance.objects.get_or_create(
            employee_id=result.employee_id,
            date=today,
            defaults={"check_in": timezone.now()},
        )

        if not created:
            return Response(
                {
                    "detail": "Already checked in today.",
                    "check_in": attendance.check_in,
                },
                status=status.HTTP_409_CONFLICT,
            )

        VerificationLog.objects.create(
            employee_id=result.employee_id, success=True,
            confidence=result.confidence, action="check_in",
            ip_address=self._get_ip(request),
        )

        return Response(
            {
                "employee_id": result.employee_id,
                "name": result.employee_name,
                "confidence": result.confidence,
                "check_in": attendance.check_in,
                "date": today,
            },
            status=status.HTTP_201_CREATED,
        )

    def _get_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        return x_forwarded.split(",")[0] if x_forwarded else request.META.get("REMOTE_ADDR")


class CheckOutView(APIView):
    """
    POST /api/attendance/check-out/
    Body: multipart/form-data { image }
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        ser = CheckInOutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        face_rows = list(
            Face.objects.select_related("employee").filter(
                employee__is_active=True
            ).values_list("employee_id", "employee__name", "embedding")
        )

        result = verify_face(ser.validated_data["image"], face_rows)

        if not result.matched:
            VerificationLog.objects.create(
                success=False, confidence=result.confidence, action="check_out",
                ip_address=self._get_ip(request),
            )
            return Response(
                {"detail": "Face not recognized.", "confidence": result.confidence},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        today = timezone.localdate()

        try:
            attendance = Attendance.objects.get(
                employee_id=result.employee_id, date=today
            )
        except Attendance.DoesNotExist:
            return Response(
                {"detail": "No check-in record found for today."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if attendance.check_out:
            return Response(
                {
                    "detail": "Already checked out today.",
                    "check_out": attendance.check_out,
                },
                status=status.HTTP_409_CONFLICT,
            )

        attendance.check_out = timezone.now()
        attendance.save(update_fields=["check_out"])

        VerificationLog.objects.create(
            employee_id=result.employee_id, success=True,
            confidence=result.confidence, action="check_out",
            ip_address=self._get_ip(request),
        )

        return Response(
            {
                "employee_id": result.employee_id,
                "name": result.employee_name,
                "confidence": result.confidence,
                "check_in": attendance.check_in,
                "check_out": attendance.check_out,
                "duration_minutes": attendance.duration_minutes(),
                "date": today,
            }
        )

    def _get_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        return x_forwarded.split(",")[0] if x_forwarded else request.META.get("REMOTE_ADDR")


class AttendanceListView(APIView):
    """
    GET /api/attendance/                    – all logs (HR/SuperAdmin)
    Query params: employee_id, date, from_date, to_date
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def get(self, request):
        qs = Attendance.objects.select_related("employee").all()

        emp_id = request.query_params.get("employee_id")
        date = request.query_params.get("date")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if emp_id:
            qs = qs.filter(employee_id=emp_id)
        if date:
            qs = qs.filter(date=date)
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)

        return Response(AttendanceSerializer(qs, many=True).data)


class EmployeeAttendanceView(APIView):
    """GET /api/attendance/{employee_id}/"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def get(self, request, employee_id):
        qs = Attendance.objects.filter(employee_id=employee_id).select_related("employee")
        return Response(AttendanceSerializer(qs, many=True).data)


# ─────────────────────────────────────────────
# 7. VERIFICATION LOGS
# ─────────────────────────────────────────────

class VerificationLogListView(APIView):
    """GET /api/logs/"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsHROrSuperAdmin]

    def get(self, request):
        qs = VerificationLog.objects.select_related("employee").all()[:200]
        return Response(VerificationLogSerializer(qs, many=True).data)