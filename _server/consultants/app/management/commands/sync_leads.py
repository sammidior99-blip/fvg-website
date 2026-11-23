"""Fill in student/client details on older records and register every existing website enquiry (run by install.sh; safe to repeat)."""
from django.apps import apps
from django.core.management.base import BaseCommand

from consultants.leads import from_enquiry
from consultants.models import Referral


class Command(BaseCommand):
    help = "Register existing website enquiries as leads (unassigned unless already credited to a consultant)."

    def handle(self, *a, **k):
        try:
            E = apps.get_model("pages", "Enquiry")
        except LookupError:
            self.stdout.write("no pages.Enquiry - nothing to do"); return
        filled = 0
        for r in Referral.objects.filter(student_name="", parent_name=""):
            e = E._base_manager.filter(pk__in=r.enquiry_list()).first()
            if not e: continue
            g = lambda f: getattr(e, f, "") or ""
            r.student_name, r.parent_name, r.phone, r.email, r.school = g("student_name"), g("parent_name"), g("phone"), g("email"), g("school")
            r.grade = str(e.get_grade_display() if hasattr(e, "get_grade_display") else g("grade"))[:50]
            r.interest = str(e.get_service_display() if hasattr(e, "get_service_display") else g("service"))[:200]
            if r.consultant_id and not r.last_activity: r.last_activity = r.updated_at
            r.save(); filled += 1
        linked = set()
        for r in Referral.objects.exclude(enquiry_ids=""): linked.update(r.enquiry_list())
        qs = E._base_manager.all().order_by("pk")
        if hasattr(E, "deleted_at"): qs = qs.filter(deleted_at__isnull=True)
        added = 0
        for e in qs:
            if e.pk in linked: continue
            from_enquiry(e); added += 1
        self.stdout.write(f"leads: details filled {filled}, website enquiries registered {added}, total {Referral.objects.count()}")
