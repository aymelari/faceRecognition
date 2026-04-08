import numpy as np
from django.db import models
from django.contrib.auth.hashers import make_password


class HRUser(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Hash password only if it hasn't been hashed yet
        if not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        db_table = "hr_users"
        ordering = ["-created_at"]


class Employee(models.Model):
    name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.position} ({self.department})"

    class Meta:
        db_table = "employees"
        ordering = ["name"]


class Face(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="faces"
    )
    embedding = models.BinaryField()  # Stores numpy float32 array as bytes
    created_at = models.DateTimeField(auto_now_add=True)

    def get_embedding(self) -> np.ndarray:
        """Deserialize embedding from binary field."""
        return np.frombuffer(bytes(self.embedding), dtype=np.float32)

    def set_embedding(self, embedding: np.ndarray):
        """Serialize numpy array to binary field."""
        self.embedding = embedding.astype(np.float32).tobytes()

    def __str__(self):
        return f"Face sample for {self.employee.name} (#{self.pk})"

    class Meta:
        db_table = "faces"
        ordering = ["-created_at"]


class Attendance(models.Model):
    """Tracks individual check-in/check-out sessions.
    Multiple sessions per day allowed for employees who leave and return.
    """
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="attendances"
    )
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    date = models.DateField()  # Derived from check_in for easy querying

    def duration_minutes(self):
        """Return total minutes worked, or None if not yet checked out."""
        if self.check_in and self.check_out:
            delta = self.check_out - self.check_in
            return round(delta.total_seconds() / 60, 1)
        return None

    @classmethod
    def total_duration_for_date(cls, employee_id, date):
        """Calculate total minutes worked by employee on a given date."""
        sessions = cls.objects.filter(
            employee_id=employee_id, date=date, check_out__isnull=False
        )
        total_seconds = 0
        for session in sessions:
            if session.check_in and session.check_out:
                delta = session.check_out - session.check_in
                total_seconds += delta.total_seconds()
        return round(total_seconds / 60, 1) if total_seconds > 0 else 0.0

    @classmethod
    def total_duration_for_range(cls, employee_id, from_date, to_date):
        """Calculate total minutes worked by employee between two dates."""
        sessions = cls.objects.filter(
            employee_id=employee_id, date__gte=from_date, date__lte=to_date,
            check_out__isnull=False
        )
        total_seconds = 0
        for session in sessions:
            if session.check_in and session.check_out:
                delta = session.check_out - session.check_in
                total_seconds += delta.total_seconds()
        return round(total_seconds / 60, 1) if total_seconds > 0 else 0.0

    def __str__(self):
        return f"{self.employee.name} | {self.date} | in={self.check_in} out={self.check_out}"

    class Meta:
        db_table = "attendance"
        ordering = ["-date", "-check_in"]


class VerificationLog(models.Model):
    employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="verification_logs"
    )
    success = models.BooleanField()
    confidence = models.FloatField(null=True, blank=True)
    action = models.CharField(
        max_length=20,
        choices=[("verify", "Verify"), ("check_in", "Check-In"), ("check_out", "Check-Out")],
        default="verify",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "✅" if self.success else "❌"
        name = self.employee.name if self.employee else "Unknown"
        return f"{status} {name} | {self.action} | conf={self.confidence} | {self.timestamp}"

    class Meta:
        db_table = "verification_logs"
        ordering = ["-timestamp"]