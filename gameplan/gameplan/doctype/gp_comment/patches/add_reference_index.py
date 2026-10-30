# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors

from ..gp_comment import add_indexes


def execute():
	"""Add (reference_doctype, reference_name) index on GP Comment"""
	add_indexes()
