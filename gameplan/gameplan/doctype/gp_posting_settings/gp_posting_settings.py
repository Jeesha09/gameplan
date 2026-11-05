import frappe
from frappe.model.document import Document

from gameplan.api import require_admin
from gameplan.posting_limits import CAPS, FIELDS, MAX_LIMIT


class GPPostingSettings(Document):
	def validate(self):
		require_admin()
		if self.enabled not in (0, 1) or self.caps_enabled not in (0, 1):
			frappe.throw("Choose whether posting limits and content caps are enabled")
		for field in (*FIELDS, *CAPS):
			value = self.get(field)
			if not isinstance(value, int) or not 0 <= value <= MAX_LIMIT:
				frappe.throw(f"{self.meta.get_label(field)} must be between 0 and {MAX_LIMIT}")
