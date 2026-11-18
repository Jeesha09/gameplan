import frappe
from frappe.model.document import Document

from gameplan.api import require_admin


class GPSettings(Document):
	def validate(self):
		require_admin()
		for field in ("min_title_length", "max_title_length", "min_post_length"):
			if not 0 <= (self.get(field) or 0) <= 10000:
				frappe.throw(f"{self.meta.get_label(field)} must be between 0 and 10000")
		if self.min_title_length and self.max_title_length and self.min_title_length > self.max_title_length:
			frappe.throw("The shortest title cannot be longer than the longest title")
