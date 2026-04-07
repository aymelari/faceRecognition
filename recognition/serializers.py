from rest_framework import serializers
from .models import HRUser, Employee, Face, Attendance, VerificationLog


# ─────────────────────────────────────────────
# HR User
# ─────────────────────────────────────────────

class HRUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = HRUser
        fields = ["id", "name", "email", "password", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class HRUserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = HRUser
        fields = ["id", "name", "email", "is_active", "created_at"]
        read_only_fields = fields


# ─────────────────────────────────────────────
# Employee
# ─────────────────────────────────────────────

class EmployeeSerializer(serializers.ModelSerializer):
    face_count = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "name", "position", "department", "is_active", "face_count", "created_at"]
        read_only_fields = ["id", "face_count", "created_at"]

    def get_face_count(self, obj):
        return obj.faces.count()


# ─────────────────────────────────────────────
# Face
# ─────────────────────────────────────────────

class FaceEnrollSerializer(serializers.Serializer):
    """Accepts a raw image upload for face enrollment."""
    employee_id = serializers.IntegerField()
    image = serializers.ImageField()

    def validate_employee_id(self, value):
        try:
            Employee.objects.get(pk=value, is_active=True)
        except Employee.DoesNotExist:
            raise serializers.ValidationError("Active employee not found.")
        return value


class FaceReadSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = Face
        fields = ["id", "employee", "employee_name", "created_at"]
        read_only_fields = fields


# ─────────────────────────────────────────────
# Face Verification
# ─────────────────────────────────────────────

class FaceVerifySerializer(serializers.Serializer):
    """Accepts an image for real-time face verification."""
    image = serializers.ImageField()


class FaceVerifyResponseSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    name = serializers.CharField()
    confidence = serializers.FloatField()


# ─────────────────────────────────────────────
# Attendance
# ─────────────────────────────────────────────

class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name",
            "date", "check_in", "check_out", "duration_minutes",
        ]
        read_only_fields = fields

    def get_duration_minutes(self, obj):
        return obj.duration_minutes()


class CheckInOutSerializer(serializers.Serializer):
    """Image-based check-in / check-out payload."""
    image = serializers.ImageField()


# ─────────────────────────────────────────────
# Verification Log
# ─────────────────────────────────────────────

class VerificationLogSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = VerificationLog
        fields = [
            "id", "employee", "employee_name",
            "success", "confidence", "action", "ip_address", "timestamp",
        ]
        read_only_fields = fields

    def get_employee_name(self, obj):
        return obj.employee.name if obj.employee else "Unknown"