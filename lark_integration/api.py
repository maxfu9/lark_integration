import json
import os
import re
import subprocess
import time
from collections.abc import Iterable
from datetime import datetime, time as dt_time, timedelta
from urllib.parse import quote

import frappe
import requests
from frappe.utils import fmt_money, get_datetime
from frappe.utils.pdf import get_pdf

LARK_BASE_URL = "https://open.larksuite.com/open-apis"
TOKEN_CACHE_KEY = "lark_integration:tenant_access_token"

# Maps human-readable reminder label (stored in ERPNext) to Lark's relative_fire_minute (int)
REMINDER_LABEL_TO_MINUTES = {
	"At due time":        0,
	"5 minutes before":   5,
	"15 minutes before":  15,
	"30 minutes before":  30,
	"1 hour before":      60,
	"2 hours before":     120,
	"1 day before":       1440,
	"2 days before":      2880,
	"1 week before":      10080,
}
# Reverse: minutes → label (for Lark → ERPNext)
REMINDER_MINUTES_TO_LABEL = {v: k for k, v in REMINDER_LABEL_TO_MINUTES.items()}
DEFAULT_REQUEST_TIMEOUT = 20
LARK_DRIVE_PARENT_TYPE = "explorer"


def _conf(key: str, default: str = "") -> str:
	value = frappe.conf.get(key)
	return str(value) if value else default


TAG_RE = re.compile(r"<.*?>")
SESSION = requests.Session()


# --- HELPER FUNCTIONS ---
def clean_html(raw_html):
	if not raw_html:
		return ""
	return re.sub(TAG_RE, "", str(raw_html)).strip()


def _ts_ms(value):
	if not value:
		return None
	return int(get_datetime(value).timestamp() * 1000)


def _log_api_error(context: str, payload: dict | None = None):
	title = (context or "Lark Integration API Error").strip()
	if len(title) > 140:
		title = f"{title[:137]}..."

	message = context
	if payload:
		try:
			import json
			message += f"\n\nPayload:\n{json.dumps(payload, indent=2)}"
		except Exception:
			message += f"\n\nPayload: {payload}"

	frappe.log_error(title=title, message=message)





def _safe_int(value, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _doctype_available(doctype_name: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype_name))
	except Exception:
		return False



def _get_settings_doc():
	if not _doctype_available("Lark Integration Settings"):
		return None
	try:
		return frappe.get_cached_doc("Lark Integration Settings")
	except Exception:
		return None


def _get_config():
	settings = _get_settings_doc()
	settings_enabled = bool(settings.enabled) if settings else True

	config = {
		"enabled": settings_enabled,
		"app_id": _conf("lark_app_id", ""),
		"app_secret": _conf("lark_app_secret", ""),
		"request_timeout": _safe_int(_conf("lark_request_timeout", str(DEFAULT_REQUEST_TIMEOUT)), DEFAULT_REQUEST_TIMEOUT),
		"drive_upload_enabled": False,
		"drive_folder_token": "",
		"replace_erpnext_files_after_upload": True,
	}

	if settings:
		config["app_id"] = settings.app_id or config["app_id"]
		config["app_secret"] = settings.get_password("app_secret") or config["app_secret"]
		config["request_timeout"] = _safe_int(settings.request_timeout, config["request_timeout"])

		if settings.drive_upload_enabled is not None:
			config["drive_upload_enabled"] = bool(settings.drive_upload_enabled)
		config["drive_folder_token"] = settings.drive_folder_token or ""
		if settings.replace_erpnext_files_after_upload is not None:
			config["replace_erpnext_files_after_upload"] = bool(settings.replace_erpnext_files_after_upload)

	if config["request_timeout"] <= 0:
		config["request_timeout"] = DEFAULT_REQUEST_TIMEOUT

	return config

@frappe.whitelist()
def clear_lark_cache(doc=None, method=None):
	"""Clears all cached Lark mappings and configuration."""
	frappe.cache().delete_keys("lark_sync_mapping:*")
	frappe.cache().delete_keys("lark_integration:*")
	if doc and doc.doctype == "Lark Sync Document":
		frappe.cache().delete_value(f"lark_sync_mapping:{doc.document_type}")
	
	import time
	# Use a small sleep to ensure cache is cleared across all workers if needed
	# though delete_keys is usually enough for Redis.
	return True


def _get_sync_mapping(doctype: str):
	cache_key = f"lark_sync_mapping:{doctype}"
	cached_mapping = frappe.cache().get_value(cache_key)
	if cached_mapping is not None:
		return cached_mapping

	mapping = {}



	# Per-doctype override from Lark Sync Document
	if _doctype_available("Lark Sync Document"):
		row = frappe.db.get_value(
			"Lark Sync Document",
			{"document_type": doctype, "enabled": 1},
			[
				"name",
				"key_field",
				"app_token",
				"main_table_id",
				"items_table_id",
				"sync_attachments",
				"attachment_sync_mode",
				"sync_child_table",
				"child_table_field",
				"child_table_doctype",
				"enable_item_summary",
				"summary_child_table",
				"summary_row_template",
				"summary_lark_field",
			],
			as_dict=True,
		)
		if row:
			mapping["key_field"] = row.key_field or mapping.get("key_field")
			mapping["app_token"] = row.app_token
			mapping["main_table_id"] = row.main_table_id or mapping.get("main_table_id")
			mapping["items_table_id"] = row.items_table_id or mapping.get("items_table_id")
			mapping["sync_attachments"] = bool(row.sync_attachments)
			mapping["attachment_sync_mode"] = row.attachment_sync_mode or "Both"
			mapping["sync_child_table"] = bool(row.sync_child_table)
			mapping["child_table_field"] = row.child_table_field
			mapping["child_table_doctype"] = row.child_table_doctype
			mapping["enable_item_summary"] = bool(row.enable_item_summary)
			mapping["summary_child_table"] = row.summary_child_table
			mapping["summary_row_template"] = row.summary_row_template
			mapping["summary_lark_field"] = row.summary_lark_field or "Item Details"

			sync_doc = frappe.get_doc("Lark Sync Document", row.name)

			mapping["custom_fields"] = []
			if _doctype_available("Lark Sync Field"):
				mapping["custom_fields"] = [
					{
						"lark_field": d.lark_field,
						"erp_field_path": d.erp_field_path or d.erp_field,
						"value_type": d.value_type,
						"default_value": d.default_value,
						"clear_if_empty": bool(d.clear_if_empty),
					}
					for d in sync_doc.get("field_mappings", [])
					if d.lark_field and (d.erp_field_path or d.erp_field)
				]

			mapping["child_tables"] = []
			if _doctype_available("Lark Sync Child Table"):
				mapping["child_tables"] = [
					{
						"child_table_field": d.child_table_field,
						"child_table_doctype": d.child_table_doctype,
						"items_table_id": d.items_table_id,
					}
					for d in sync_doc.get("child_tables", [])
					if d.child_table_field
				]

			mapping["child_fields"] = []
			if _doctype_available("Lark Sync Child Field"):
				mapping["child_fields"] = [
					{
						"lark_field": d.lark_field,
						"child_table_field": d.child_table_field,
						"child_field_path": d.child_field_path or d.child_field,
						"value_type": d.value_type,
						"default_value": d.default_value,
						"clear_if_empty": bool(d.clear_if_empty),
					}
					for d in sync_doc.get("child_field_mappings", [])
					if d.lark_field and (d.child_field_path or d.child_field)
				]

	mapping["app_token"] = mapping.get("app_token")

	if not mapping.get("main_table_id") or not mapping.get("key_field") or not mapping.get("app_token"):
		frappe.cache().set_value(cache_key, None)
		return None

	frappe.cache().set_value(cache_key, mapping)
	return mapping


def _resolve_field_path(doc, field_path: str):
	current = doc
	for key in (field_path or "").split("."):
		if not key:
			continue
		if current is None:
			return None
		if hasattr(current, "get"):
			current = current.get(key)
		elif isinstance(current, dict):
			current = current.get(key)
		else:
			current = getattr(current, key, None)
	return current


def _cast_custom_value(value, value_type: str):
	if value in (None, ""):
		return None

	cast_type = (value_type or "Text").strip()
	if cast_type == "Float":
		try:
			return float(value)
		except (TypeError, ValueError):
			return None
	if cast_type == "Int":
		try:
			return int(value)
		except (TypeError, ValueError):
			return None
	if cast_type == "Check":
		return bool(value)
	if cast_type in {"Date", "Datetime"}:
		return _ts_ms(value)
	if cast_type == "Raw":
		return value
	return str(value)


def _apply_custom_field_mappings(fields: dict, doc, mapping: dict):
	for custom in mapping.get("custom_fields", []):
		lark_field = custom.get("lark_field")
		if not lark_field:
			continue

		raw_value = _resolve_field_path(doc, custom.get("erp_field_path", ""))
		if raw_value in (None, "") and custom.get("default_value") not in (None, ""):
			raw_value = custom.get("default_value")

		casted_value = _cast_custom_value(raw_value, custom.get("value_type"))
		if casted_value is None and not custom.get("clear_if_empty"):
			continue

		fields[lark_field] = casted_value


def _build_fields_payload(doc, mapping: dict):
	fields = {}

	for custom in mapping.get("custom_fields", []):
		lark_field = custom.get("lark_field")
		if not lark_field:
			continue

		raw_value = _resolve_field_path(doc, custom.get("erp_field_path", ""))
		if raw_value in (None, "") and custom.get("default_value") not in (None, ""):
			raw_value = custom.get("default_value")

		casted_value = _cast_custom_value(raw_value, custom.get("value_type"))
		if casted_value is None and not custom.get("clear_if_empty"):
			continue

		if lark_field == mapping.get("key_field"):
			try:
				base_url = frappe.utils.get_url()
				doc_url = f"{base_url}/app/{frappe.scrub(doc.doctype)}/{doc.name}"
				fields[lark_field] = {
					"link": doc_url,
					"text": str(casted_value)
				}
			except Exception:
				fields[lark_field] = casted_value
		else:
			fields[lark_field] = casted_value


	if mapping.get("key_field") and mapping.get("key_field") not in fields:
		try:
			base_url = frappe.utils.get_url()
			doc_url = f"{base_url}/app/{frappe.scrub(doc.doctype)}/{doc.name}"
			fields[mapping["key_field"]] = {
				"link": doc_url,
				"text": str(doc.name)
			}
		except Exception:
			fields[mapping["key_field"]] = str(doc.name)

	# Formatted Item Summary from config
	items_summary = _build_doc_item_summary(doc, mapping)
	if items_summary:
		fields[mapping.get("summary_lark_field") or "Item Details"] = items_summary

	return fields


def _get_doc_attachment_tokens(doc):
	"""Fetch all Lark Drive File tokens associated with the given document."""
	tokens = []
	if not _doctype_available("Lark Drive File"):
		return tokens

	try:
		records = frappe.get_all(
			"Lark Drive File",
			filters={
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name
			},
			fields=["bitable_token"]
		)
		for r in records:
			if r.bitable_token:
				tokens.append(r.bitable_token)
	except Exception:
		pass
	
	return tokens

def _build_doc_item_summary(doc, mapping: dict):
	"""Generate a formatted item summary based on mapping settings."""
	if not mapping.get("enable_item_summary") or not mapping.get("summary_child_table"):
		return ""

	child_table = mapping["summary_child_table"]
	template = mapping.get("summary_row_template")

	if not template:
		return ""

	lines = []
	for d in doc.get(child_table) or []:
		try:
			# Support standard {fieldname} by converting to Jinja {{ fieldname }}
			jinja_template = str(template).replace("{", "{{ ").replace("}", " }}")
			row_str = frappe.render_template(jinja_template, d.as_dict())
			if row_str.strip():
				lines.append(row_str.strip())
		except Exception:
			continue

	return "\n".join(lines)


def _build_child_item_records(child_rows, child_fields, key_field: str, parent_name: str):
	item_records = []
	for row in child_rows or []:
		fields = {}
		for custom in child_fields or []:
			lark_field = custom.get("lark_field")
			if not lark_field:
				continue

			raw_value = _resolve_field_path(row, custom.get("child_field_path", ""))
			if raw_value in (None, "") and custom.get("default_value") not in (None, ""):
				raw_value = custom.get("default_value")

			casted_value = _cast_custom_value(raw_value, custom.get("value_type"))
			if casted_value is None and not custom.get("clear_if_empty"):
				continue

			fields[lark_field] = casted_value

		if key_field and key_field not in fields:
			fields[key_field] = str(parent_name)

		if fields:
			item_records.append({"fields": fields})

	return item_records


def _sync_child_tables(doc, mapping: dict, token: str, app_token: str):
	if not mapping.get("sync_child_table"):
		return False

	child_fields = mapping.get("child_fields") or []
	if not child_fields:
		return False

	child_tables = mapping.get("child_tables") or []
	if child_tables:
		for child in child_tables:
			child_table_field = child.get("child_table_field")
			if not child_table_field:
				continue
			table_id = child.get("items_table_id") or mapping.get("items_table_id")
			if not table_id:
				continue
			fields_for_table = [
				d for d in child_fields if not d.get("child_table_field") or d.get("child_table_field") == child_table_field
			]
			item_records = _build_child_item_records(
				doc.get(child_table_field), fields_for_table, mapping.get("key_field"), doc.name
			)
			clear_and_sync_items(table_id, mapping.get("key_field"), doc.name, item_records, token, app_token, reference_doctype=doc.doctype, reference_name=doc.name)
		return True

	child_table_field = mapping.get("child_table_field")
	if child_table_field and mapping.get("items_table_id"):
		fields_for_table = [
			d for d in child_fields if not d.get("child_table_field") or d.get("child_table_field") == child_table_field
		]
		item_records = _build_child_item_records(
			doc.get(child_table_field), fields_for_table, mapping.get("key_field"), doc.name
		)
		clear_and_sync_items(
			mapping.get("items_table_id"),
			mapping.get("key_field"),
			doc.name,
			item_records,
			token,
			app_token,
			reference_doctype=doc.doctype,
			reference_name=doc.name
		)
		return True

	return False


def _lark_request(method: str, url: str, token: str | None = None, **kwargs):
	headers = dict(kwargs.pop("headers", {}) or {})
	if token:
		headers["Authorization"] = f"Bearer {token}"

	config = _get_config()
	response = None
	
	# Reference for logging
	ref_doctype = kwargs.pop("reference_doctype", None)
	ref_name = kwargs.pop("reference_name", None)
	
	# Allow caller to override default timeout, useful for large file uploads
	req_timeout = kwargs.pop("timeout", config.get("request_timeout", 20))
	
	import time
	MAX_RETRIES = 3
	BASE_DELAY = 1.0
	
	for attempt in range(MAX_RETRIES):
		try:
			response = SESSION.request(method, url, headers=headers, timeout=req_timeout, **kwargs)
			
			# If rate limited (429) or Server Error (5xx), raise HTTPError to trigger retry
			if response.status_code == 429 or int(response.status_code / 100) == 5:
				response.raise_for_status()
				
			# If we got here and it's a 4xx client error (but not 429), it's a hard failure
			if int(response.status_code / 100) == 4 and response.status_code != 429:
				response.raise_for_status()

			break # Success, exit retry loop
			
		except requests.RequestException as exc:
			is_retryable = False
			status_code = getattr(response, "status_code", None)
			
			# Retry on network timeouts or specific HTTP statuses
			if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
				is_retryable = True
			elif status_code in (429, 500, 502, 503, 504):
				is_retryable = True
				# Don't retry if it's a monthly quota limit reached error
				if status_code == 429 and response is not None:
					try:
						res_json = response.json()
						if res_json.get("code") == 99991403:
							is_retryable = False
					except Exception:
						pass
				
			if is_retryable and attempt < MAX_RETRIES - 1:
				delay = BASE_DELAY * (2 ** attempt)
				frappe.log_error(title=f"Lark API Retry {attempt+1}", message=f"URL: {url} | Error: {exc} | Retrying in {delay}s")
				time.sleep(delay)
				continue
				
			# If we exhausted retries or it's a non-retryable error, log and fail
			detail = {
				"status_code": status_code,
				"attempt_count": attempt + 1
			}
			try:
				detail["body"] = response.text if response is not None else None
			except Exception:
				detail["body"] = None
			
			_log_api_error(f"{method} {url} failed after {attempt+1} attempts: {exc}", detail)
			
			if response is not None:
				_log_api_call(method, url, kwargs, response, ref_doctype, ref_name)

			return None

	# Success - Log if enabled
	if response is not None:
		_log_api_call(method, url, kwargs, response, ref_doctype, ref_name)

	try:
		payload = response.json()
	except ValueError:
		_log_api_error(f"{method} {url} returned non-JSON response")
		return None

	if payload.get("code") not in (None, 0):
		# Only log API level logic errors if it's truly an unexpected result
		log_verbosity = frappe.conf.get("lark_log_verbosity", "errors")
		if log_verbosity == "all" or payload.get("code") not in (1061054,):
			_log_api_error(f"{method} {url} returned Lark code={payload.get('code')}", payload)
		return None

	return payload


def _log_api_call(method, url, request_payload, response, reference_doctype=None, reference_name=None):
	"""Helper to log Lark API calls to Lark API Log DocType."""
	try:
		# Use cache to avoid hitting DB every time
		settings_enabled = frappe.cache().get_value("lark_api_logging_enabled")
		if settings_enabled is None:
			settings = frappe.get_cached_doc("Lark Integration Settings")
			settings_enabled = settings.enable_api_logging
			frappe.cache().set_value("lark_api_logging_enabled", settings_enabled, expires_in_sec=600)
		
		if not settings_enabled:
			return

		import json
		res_payload = ""
		try:
			res_payload = json.dumps(response.json(), indent=4)
		except Exception:
			res_payload = response.text

		# Filter kwargs to only log relevant data
		req_data = {}
		for k, v in request_payload.items():
			if k in ("json", "data", "params"):
				req_data[k] = v

		log = frappe.get_doc({
			"doctype": "Lark API Log",
			"method": method,
			"url": url,
			"status_code": response.status_code,
			"request_payload": json.dumps(req_data, indent=4),
			"response_payload": res_payload,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name
		})
		log.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		# Never let logging crash the main sync
		pass


def _validate_config() -> bool:
	config = _get_config()
	if not config["enabled"]:
		return False
	if config["app_id"] and config["app_secret"]:
		return True
	_log_api_error("Missing Lark credentials/config. Configure Lark Integration Settings or site_config values")
	return False


def get_lark_token(force_refresh: bool = False):
	if not _validate_config():
		return None

	config = _get_config()
	cache = frappe.cache()
	cache_key = f"{TOKEN_CACHE_KEY}:{config['app_id']}"
	if not force_refresh:
		cached_token = cache.get_value(cache_key)
		if cached_token:
			return cached_token

	auth_url = f"{LARK_BASE_URL}/auth/v3/tenant_access_token/internal"
	payload = _lark_request("POST", auth_url, json={"app_id": config["app_id"], "app_secret": config["app_secret"]})
	if not payload:
		return None

	token = payload.get("tenant_access_token")
	expire = int(payload.get("expire") or 0)
	if token:
		expires_in = max(expire - 120, 60) if expire else 60
		cache.set_value(cache_key, token, expires_in_sec=expires_in)
	return token


def get_erp_link(doctype, docname):
	return f"{frappe.utils.get_url()}/app/{doctype.lower().replace(' ', '-')}/{docname}"


def upload_pdf_to_lark(doc, token, app_token):
	if not token or not app_token:
		return None

	try:
		html = frappe.get_print(doc.doctype, doc.name)
		pdf_content = get_pdf(html)
		if not pdf_content:
			return None

		upload_url = f"{LARK_BASE_URL}/drive/v1/medias/upload_all"
		params = {
			"file_name": f"{doc.name}.pdf",
			"parent_type": "bitable_file",
			"parent_node": app_token,
			"size": len(pdf_content),
		}
		files = {"file": (f"{doc.name}.pdf", pdf_content, "application/pdf")}
		payload = _lark_request("POST", upload_url, token=token, data=params, files=files, timeout=120, reference_doctype=doc.doctype, reference_name=doc.name)
		if not payload:
			return None

		return payload.get("data", {}).get("file_token")

	except Exception:
		frappe.log_error(title=f"Lark PDF Upload Fail: {doc.doctype} {doc.name}", message=frappe.get_traceback())
		return None


def upsert_lark_record(table_id, field_name, doc_name, fields, token, app_token, reference_doctype=None, reference_name=None):
	if not token or not app_token:
		return None

	url = f"{LARK_BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
	
	# Try exact match first
	search_query = {
		"filter": {
			"conjunction": "and",
			"conditions": [{"field_name": field_name, "operator": "is", "value": [doc_name]}],
		},
		"page_size": 1
	}
	search_res = _lark_request("POST", f"{url}/search", token=token, json=search_query, reference_doctype=reference_doctype, reference_name=reference_name)
	
	items = search_res.get("data", {}).get("items", []) if search_res else []
	
	# Fallback: if 'is' fails, try 'contains' (handles URL fields where text is custom but link contains ID)
	if not items:
		search_query["filter"]["conditions"][0]["operator"] = "contains"
		search_res = _lark_request("POST", f"{url}/search", token=token, json=search_query)
		items = search_res.get("data", {}).get("items", []) if search_res else []

	if items:
		# Update existing
		record_id = items[0]["record_id"]
		return _lark_request("PUT", f"{url}/{record_id}", token=token, json={"fields": fields}, reference_doctype=reference_doctype, reference_name=reference_name)
		
	# Create new
	return _lark_request("POST", url, token=token, json={"fields": fields}, reference_doctype=reference_doctype, reference_name=reference_name)


def clear_and_sync_items(table_id, parent_field_name, doc_name, item_records, token, app_token, reference_doctype=None, reference_name=None):
	if not token or not app_token or not table_id:
		return None

	url = f"{LARK_BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
	search_query = {
		"filter": {
			"conjunction": "and",
			"conditions": [{"field_name": parent_field_name, "operator": "is", "value": [doc_name]}],
		}
	}

	search_res = _lark_request("POST", f"{url}/search", token=token, json=search_query, reference_doctype=reference_doctype, reference_name=reference_name)
	if search_res is None:
		return None

	items = search_res.get("data", {}).get("items", [])
	if items:
		record_ids = [item.get("record_id") for item in items if item.get("record_id")]
		if record_ids:
			_lark_request("POST", f"{url}/batch_delete", token=token, json={"records": record_ids}, reference_doctype=reference_doctype, reference_name=reference_name)

	if item_records:
		_lark_request("POST", f"{url}/batch_create", token=token, json={"records": item_records}, reference_doctype=reference_doctype, reference_name=reference_name)

	return True


def upload_to_lark_drive(file_name: str, content: bytes, token: str, folder_token: str, reference_doctype=None, reference_name=None):
	if not token or not folder_token or not content:
		return None

	upload_url = f"{LARK_BASE_URL}/drive/v1/medias/upload_all"
	params = {
		"file_name": file_name,
		"parent_type": LARK_DRIVE_PARENT_TYPE,
		"parent_node": folder_token,
		"size": len(content),
	}
	files = {"file": (file_name, content, "application/octet-stream")}
	payload = _lark_request("POST", upload_url, token=token, data=params, files=files, timeout=120, reference_doctype=reference_doctype, reference_name=reference_name)
	if not payload:
		return None
	return payload.get("data", {}).get("file_token")

def upload_attachment_to_bitable(file_name: str, content: bytes, token: str, app_token: str, reference_doctype=None, reference_name=None):
	if not token or not app_token or not content:
		return None

	upload_url = f"{LARK_BASE_URL}/drive/v1/medias/upload_all"
	params = {
		"file_name": file_name,
		"parent_type": "bitable_file",
		"parent_node": app_token,
		"size": len(content),
	}
	files = {"file": (file_name, content, "application/octet-stream")}
	payload = _lark_request("POST", upload_url, token=token, data=params, files=files, timeout=120, reference_doctype=reference_doctype, reference_name=reference_name)
	if not payload:
		return None
	return payload.get("data", {}).get("file_token")
	return payload.get("data", {}).get("file_token")


def _get_or_create_nested_folder(path_parts: list[str], parent_token: str, token: str):
	"""
	Iteratively find or create folders along a path.
	Example: path_parts=["Sales Invoice", "2026", "March"]
	"""
	current_parent = parent_token
	for folder_name in path_parts:
		if not folder_name:
			continue
		current_parent = _get_or_create_single_folder(folder_name, current_parent, token)
	return current_parent


def _get_or_create_single_folder(name: str, parent_token: str, token: str):
	"""Find or create a single folder level in Lark Drive."""
	if not name or not parent_token or not token:
		return parent_token

	cache_key = f"lark_folder:{parent_token}:{name}"
	cached_token = frappe.cache.get_value(cache_key)
	if cached_token:
		return cached_token

	# 1. Search existing folder
	list_url = f"{LARK_BASE_URL}/drive/v1/files?folder_token={parent_token}"
	payload = _lark_request("GET", list_url, token=token)
	if payload:
		items = payload.get("data", {}).get("files", [])
		for item in items:
			if item.get("name") == name and item.get("type") == "folder":
				found_token = item.get("token")
				frappe.cache.set_value(cache_key, found_token, expires_in_sec=86400)
				return found_token

	# 2. Not found, create it
	create_url = f"{LARK_BASE_URL}/drive/v1/files/create_folder"
	body = {
		"name": name,
		"folder_token": parent_token
	}
	create_payload = _lark_request("POST", create_url, token=token, json=body)
	if create_payload:
		new_token = create_payload.get("data", {}).get("token")
		if new_token:
			frappe.cache.set_value(cache_key, new_token, expires_in_sec=86400)
			return new_token

	return parent_token


def _is_managed_lark_proxy(file_url: str | None):
	return bool(file_url and "download_lark_drive_file" in file_url)


def _replace_attachment_with_lark_proxy(file_doc, lark_file_token: str, folder_token: str, bitable_token: str | None = None):
	if not _doctype_available("Lark Drive File"):
		# If the tracking doctype is not available, we cannot create a link doc.
		# However, we still want to attempt to delete the physical file and update the File doc
		# if possible, to avoid leaving orphaned files or incorrect URLs.
		link_name = None
	else:
		# Get-or-create the Lark Drive File tracking record.
		# Previous failed attempts may have left a record with the same lark_file_token.
		existing_name = frappe.db.get_value("Lark Drive File", {"lark_file_token": lark_file_token}, "name")
		if existing_name:
			link_name = existing_name
			if bitable_token:
				frappe.db.set_value("Lark Drive File", link_name, "bitable_token", bitable_token)
		else:
			link_doc = frappe.get_doc(
				{
					"doctype": "Lark Drive File",
					"attached_to_doctype": file_doc.attached_to_doctype,
					"attached_to_name": file_doc.attached_to_name,
					"file_name": file_doc.file_name,
					"lark_file_token": lark_file_token,
					"bitable_token": bitable_token,
					"lark_folder_token": folder_token,
					"source_file": file_doc.name,
				}
			)
			link_doc.insert(ignore_permissions=True)
			link_name = link_doc.name

	proxy_url = f"/api/method/lark_integration.api.download_lark_drive_file?record={quote(link_name)}" if link_name else None

	# --- Delete the physical file from ERPNext disk first ---
	import os
	try:
		file_url = str(file_doc.file_url or "")
		# Strip absolute prefix (e.g. http://localhost:8000) to get the relative path
		for prefix in ("http://", "https://"):
			if file_url.startswith(prefix):
				file_url = "/" + file_url.split("/", 3)[-1]
				break

		if not file_url.startswith("http"):
			physical_path = None
			try:
				physical_path = file_doc.get_full_path()
			except Exception:
				if file_url.startswith("/private/files/"):
					physical_path = frappe.get_site_path("private", "files", os.path.basename(file_url))
				elif file_url.startswith("/files/"):
					physical_path = frappe.get_site_path("public", "files", os.path.basename(file_url))
			if physical_path and os.path.isfile(physical_path):
				os.remove(physical_path)
	except Exception:
		frappe.log_error(
			title=f"Lark Drive: failed to delete physical file: {file_doc.name}",
			message=frappe.get_traceback(),
		)

	# Patch the File doc URL in-place via raw SQL — most reliable, bypasses all validators.
	try:
		# is_remote_file is only available in newer ERPNext/Frappe versions.
		# Check if it exists before trying to update it.
		set_clause = "file_url=%s, is_private=0, file_size=0"
		params = [proxy_url]
		
		if frappe.get_meta("File").has_field("is_remote_file"):
			set_clause += ", is_remote_file=1"
		
		params.append(file_doc.name)
		
		sql = f"UPDATE `tabFile` SET {set_clause} WHERE name=%s"
		frappe.db.sql(sql, tuple(params))
		frappe.db.commit()
		frappe.log_error(title="Lark SQL Patch Success", message=f"SQL: {sql} | Params: {params}")
	except Exception:
		frappe.log_error(
			title=f"Lark Drive: failed to update file_url for: {file_doc.name}",
			message=frappe.get_traceback(),
		)


def sync_doc_attachments_to_lark_drive(doc, token: str, config: dict):
	if not config.get("drive_upload_enabled") or not config.get("drive_folder_token"):
		return

	# Explicitly skip Drive upload if the document's sync mode forbids it.
	mapping = _get_sync_mapping(doc.doctype)
	if mapping:
		sync_mode = mapping.get("attachment_sync_mode", "Both")
		if sync_mode in ("Base Only", "None"):
			return

	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_folder": 0},
		fields=["name"],
	)
	for row in files:
		try:
			file_doc = frappe.get_doc("File", row.name)
			if _is_managed_lark_proxy(file_doc.file_url):
				continue
			# Skip external http URLs but allow local absolute URLs (e.g. http://localhost:8000/private/...)
			# that are leftovers from previous failed proxy attempts — those need to be reprocessed.
			file_url_str = str(file_doc.file_url or "")
			if file_url_str.startswith("http"):
				# Allow local absolute private file URLs (broken from old code)
				import re as _re
				if not _re.match(r'https?://[^/]*/private/files/', file_url_str) and not _re.match(r'https?://[^/]*/files/', file_url_str):
					continue

			content = file_doc.get_content()
			if not content:
				continue

			b_token = None
			if sync_mode in ("Base Only", "Both"):
				b_token = upload_attachment_to_bitable(file_doc.file_name, content, token, mapping["app_token"], reference_doctype=doc.doctype, reference_name=doc.name)

			drive_enabled = config.get("drive_upload_enabled") and config.get("drive_folder_token")
			
			lark_file_token = None
			effective_folder_token = None
			if drive_enabled and sync_mode in ("Drive Only", "Both"):
				# Organization: use DocType/Year/Month subfolders
				creation = get_datetime(doc.creation or frappe.utils.now_datetime())
				path_parts = [
					doc.doctype,
					str(creation.year),
					creation.strftime("%B") # e.g., "March"
				]
				effective_folder_token = _get_or_create_nested_folder(path_parts, config["drive_folder_token"], token)
				
				lark_file_token = upload_to_lark_drive(file_doc.file_name, content, token, effective_folder_token, reference_doctype=doc.doctype, reference_name=doc.name)
			
			if not lark_file_token and b_token and sync_mode == "Base Only":
				# Generate dummy token to bypass constraints for Base Only where no drive token exists
				lark_file_token = f"base_only_{frappe.generate_hash()}"
				effective_folder_token = ""

			if lark_file_token and (b_token or sync_mode in ("Drive Only", "Both")):
				if config.get("replace_erpnext_files_after_upload", True) and sync_mode != "Base Only":
					_replace_attachment_with_lark_proxy(file_doc, lark_file_token, effective_folder_token, bitable_token=b_token)
				elif sync_mode == "Base Only":
					# DO NOT proxy the file via frappe URL for Base Only, but DO save tracking.
					if not frappe.db.exists("Lark Drive File", {"lark_file_token": lark_file_token}):
						frappe.get_doc({
							"doctype": "Lark Drive File",
							"attached_to_doctype": file_doc.attached_to_doctype,
							"attached_to_name": file_doc.attached_to_name,
							"file_name": file_doc.file_name,
							"lark_file_token": lark_file_token,
							"bitable_token": b_token,
							"lark_folder_token": "",
							"source_file": file_doc.name
						}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Lark Drive upload failed: {doc.doctype} {doc.name}", message=frappe.get_traceback())


def handle_file_delete(doc, method=None):
	"""Hook for File on_trash: enqueues background deletion."""
	links = frappe.get_all(
		"Lark Drive File",
		filters={"source_file": doc.name},
		fields=["name", "lark_file_token"]
	)

	if not links:
		return

	frappe.enqueue(
		"lark_integration.api._delete_lark_file_job",
		links=[l.as_dict() for l in links],
		parent_doctype=doc.attached_to_doctype,
		parent_name=doc.attached_to_name,
		queue="long",
		enqueue_after_commit=True
	)


def _delete_lark_file_job(links, parent_doctype=None, parent_name=None):
	"""Background job to delete files from Lark Drive."""
	token = get_lark_token()
	if not token:
		return

	for link in links:
		try:
			# 2. Delete from Lark Drive
			# Endpoint: DELETE /drive/v1/files/:file_token?type=file
			delete_url = f"{LARK_BASE_URL}/drive/v1/files/{link['lark_file_token']}"
			_lark_request("DELETE", delete_url, token=token, params={"type": "file"}, reference_doctype=parent_doctype, reference_name=parent_name)
			
			# 3. Delete the tracking record itself
			frappe.db.delete("Lark Drive File", {"name": link['name']})
			frappe.db.commit()
		except Exception:
			frappe.log_error(title=f"Failed to delete Lark file {link.get('name')}", message=frappe.get_traceback())


@frappe.whitelist()
def download_lark_drive_file(record: str):
	frappe.log_error(title="Lark Download Attempt", message=f"Attempting download for record: {record} by user {frappe.session.user}")
	if not _doctype_available("Lark Drive File"):
		frappe.throw("Lark Drive File DocType is not available")

	link_doc = frappe.get_doc("Lark Drive File", record, ignore_permissions=True)

	# Check permission: user must have read access on the parent document.
	# If the parent doctype/name are missing, fall back to checking the Lark Drive File doc itself.
	if link_doc.attached_to_doctype and link_doc.attached_to_name:
		if not frappe.has_permission(link_doc.attached_to_doctype, "read", link_doc.attached_to_name):
			frappe.throw("Not permitted", frappe.PermissionError)
	elif not frappe.has_permission("Lark Drive File", "read", link_doc.name):
		frappe.throw("Not permitted", frappe.PermissionError)

	token = get_lark_token()
	if not token:
		frappe.throw("Lark token unavailable")

	config = _get_config()
	# Switched from 'medias' to 'files' endpoint as per Lark documentation for drive files
	url = f"{LARK_BASE_URL}/drive/v1/files/{link_doc.lark_file_token}/download"
	
	try:
		response = SESSION.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=config["request_timeout"])
		if response.status_code != 200:
			error_payload = {}
			try:
				error_payload = response.json()
			except Exception:
				error_payload = {"raw": response.text}
			
			_log_api_error(f"Lark download failed for {link_doc.lark_file_token}: {response.status_code}", error_payload)
			
			if response.status_code == 403:
				frappe.throw(f"Forbidden: Lark API returned 403 for file {link_doc.lark_file_token}. Check app permissions for Drive.")
			
		response.raise_for_status()
	except requests.exceptions.HTTPError as e:
		frappe.throw(f"Lark Download Error: {e}")
	except Exception as e:
		frappe.log_error(title="Lark Download Exception", message=frappe.get_traceback())
		frappe.throw(f"An unexpected error occurred during Lark download: {e}")
	import mimetypes
	frappe.local.response.filename = link_doc.file_name
	frappe.local.response.filecontent = response.content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"
	frappe.local.response.content_type = mimetypes.guess_type(link_doc.file_name)[0] or "application/octet-stream"


@frappe.whitelist()



def _sync_linked_references(references: Iterable):
	for ref in references or []:
		# Support both reference_doctype (Payment Entry) and reference_type (Journal Entry)
		ref_type = getattr(ref, "reference_doctype", None) or getattr(ref, "reference_type", None)
		ref_name = getattr(ref, "reference_name", None)
		
		# Fallback to dict-like access if needed
		if not ref_type and isinstance(ref, dict):
			ref_type = ref.get("reference_doctype") or ref.get("reference_type")
		if not ref_name and isinstance(ref, dict):
			ref_name = ref.get("reference_name")
		
		if ref_type and ref_name:
			log_msg = f"Enqueuing linked sync: {ref_type} {ref_name}"
			frappe.log_error(title="Lark Reference Sync Triggered", message=log_msg)
			_enqueue_sync_for_reference(ref_type, ref_name)


# --- CANCELLATION & BACKGROUND HANDLERS ---
def handle_cancel(doc, handler=None):
	"""Hook for Document on_cancel. Enqueues background sync."""
	frappe.enqueue(
		"lark_integration.api._handle_cancel_job",
		doctype=doc.doctype,
		doc_name=doc.name,
		queue="long",
		enqueue_after_commit=True
	)


def _handle_cancel_job(doctype, doc_name):
	"""Background job to update Lark status to Cancelled."""
	try:
		doc = frappe.get_doc(doctype, doc_name)
		# Update linked references BEFORE checking if this doc is mapped (crucial for Payment/Journal Entry)
		if hasattr(doc, "references") and doc.references:
			_sync_linked_references(doc.references)
		elif hasattr(doc, "accounts") and doc.accounts:
			_sync_linked_references(doc.accounts)

		token = get_lark_token()
		config = _get_config()
		mapping = _get_sync_mapping(doc.doctype)
		if not token or not mapping:
			return

		upsert_lark_record(
			mapping["main_table_id"],
			mapping["key_field"],
			doc.name,
			{"Status": "Cancelled"},
			token,
			mapping["app_token"],
		)
	except Exception:
		frappe.log_error(title=f"Lark Cancel Fail: {doc.name}", message=frappe.get_traceback())


def _parse_notification_emails(raw_value: str | None):
	if not raw_value:
		return []
	return [email.strip() for email in raw_value.split(",") if email.strip()]


def _weekday_index(label: str | None):
	day_map = {
		"Monday": 0,
		"Tuesday": 1,
		"Wednesday": 2,
		"Thursday": 3,
		"Friday": 4,
		"Saturday": 5,
		"Sunday": 6,
	}
	return day_map.get(label or "Sunday", 6)


def _is_backup_due(settings, now_dt: datetime):
	last_backup = get_datetime(settings.last_backup_on) if settings.last_backup_on else None
	if not last_backup:
		return True

	frequency = settings.backup_frequency or "Daily"
	if frequency == "Hourly":
		interval = max(_safe_int(settings.backup_interval_hours, 24), 1)
		# Add a 10-minute buffer to account for minor scheduler drift
		return now_dt >= (last_backup + timedelta(hours=interval, minutes=-10))

	backup_time = settings.backup_time or dt_time(hour=2)
	target_time = get_datetime(f"{now_dt.date()} {backup_time}")

	if frequency == "Daily":
		return now_dt >= target_time and last_backup.date() < now_dt.date()

	if frequency == "Weekly":
		target_weekday = _weekday_index(settings.backup_weekday)
		return (
			now_dt.weekday() == target_weekday
			and now_dt >= target_time
			and (now_dt - last_backup) >= timedelta(days=6)
		)

	return False


def _notify_backup_status(settings, success=True, error_message=None):
	if success and not settings.send_email_on_success:
		return
	if not success and not settings.notify_on_backup_failure:
		return

	recipients = _parse_notification_emails(settings.backup_notification_emails)
	if not recipients:
		return

	subject = f"[{frappe.local.site}] Lark Integration backup {'succeeded' if success else 'failed'}"
	message = "Backup was completed successfully." if success else f"Backup failed with error: {error_message}"

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		now=True,
	)


@frappe.whitelist()
def take_instant_backup():
	"""Manually triggered backup from UI. Enqueues to background worker to avoid timeout."""
	settings = _get_settings_doc()
	if not settings:
		frappe.throw("Lark Integration Settings not found")

	from frappe.utils.background_jobs import enqueue
	enqueue(
		"lark_integration.api._run_instant_backup",
		queue="long",
		timeout=3600,
		is_async=True,
	)
	return {"status": "queued"}


def _run_instant_backup():
	"""Background job: runs the actual backup and updates status fields."""
	import frappe as _frappe
	settings = _get_settings_doc()
	if not settings:
		return

	_publish_backup_progress(5, "Initializing backup...")
	start_time = time.time()
	try:
		total_size_bytes = _run_erpnext_backup(settings, publish_progress=True)
		end_time = time.time()
		duration_sec = int(end_time - start_time)
		duration_str = f"{duration_sec // 60}m {duration_sec % 60}s" if duration_sec >= 60 else f"{duration_sec}s"
		size_mb = total_size_bytes / (1024 * 1024)
		size_str = f"{size_mb:.2f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"
		_update_backup_status(settings, "Success", size=size_str, duration=duration_str)
		_notify_backup_status(settings, success=True)
		_publish_backup_progress(100, f"Backup completed successfully! ({size_str})")
	except Exception as exc:
		error_message = str(exc)
		_update_backup_status(settings, "Failed", error_message)
		_notify_backup_status(settings, success=False, error_message=error_message)
		_publish_backup_progress(100, f"Backup failed: {error_message}")
		frappe.log_error(title="Lark Instant Backup Failed", message=frappe.get_traceback())


def _publish_backup_progress(percent, message):
	"""Helper to publish progress to the UI via realtime and standard progress bar."""
	frappe.publish_realtime("lark_backup_progress", {"percent": percent, "message": message})
	frappe.publish_progress(percent, title="Lark Backup", description=message)


def _run_erpnext_backup(settings, publish_progress=False):
	if publish_progress:
		_publish_backup_progress(10, "Executing bench backup (this may take time)...")

	site_name = settings.backup_site or frappe.local.site
	cmd = ["bench", "--site", site_name, "backup"]
	if settings.backup_files:
		cmd.append("--with-files")

	result = subprocess.run(
		cmd,
		capture_output=True,
		text=True,
		check=False,
		timeout=3600,
	)
	if result.returncode != 0:
		raise RuntimeError((result.stderr or result.stdout or "Unknown backup failure").strip())
	
	if publish_progress:
		_publish_backup_progress(40, "Parsing backup paths...")

	# Parse backup paths from output
	backup_paths = []
	for line in result.stdout.splitlines():
		if ":" in line and "./" in line:
			# Split by first colon and take the path part
			parts = line.split(":", 1)
			if len(parts) > 1:
				# Path part might contain the file size at the end, so split by space
				path = parts[1].strip().split()[0]
				if path.startswith("./"):
					# Convert to absolute path relative to sites directory
					abs_path = os.path.join(frappe.get_site_path(), "..", path[2:])
					backup_paths.append(os.path.abspath(abs_path))
	
	if not backup_paths:
		frappe.log_error(title="Lark backup parsing failure", message=f"Full output:\n{result.stdout}")
		raise RuntimeError("Could not identify backup file paths from bench output")

	# Calculate total size
	total_size_bytes = sum(os.path.getsize(p) for p in backup_paths if os.path.exists(p))

	_upload_backups_to_lark(settings, backup_paths, publish_progress=publish_progress)
	_apply_backup_retention(settings, publish_progress=publish_progress)
	
	return total_size_bytes


def _upload_backups_to_lark(settings, backup_paths, publish_progress=False):
	if not settings.backup_lark_folder:
		return

	token = get_lark_token()
	if not token:
		return

	total = len(backup_paths)
	for i, path in enumerate(backup_paths):
		if not os.path.exists(path):
			continue
		
		if publish_progress:
			base_name = os.path.basename(path)
			progress_val = 40 + int((i / total) * 40)
			_publish_backup_progress(progress_val, f"Uploading {base_name} to Lark Drive...")

		with open(path, "rb") as f:
			content = f.read()
			token_res = upload_to_lark_drive(os.path.basename(path), content, token, settings.backup_lark_folder)
			if not token_res:
				# Raising an error here will be caught by the caller (_run_instant_backup or run_backup_scheduler)
				# which correctly updates the backup status to "Failed"
				raise RuntimeError(f"Failed to upload {os.path.basename(path)} to Lark Drive. Check Lark API Logs for details.")


def _apply_backup_retention(settings, publish_progress=False):
	if not settings.backup_lark_folder or not settings.backup_limit or settings.backup_limit <= 0:
		return

	if publish_progress:
		_publish_backup_progress(90, "Applying retention limits...")

	token = get_lark_token()
	if not token:
		return

	# List files in folder
	list_url = f"{LARK_BASE_URL}/drive/v1/files"
	res = _lark_request("GET", list_url, token=token, params={"folder_token": settings.backup_lark_folder})
	
	if not res or "data" not in res or "files" not in res.get("data", {}):
		return

	files = res["data"]["files"]
	
	# Group files by backup timestamp (e.g., 20260313_014820)
	runs = {}
	for f in files:
		name = f.get("name", "")
		if "-" in name:
			timestamp = name.split("-")[0]
			if timestamp not in runs:
				runs[timestamp] = []
			runs[timestamp].append(f)

	sorted_timestamps = sorted(runs.keys(), reverse=True)

	if len(sorted_timestamps) > settings.backup_limit:
		to_delete_runs = sorted_timestamps[settings.backup_limit:]
		files_to_delete = []
		for ts in to_delete_runs:
			files_to_delete.extend(runs[ts])

		total_del = len(files_to_delete)
		for j, f in enumerate(files_to_delete):
			if publish_progress:
				del_progress = 90 + int((j / total_del) * 10)
				frappe.publish_progress(del_progress, title="Lark Backup", description=f"Removing old backup {f.get('name')}...")
				
			delete_url = f"{LARK_BASE_URL}/drive/v1/files/{f['token']}"
			_lark_request("DELETE", delete_url, token=token, params={"type": f["type"]})


def _update_backup_status(settings, status: str, error: str | None = None, size: str | None = None, duration: str | None = None):
	settings.last_backup_on = get_datetime()
	settings.last_backup_status = status
	settings.last_backup_error = error or ""
	if size:
		settings.last_backup_size = size
	if duration:
		settings.last_backup_duration = duration
	settings.save(ignore_permissions=True, ignore_version=True)


def sync_overdue_documents():
	"""Re-sync all Overdue documents to Lark (handles background status changes)."""
	if not _doctype_available("Lark Sync Document"):
		return

	mappings = frappe.get_all("Lark Sync Document", filters={"enabled": 1}, fields=["document_type"])
	for m in mappings:
		# Check if the doctype has a 'status' field and any are 'Overdue'
		meta = frappe.get_meta(m.document_type)
		if not meta.has_field("status"):
			continue
			
		overdue_docs = frappe.get_all(
			m.document_type,
			filters={"status": "Overdue", "docstatus": 1},
			fields=["name"]
		)
		
		for d in overdue_docs:
			# Re-sync to ensure Lark matches
			frappe.enqueue(
				"lark_integration.api.sync_universal",
				doctype=m.document_type,
				doc_name=d.name,
				queue="long"
			)


def run_backup_scheduler():
	settings = _get_settings_doc()
	if not settings or not settings.backup_enabled:
		return

	now_dt = get_datetime()
	if not _is_backup_due(settings, now_dt):
		return

	start_time = time.time()
	try:
		total_size_bytes = _run_erpnext_backup(settings)
		end_time = time.time()
		duration_sec = int(end_time - start_time)
		
		# Format metrics
		duration_str = f"{duration_sec // 60}m {duration_sec % 60}s" if duration_sec >= 60 else f"{duration_sec}s"
		size_mb = total_size_bytes / (1024 * 1024)
		size_str = f"{size_mb:.2f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"

		_update_backup_status(settings, "Success", size=size_str, duration=duration_str)
		_notify_backup_status(settings, success=True)
	except Exception as exc:
		error_message = str(exc)
		_update_backup_status(settings, "Failed", error_message)
		_notify_backup_status(settings, success=False, error_message=error_message)
		frappe.log_error(title="Lark Scheduled Backup Failed", message=frappe.get_traceback())


def _enqueue_sync_for_reference(reference_type: str, reference_name: str):
	if not reference_type or not reference_name:
		return
	
	mapping_name = frappe.db.get_value("Lark Sync Document", {"document_type": reference_type, "enabled": 1}, "name")
	if mapping_name:
		frappe.enqueue(
			"lark_integration.api.sync_universal",
			doctype=reference_type,
			doc_name=reference_name,
			queue="long",
			enqueue_after_commit=True
		)


def enqueue_journal_entry_sync(doc, handler=None):
	"""Trigger linked invoice sync when Journal Entries are submitted or cancelled."""
	synced_docs = set()
	for row in doc.get("accounts", []):
		if not (row.reference_type and row.reference_name):
			continue
		ref_key = (row.reference_type, row.reference_name)
		if ref_key in synced_docs:
			continue
		_enqueue_sync_for_reference(row.reference_type, row.reference_name)
		synced_docs.add(ref_key)


# --- HOOKS WRAPPERS ---
def handle_universal_update(doc, handler=None):
	# Sync on save ONLY if the document type is not submittable.
	# Submittable documents will be synced via on_submit.
	if not getattr(doc.meta, "is_submittable", 0):
		frappe.enqueue("lark_integration.api.sync_universal", doctype=doc.doctype, doc_name=doc.name, queue="long", enqueue_after_commit=True)


def enqueue_universal_sync(doc, handler=None):
	if doc.docstatus == 1:
		frappe.enqueue("lark_integration.api.sync_universal", doctype=doc.doctype, doc_name=doc.name, queue="long", enqueue_after_commit=True)


def handle_file_attach(doc, handler=None):
	"""Upload a newly attached file to Lark Drive for ANY parent doctype."""
	if not doc.attached_to_doctype or not doc.attached_to_name:
		return

	# Skip Lark proxy files (already uploaded) and external HTTP URLs
	if _is_managed_lark_proxy(doc.file_url):
		return
	if doc.file_url and str(doc.file_url).startswith("http"):
		return

	config = _get_config()
	if not config.get("drive_upload_enabled") or not config.get("drive_folder_token"):
		return

	frappe.enqueue(
		"lark_integration.api._upload_single_file_to_drive",
		file_name=doc.name,
		queue="long",
		enqueue_after_commit=True,
	)


def _upload_single_file_to_drive(file_name: str):
	"""Background job: upload a specific File doc to Lark Drive."""
	try:
		file_doc = frappe.get_doc("File", file_name)

		# Guard: skip if already a proxy or external URL
		if _is_managed_lark_proxy(file_doc.file_url):
			return
		if file_doc.file_url and str(file_doc.file_url).startswith("http"):
			return

		config = _get_config()

		mapping = None
		sync_mode = "Both"
		if file_doc.attached_to_doctype:
			mapping = _get_sync_mapping(file_doc.attached_to_doctype)
			if mapping:
				sync_mode = mapping.get("attachment_sync_mode", "Both")

		if sync_mode == "None":
			return

		drive_enabled = config.get("drive_upload_enabled") and config.get("drive_folder_token")
		if not drive_enabled and sync_mode == "Drive Only":
			return

		token = get_lark_token()
		if not token:
			return

		content = file_doc.get_content()
		if not content:
			return

		b_token = None
		if mapping and sync_mode in ("Base Only", "Both"):
			app_token = mapping.get("app_token")
			if app_token:
				b_token = upload_attachment_to_bitable(file_doc.file_name, content, token, app_token, reference_doctype=file_doc.attached_to_doctype, reference_name=file_doc.attached_to_name)

		lark_file_token = None
		effective_folder_token = None
		if drive_enabled and sync_mode in ("Drive Only", "Both"):
			# Organization: use DocType/Year/Month subfolders
			creation = get_datetime(file_doc.creation or frappe.utils.now_datetime())
			path_parts = [
				str(file_doc.attached_to_doctype or "Unknown"),
				str(creation.year),
				creation.strftime("%B")
			]
			effective_folder_token = _get_or_create_nested_folder(path_parts, config["drive_folder_token"], token)
			lark_file_token = upload_to_lark_drive(file_doc.file_name, content, token, effective_folder_token, reference_doctype=file_doc.attached_to_doctype, reference_name=file_doc.attached_to_name)

		if not lark_file_token and b_token and sync_mode == "Base Only":
			lark_file_token = f"base_only_{frappe.generate_hash()}"
			effective_folder_token = ""

		if lark_file_token and (b_token or sync_mode in ("Drive Only", "Both")):
			if config.get("replace_erpnext_files_after_upload", True) and sync_mode != "Base Only":
				_replace_attachment_with_lark_proxy(file_doc, lark_file_token, effective_folder_token, bitable_token=b_token)
			elif sync_mode == "Base Only":
				if not frappe.db.exists("Lark Drive File", {"lark_file_token": lark_file_token}):
					frappe.get_doc({
						"doctype": "Lark Drive File",
						"attached_to_doctype": file_doc.attached_to_doctype,
						"attached_to_name": file_doc.attached_to_name,
						"file_name": file_doc.file_name,
						"lark_file_token": lark_file_token,
						"bitable_token": b_token,
						"lark_folder_token": "",
						"source_file": file_doc.name
					}).insert(ignore_permissions=True)

		# Sync Bitable to include the new attachment
		if file_doc.attached_to_doctype and file_doc.attached_to_name:
			frappe.enqueue(
				"lark_integration.api.sync_universal",
				doctype=file_doc.attached_to_doctype,
				doc_name=file_doc.attached_to_name,
				queue="long"
			)
	except Exception:
		frappe.log_error(title=f"Lark Drive file attach upload failed: {file_name}", message=frappe.get_traceback())


def enqueue_universal_sync(doc, handler=None):
	if doc.docstatus == 1:
		frappe.enqueue("lark_integration.api.sync_universal", doctype=doc.doctype, doc_name=doc.name, queue="long", enqueue_after_commit=True)


def sync_universal(doctype, doc_name, **kwargs):
	try:
		doc = frappe.get_doc(doctype, doc_name)
		
		# Always sync linked references regardless of whether THIS doc is mapped to Bitable
		# (e.g. Payment Entry is usually NOT mapped, but it must trigger Invoice sync)
		if hasattr(doc, "references") and doc.references:
			_sync_linked_references(doc.references)
		elif hasattr(doc, "accounts") and doc.accounts:
			_sync_linked_references(doc.accounts)

		token = get_lark_token()
		config = _get_config()
		mapping = _get_sync_mapping(doctype)
		if not token or not mapping:
			return

		file_token = None
		if mapping.get("sync_attachments"):
			file_token = upload_pdf_to_lark(doc, token, mapping["app_token"])

		# Ensure attachments are uploaded to Drive BEFORE generating Bitable payload
		sync_doc_attachments_to_lark_drive(doc, token, config)

		fields = _build_fields_payload(doc, mapping)
		
		# Check if we should link attachments to the Bitable record
		sync_mode = mapping.get("attachment_sync_mode", "Both")
		if sync_mode in ("Base Only", "Both"):
			# Combine PDF token and any other document attachments
			lark_attachments = _get_doc_attachment_tokens(doc)
			if file_token:
				lark_attachments.insert(0, file_token)
				
			if lark_attachments:
				fields["ERP Attachment"] = [{"file_token": t} for t in lark_attachments]

		upsert_lark_record(mapping["main_table_id"], mapping["key_field"], doc.name, fields, token, mapping["app_token"], reference_doctype=doc.doctype, reference_name=doc.name)
			
		# Sync child tables dynamically
		if not _sync_child_tables(doc, mapping, token, mapping["app_token"]):
			# If manual child table sync fails or isn't configured correctly but an items_table_id exists
			# we attempt a generic fallback using the `items` property if it exists, otherwise do nothing
			if mapping.get("items_table_id") and hasattr(doc, "items") and doc.items:
				item_records = [
					{
						"fields": {
							mapping["key_field"]: str(doc.name),
							"Date": _ts_ms(doc.get("posting_date") or doc.creation),
							"Item": str(getattr(i, "item_name", getattr(i, "item_code", ""))),
							"Qty": float(getattr(i, "qty", 0.0)),
							"Rate": float(getattr(i, "rate", 0.0)),
							"Amount": float(getattr(i, "amount", 0.0)),
						}
					}
					for i in doc.items
				]
				clear_and_sync_items(
					mapping.get("items_table_id"),
					mapping["key_field"],
					doc.name,
					item_records,
					token,
					mapping["app_token"],
					reference_doctype=doc.doctype,
					reference_name=doc.name
				)
	except Exception:
		frappe.log_error(title=f"Lark Universal Sync Fail: {doctype} {doc_name}", message=frappe.get_traceback())


# --- BULK SYNC LOGIC ---
def bulk_sync_from_date(start_date, doctype=None):
	if isinstance(start_date, (list, tuple)):
		start_date = start_date[0]

	if doctype:
		doctypes = [doctype]
	else:
		# Sync all active mapped doctypes
		mappings = frappe.get_all("Lark Sync Document", fields=["document_type"])
		doctypes = [m.document_type for m in mappings]

	for dt in doctypes:
		try:
			docs = frappe.get_all(dt, filters={"posting_date": [">=", start_date], "docstatus": 1}, pluck="name")
			for name in docs:
				frappe.enqueue("lark_integration.api.sync_universal", doctype=dt, doc_name=name, queue="long")
		except Exception:
			# Handle case where doctype doesn't have posting_date
			pass

@frappe.whitelist()
def repair_lark_proxy_files():
	"""One-shot utility: fix all File docs with broken localhost-absolute file_url
	by finding their corresponding Lark Drive File record and patching the file_url."""
	frappe.only_for("System Manager")
	if not _doctype_available("Lark Drive File"):
		frappe.throw("Lark Drive File DocType is not available")

	fixed = 0
	lark_files = frappe.get_all("Lark Drive File", fields=["name", "source_file", "lark_file_token"])
	
	has_remote_file_field = frappe.get_meta("File").has_field("is_remote_file")
	
	for lf in lark_files:
		if not lf.source_file:
			continue
		if not frappe.db.exists("File", lf.source_file):
			continue
		current_url = frappe.db.get_value("File", lf.source_file, "file_url") or ""
		# Skip if already a proxy URL
		if "download_lark_drive_file" in current_url:
			continue
			
		proxy_url = f"/api/method/lark_integration.api.download_lark_drive_file?record={quote(lf.name)}"
		
		# Patch the File doc URL in-place via raw SQL
		set_clause = "file_url=%s, is_private=0"
		params = [proxy_url]
		if has_remote_file_field:
			set_clause += ", is_remote_file=1"
		
		params.append(lf.source_file)
		
		frappe.db.sql(
			f"UPDATE `tabFile` SET {set_clause} WHERE name=%s",
			tuple(params),
		)
		fixed += 1
		
	frappe.db.commit()
	return {"fixed": fixed}


# --- TODO SYNC LOGIC (LARK TASK V2) ---

def sync_todo_to_lark(doc, method=None):
	"""Hook for ToDo on_update. Enqueues background sync."""
	if frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	if getattr(doc, "_sync_from_lark", False):
		return

	frappe.enqueue(
		"lark_integration.api._sync_todo_record_to_lark",
		doc_name=doc.name,
		queue="long",
		enqueue_after_commit=True
	)


def _sync_todo_record_to_lark(doc_name):
	"""Background job to sync a specific ToDo to Lark."""
	try:
		doc = frappe.get_doc("ToDo", doc_name)
	except frappe.DoesNotExistError:
		return

	# Avoid loops from pull_lark_tasks
	if getattr(doc, "_sync_from_lark", False):
		return

	try:
		settings = _get_settings_doc()
		if not settings or not settings.todo_sync_enabled:
			return

		token = get_lark_token()
		if not token:
			return

		# Prepare Payload
		summary = doc.description or "Untitled Task"
		if len(summary) > 100:
			summary = summary[:97] + "..."
		
		from frappe.utils import strip_html
		desc = strip_html(doc.description or "")

		payload = {
			"summary": summary,
			"description": desc,
			"obj_edit_configs": {
				"resource_type": "task",
			}
		}

		if settings.sync_todo_references and doc.reference_type and doc.reference_name:
			site_url = frappe.utils.get_url()
			ref_url = f"{site_url}/app/{doc.reference_type.lower().replace(' ', '-')}/{doc.reference_name}"
			payload["origin"] = {
				"platform_i18n_name": "{\"en_us\":\"ERPNext\"}",
				"url": ref_url
			}

		if doc.status == "Closed":
			from datetime import datetime, timezone
			payload["completed_at"] = str(int(datetime.now(timezone.utc).timestamp() * 1000))
		else:
			payload["completed_at"] = "0"

		# Due Date
		if doc.date:
			from datetime import datetime, timezone, timedelta
			from frappe.utils import get_system_timezone as _get_sys_tz
			date_str = str(doc.date).split(" ")[0]
			is_all_day = True
			
			try:
				import pytz
				system_tz = _get_sys_tz()
				local_tz = pytz.timezone(system_tz)

				if doc.get("lark_due_time"):
					time_val = doc.lark_due_time
					if hasattr(time_val, 'seconds'):
						total_secs = int(time_val.total_seconds())
						h, rem = divmod(total_secs, 3600)
						m, s = divmod(rem, 60)
						time_str = f"{h:02d}:{m:02d}:{s:02d}"
					else:
						time_str = str(time_val).split('.')[0]
					
					local_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
					local_dt = local_tz.localize(local_dt)
					utc_dt = local_dt.astimezone(timezone.utc)
					ts = int(utc_dt.timestamp() * 1000)
					is_all_day = False
				else:
					local_dt = datetime.strptime(date_str, "%Y-%m-%d")
					local_dt = local_tz.localize(local_dt)
					utc_dt = local_dt.astimezone(timezone.utc)
					ts = int(utc_dt.timestamp() * 1000)
			except Exception:
				from datetime import datetime as _dt, timezone as _tz
				ts = int(_dt.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_tz.utc).timestamp() * 1000)
			
			payload["due"] = {"timestamp": str(ts), "is_all_day": is_all_day}
		else:
			payload["due"] = {"timestamp": "0", "is_all_day": False}

		# Assignee
		target_user = doc.allocated_to or doc.assigned_by or doc.owner
		assignee_lark_id = frappe.db.get_value("User", target_user, "lark_user_id")
		if assignee_lark_id:
			payload["members"] = [{"id": assignee_lark_id, "role": "assignee", "type": "user"}]

		url = f"{LARK_BASE_URL}/task/v2/tasks"
		
		if doc.lark_task_guid:
			# UPDATE
			update_url = f"{url}/{doc.lark_task_guid}"
			update_fields = ["summary", "description", "completed_at", "due", "origin"]
			final_payload = {"update_fields": update_fields, "task": payload}
			
			_lark_request("PATCH", update_url, token=token, json=final_payload, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)

			# Assignees
			if payload.get("members"):
				_lark_request("POST", f"{update_url}/add_members", token=token, json={"members": payload["members"]}, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
			else:
				detail_res = _lark_request("GET", update_url, token=token, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
				if detail_res and "data" in detail_res and "task" in detail_res["data"]:
					existing_members = detail_res["data"]["task"].get("members", [])
					if existing_members:
						_lark_request("POST", f"{update_url}/remove_members", token=token, json={"member_ids": [m["id"] for m in existing_members]}, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)

			# Reminders
			if doc.get("lark_remind_at_due"):
				label = doc.get("lark_reminder_offset") or settings.default_reminder_offset or "At due time"
				offset = REMINDER_LABEL_TO_MINUTES.get(str(label), 0)
				
				detail_res = _lark_request("GET", update_url, token=token, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
				if detail_res and "data" in detail_res and "task" in detail_res["data"]:
					existing_rems = detail_res["data"]["task"].get("reminders", [])
					if existing_rems:
						_lark_request("POST", f"{update_url}/remove_reminders", token=token, json={"reminder_ids": [r["id"] for r in existing_rems]}, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
				
				try:
					_lark_request("POST", f"{update_url}/add_reminders", token=token, json={"reminders": [{"relative_fire_minute": offset}]}, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
				except Exception:
					frappe.log_error(title="Lark Integration: Failed to add reminders on update", message=frappe.get_traceback())
			else:
				# Clear reminders if unticked
				try:
					detail_res = _lark_request("GET", update_url, token=token, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
					if detail_res and "data" in detail_res and "task" in detail_res["data"]:
						existing_rems = detail_res["data"]["task"].get("reminders", [])
						if existing_rems:
							_lark_request("POST", f"{update_url}/remove_reminders", token=token, json={"reminder_ids": [r["id"] for r in existing_rems]}, params={"user_id_type": "user_id"}, reference_doctype="ToDo", reference_name=doc.name)
				except Exception:
					frappe.log_error(title="Lark Integration: Failed to clear reminders on untick", message=frappe.get_traceback())

			# Task List linkage
			if doc.lark_task_list:
				new_list_guid = frappe.db.get_value("Lark Task List", doc.lark_task_list, "lark_list_guid")
				if new_list_guid:
					before_save = doc.get_doc_before_save()
					old_list = before_save.lark_task_list if before_save else None
					if old_list and old_list != doc.lark_task_list:
						old_list_guid = frappe.db.get_value("Lark Task List", old_list, "lark_list_guid")
						if old_list_guid:
							_lark_request("POST", f"{url}/{doc.lark_task_guid}/remove_tasklist", token=token, json={"tasklist_guid": old_list_guid})
					_lark_request("POST", f"{url}/{doc.lark_task_guid}/add_tasklist", token=token, json={"tasklist_guid": new_list_guid})

			# Priority
			if settings.todo_priority_mapping:
				_sync_lark_task_priority(doc.lark_task_guid, doc.priority, token)

		else:
			# CREATE
			res = _lark_request("POST", url, token=token, json=payload, params={"user_id_type": "user_id"})
			if res and res.get("data", {}).get("task", {}).get("guid"):
				guid = res["data"]["task"]["guid"]
				doc.db_set("lark_task_guid", guid, update_modified=False)
				
				if doc.lark_task_list:
					list_guid = frappe.db.get_value("Lark Task List", doc.lark_task_list, "lark_list_guid")
					if list_guid:
						_lark_request("POST", f"{url}/{guid}/add_tasklist", token=token, json={"tasklist_guid": list_guid})
						if settings.todo_priority_mapping and doc.priority:
							_sync_lark_task_priority(guid, doc.priority, token)

				if doc.get("lark_remind_at_due"):
					label = doc.get("lark_reminder_offset") or settings.default_reminder_offset or "At due time"
					offset = REMINDER_LABEL_TO_MINUTES.get(str(label), 0)
					_lark_request("POST", f"{url}/{guid}/add_reminders", token=token, json={"reminders": [{"relative_fire_minute": offset}]}, params={"user_id_type": "user_id"})

	except Exception:
		# Fail gracefully to allow ToDo to save in ERPNext even if Lark is down
		frappe.log_error(title="Lark Integration: sync_todo_to_lark crash", message=frappe.get_traceback())



def delete_lark_task(doc, method=None):
	"""Hook for ToDo on_trash. Enqueues background deletion."""
	if not doc.lark_task_guid:
		return

	frappe.enqueue(
		"lark_integration.api._delete_lark_task_job",
		guid=doc.lark_task_guid,
		queue="long",
		enqueue_after_commit=True
	)


def _delete_lark_task_job(guid):
	"""Background job to delete a Lark task."""
	token = get_lark_token()
	if not token:
		return

	delete_url = f"{LARK_BASE_URL}/task/v2/tasks/{guid}"
	_lark_request("DELETE", delete_url, token=token)


def _should_sync_periodically(settings, sync_type):
	"""Check if the selected interval has passed since the last sync."""
	last_sync_field = "last_todo_sync_on" if sync_type == "ToDo" else "last_calendar_sync_on"
	interval_field = "todo_sync_interval" if sync_type == "ToDo" else "calendar_sync_interval"
	
	last_sync = settings.get(last_sync_field)
	interval_label = settings.get(interval_field) or "15 Minutes"
	
	if not last_sync:
		return True
	
	# Map labels to minutes
	interval_map = {
		"5 Minutes": 5,
		"15 Minutes": 15,
		"30 Minutes": 30,
		"Hourly": 60
	}
	interval_mins = interval_map.get(interval_label, 15)
	
	from frappe.utils import get_datetime, now_datetime
	diff = (now_datetime() - get_datetime(last_sync)).total_seconds() / 60
	return diff >= (interval_mins - 1) # 1 min buffer


@frappe.whitelist()
def pull_lark_tasks(publish_progress=False):
	"""Scheduled task to pull updates from Lark Tasks back to ERPNext ToDo."""
	settings = frappe.get_single("Lark Integration Settings")
	if not settings.todo_sync_enabled or settings.todo_sync_method != "Periodic":
		return
	
	if not _should_sync_periodically(settings, "ToDo"):
		return

	if publish_progress:
		frappe.publish_progress(10, title="ToDo Sync", description="Fetching tasks from Lark...")

	token = get_lark_token()
	if not token:
		return

	# Sync task list deletions: clean up ERPNext lists that no longer exist in Lark
	try:
		_sync_lark_task_lists_with_erp(token)
	except Exception:
		pass  # Don't break the sync if list cleanup fails

	# 1. Collect GUIDs from all mapped Task Lists
	all_guids = set()
	task_lists = frappe.get_all("Lark Task List", filters={"lark_list_guid": ("!=", "")}, fields=["name", "lark_list_guid"])
	for tl in task_lists:
		tl_guid = tl.lark_list_guid
		tl_url = f"{LARK_BASE_URL}/task/v2/tasklists/{tl_guid}/tasks"
		tl_res = _lark_request("GET", tl_url, token=token, params={
			"user_id_type": "user_id", 
			"page_size": 50
		})
		if tl_res and "data" in tl_res and "items" in tl_res.get("data", {}):
			for item in tl_res["data"]["items"]:
				if item.get("guid"):
					all_guids.add(item["guid"])

	# 2. Collect GUIDs from existing ToDos
	existing_guids = frappe.db.get_all("ToDo", filters={"lark_task_guid": ("!=", "")}, pluck="lark_task_guid")
	all_guids.update(eg for eg in existing_guids if eg)

	# 3. Fetch full details for EVERY guid and sync
	total = len(all_guids)
	synced = 0
	
	for i, guid in enumerate(all_guids):
		if publish_progress:
			prog = 10 + int((i / total) * 80)
			frappe.publish_progress(prog, title="ToDo Sync", description=f"Syncing task {i+1}/{total}...")

		# Fetch full detail
		detail_url = f"{LARK_BASE_URL}/task/v2/tasks/{guid}"
		detail_res = _lark_request("GET", detail_url, token=token, params={"user_id_type": "user_id"})
		if not detail_res or "data" not in detail_res or "task" not in detail_res["data"]:
			continue
			
		item = detail_res["data"]["task"]
		summary = item.get("summary") or "(No Summary)"

		# Find/Create ToDo
		todo_name = frappe.db.get_value("ToDo", {"lark_task_guid": guid}, "name")
		todo = None
		if todo_name:
			todo = frappe.get_doc("ToDo", todo_name)
		else:
			# Pre-calculate values to avoid Frappe defaults during insert()
			lark_due = item.get("due")
			due_date, due_time = None, None
			if lark_due:
				try:
					lark_ts = float(lark_due.get("timestamp", 0)) / 1000
					if lark_ts > 0:
						from datetime import datetime, timezone
						import pytz
						from frappe.utils import get_system_timezone as _sys_tz
						# Convert UTC ms → local datetime
						utc_dt = datetime.fromtimestamp(lark_ts, tz=timezone.utc)
						local_tz = pytz.timezone(_sys_tz())
						
						local_dt = utc_dt.astimezone(local_tz)
						due_date = local_dt.date()
						due_time = local_dt.strftime("%H:%M:%S") if not lark_due.get("is_all_day") else None
				except Exception:
					pass

			# Create new ToDo
			todo = frappe.get_doc({
				"doctype": "ToDo",
				"description": summary,
				"lark_task_guid": guid,
				"status": "Closed" if item.get("completed_at") not in (None, "0", 0) else "Open",
				"date": due_date,
				"lark_due_time": due_time
			})
			todo._sync_from_lark = True # Prevents sync back to Lark
			todo.insert(ignore_permissions=True)
			
			# Force NULL if no date/time was provided (avoids Frappe's defaults: date=Today, time=Now)
			reset_fields = {}
			if due_date is None:
				reset_fields["date"] = None
			if due_time is None:
				reset_fields["lark_due_time"] = None
			
			if reset_fields:
				frappe.db.set_value("ToDo", todo.name, reset_fields, update_modified=False)
				if "date" in reset_fields: todo.date = None
				if "lark_due_time" in reset_fields: todo.lark_due_time = None

			todo_name = todo.name
			synced += 1

		# Run heavy sync logic (Priority, Members, Checklists, etc.)
		if _sync_todo_from_lark_task(todo, item, settings, token):
			# _sync_todo_from_lark_task handles its own db_sets
			if todo_name: # Already counted if new
				synced += 1

	settings.last_todo_sync_on = get_datetime()
	settings.db_set("last_todo_sync_on", settings.last_todo_sync_on)

	if publish_progress:
		frappe.publish_progress(100, title="ToDo Sync", description=f"Sync complete. Synced {synced} tasks.")


# --- CALENDAR SYNC LOGIC (LARK CALENDAR V4) ---

def map_erp_recurrence_to_lark(doc):
	"""Converts ERPNext Event recurrence to RFC 5545 RRULE string."""
	if not doc.repeat_this_event:
		return None

	freq_map = {
		"Daily": "DAILY",
		"Weekly": "WEEKLY",
		"Monthly": "MONTHLY",
		"Yearly": "YEARLY"
	}
	
	freq = freq_map.get(doc.repeat_on, "DAILY")
	rrule = f"FREQ={freq}"
	
	if freq == "WEEKLY":
		days = []
		for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
			if doc.get(day):
				days.append(day[:2].upper())
		if days:
			rrule += f";BYDAY={','.join(days)}"
	
	if doc.repeat_till:
		until = get_datetime(doc.repeat_till).strftime("%Y%m%dT%H%M%SZ")
		rrule += f";UNTIL={until}"
		
	return rrule


def sync_event_attendees(calendar_id, event_id, erp_participants, token):
	"""Pushes ERPNext participants to Lark Event attendees."""
	if not erp_participants:
		return

	attendees = []
	for p in erp_participants:
		if p.reference_doctype == "User":
			lark_user_id = frappe.db.get_value("User", p.reference_docname, "lark_user_id")
			if lark_user_id:
				attendees.append({
					"type": "user",
					"attendee_id": lark_user_id
				})
	
	if not attendees:
		return

	url = f"{LARK_BASE_URL}/calendar/v4/calendars/{calendar_id}/events/{event_id}/attendees"
	_lark_request("POST", url, token=token, json={"attendees": attendees})


def sync_event_to_lark(doc, method=None):
	"""Hook for Event on_update. Enqueues background sync."""
	if frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_import:
		return
	if getattr(doc, "_sync_from_lark", False):
		return

	frappe.enqueue(
		"lark_integration.api._sync_event_record_to_lark",
		doc_name=doc.name,
		queue="long",
		enqueue_after_commit=True
	)


def _sync_event_record_to_lark(doc_name):
	"""Background job to sync a specific Event to Lark."""
	try:
		doc = frappe.get_doc("Event", doc_name)
	except frappe.DoesNotExistError:
		return

	if getattr(doc, "_sync_from_lark", False):
		return

	settings = frappe.get_single("Lark Integration Settings")
	if not settings.calendar_sync_enabled:
		return

	token = get_lark_token()
	if not token:
		return

	# 1. Determine the Calendar ID
	calendar_id = None
	
	if doc.lark_calendar:
		calendar_id = frappe.db.get_value("Lark Calendar", doc.lark_calendar, "lark_calendar_id")
	
	if not calendar_id:
		# Fallback to the owner's primary calendar
		calendar_id = frappe.db.get_value("User", doc.owner, "lark_user_id")

	if not calendar_id:
		return

	# Prepare payload
	payload = {
		"summary": doc.subject or "(No Subject)",
		"description": doc.description or "",
		"start_time": {
			"timestamp": str(int(get_datetime(doc.starts_on).timestamp())),
		},
		"end_time": {
			"timestamp": str(int(get_datetime(doc.ends_on or doc.starts_on).timestamp())),
		}
	}
	
	if doc.location:
		payload["location"] = {"name": doc.location}

	# Advanced Feature: Recurrence
	recurrence = map_erp_recurrence_to_lark(doc)
	if recurrence:
		payload["recurrence"] = recurrence

	# Advanced Feature: Video Conferencing (Lark Meeting)
	if doc.add_lark_meeting:
		payload["vchat"] = {"vc_type": "vc"}

	url = f"{LARK_BASE_URL}/calendar/v4/calendars/{calendar_id}/events"
	
	res = None
	if doc.lark_event_id:
		# Update
		update_url = f"{url}/{doc.lark_event_id}"
		res = _lark_request("PATCH", update_url, token=token, json=payload, reference_doctype="Event", reference_name=doc.name)
	else:
		# Create
		res = _lark_request("POST", url, token=token, json=payload, reference_doctype="Event", reference_name=doc.name)
		if res and res.get("data", {}).get("event", {}).get("event_id"):
			event_id = res["data"]["event"]["event_id"]
			doc.db_set("lark_event_id", event_id, update_modified=False)
			doc.db_set("lark_calendar_id", calendar_id, update_modified=False)
			
			# Save meeting URL if generated
			vchat = res["data"]["event"].get("vchat", {})
			if vchat.get("meeting_url"):
				doc.db_set("lark_meeting_url", vchat["meeting_url"], update_modified=False)

	# Advanced Feature: Attendee Sync
	if res and not res.get("error"):
		event_id = doc.lark_event_id or res.get("data", {}).get("event", {}).get("event_id")
		if event_id:
			sync_event_attendees(calendar_id, event_id, doc.event_participants, token)


def delete_lark_event(doc, method=None):
	"""Hook for Event on_trash. Enqueues background deletion."""
	if not doc.lark_event_id or not doc.lark_calendar_id:
		return

	frappe.enqueue(
		"lark_integration.api._delete_lark_event_job",
		event_id=doc.lark_event_id,
		calendar_id=doc.lark_calendar_id,
		queue="long",
		enqueue_after_commit=True
	)


def _delete_lark_event_job(event_id, calendar_id):
	"""Background job to delete a Lark event."""
	token = get_lark_token()
	if not token:
		return

	delete_url = f"{LARK_BASE_URL}/calendar/v4/calendars/{calendar_id}/events/{event_id}"
	_lark_request("DELETE", delete_url, token=token)


@frappe.whitelist()
def pull_lark_calendar_events(publish_progress=False):
	"""Scheduled task to pull updates from Lark Calendars back to ERPNext Event."""
	settings = frappe.get_single("Lark Integration Settings")
	if not settings.calendar_sync_enabled or settings.calendar_sync_method != "Periodic":
		return

	if not _should_sync_periodically(settings, "Calendar"):
		return

	token = get_lark_token()
	if not token:
		return

	# 1. Identify all mapped calendars in ERPNext
	# This includes both primary user calendars and custom shared calendars
	calendars = frappe.get_all("Lark Calendar", fields=["name", "lark_calendar_id", "owner"])
	
	# Also include Users who don't have a Lark Calendar record yet but have a lark_user_id (legacy/simple setup)
	legacy_users = frappe.get_all("User", filters={
		"lark_user_id": ["not in", (None, "")],
		"name": ["not in", [c.owner for c in calendars]]
	}, fields=["name", "lark_user_id"])
	
	# Combine into a unique set of calendar IDs to check
	sync_targets = []
	for c in calendars:
		if c.lark_calendar_id:
			sync_targets.append({
				"id": c.lark_calendar_id, 
				"label": c.name, 
				"docname": c.name, 
				"sync_token": frappe.db.get_value("Lark Calendar", c.name, "sync_token")
			})
	for u in legacy_users:
		sync_targets.append({
			"id": u.lark_user_id, 
			"label": f"Primary ({u.name})", 
			"user": u.name, 
			"sync_token": None
		})

	active_target_count = len(sync_targets)
	synced_total = 0

	for idx, target in enumerate(sync_targets):
		calendar_id = target["id"]
		
		if publish_progress:
			prog = 10 + int((idx / active_target_count) * 80)
			frappe.publish_progress(prog, title="Calendar Sync", description=f"Checking {target['label']}...")

		# Use sync_token for incremental sync
		list_url = f"{LARK_BASE_URL}/calendar/v4/calendars/{calendar_id}/events"
		params = {}
		if target.get("sync_token"):
			params["sync_token"] = target["sync_token"]
		
		res = _lark_request("GET", list_url, token=token, params=params)
		
		if not res or "data" not in res:
			continue

		data = res["data"]
		items = data.get("items", [])
		
		# Update sync_token for next time
		if data.get("sync_token"):
			if target.get("docname"):
				frappe.db.set_value("Lark Calendar", target["docname"], "sync_token", data["sync_token"])
			# Note: legacy user user sync token isn't stored currently as User doc doesn't have it

		for item in items:
			event_id = item.get("event_id")
			if not event_id:
				continue

			# Find existing
			event_name = frappe.db.get_value("Event", {"lark_event_id": event_id}, "name")
			
			# If cancelled, handle deletion/closing
			if item.get("status") == "cancelled":
				if event_name:
					frappe.db.set_value("Event", event_name, "status", "Closed")
					synced_total += 1
				continue

			if not event_name:
				continue
			
			event = frappe.get_doc("Event", event_name)
			
			lark_start = int(item["start_time"].get("timestamp", 0))
			lark_end = int(item["end_time"].get("timestamp", 0))
			
			erp_start = int(get_datetime(event.starts_on).timestamp())
			erp_end = int(get_datetime(event.ends_on).timestamp()) if event.ends_on else erp_start

			changed = False
			if abs(lark_start - erp_start) > 60: # Threshold for drift
				event.starts_on = get_datetime(lark_start)
				changed = True
			
			if abs(lark_end - erp_end) > 60:
				event.ends_on = get_datetime(lark_end)
				changed = True

			if item.get("summary") and item["summary"] != event.subject:
				event.subject = item["summary"]
				changed = True

			if changed:
				event.db_set("starts_on", event.starts_on, update_modified=True)
				event.db_set("ends_on", event.ends_on, update_modified=True)
				event.db_set("subject", event.subject, update_modified=True)
				event.db_set("_sync_from_lark", True, update_modified=False)
				synced_total += 1

	settings.last_calendar_sync_on = get_datetime()
	settings.save(ignore_permissions=True)

	if publish_progress:
		frappe.publish_progress(100, title="Calendar Sync", description=f"Sync complete. Updated {synced_total} events.")


@frappe.whitelist()
def create_lark_calendar(doc_name):
	"""Manually create a calendar in Lark for an ERPNext Lark Calendar record."""
	doc = frappe.get_doc("Lark Calendar", doc_name)
	if doc.lark_calendar_id:
		frappe.throw("This calendar is already linked to Lark.")

	token = get_lark_token()
	if not token:
		return

	payload = {
		"summary": doc.calendar_name,
		"description": "Created from ERPNext Lark Integration"
	}
	
	url = f"{LARK_BASE_URL}/calendar/v4/calendars"
	res = _lark_request("POST", url, token=token, json=payload)
	
	if res and res.get("data", {}).get("calendar", {}).get("calendar_id"):
		calendar_id = res["data"]["calendar"]["calendar_id"]
		doc.db_set("lark_calendar_id", calendar_id)
		return {"status": "success", "calendar_id": calendar_id}
	
	return {"status": "error", "message": "Failed to create calendar in Lark."}


@frappe.whitelist()
def create_lark_task_list(doc_name):
	"""Manually create a task list in Lark for an ERPNext Lark Task List record."""
	doc = frappe.get_doc("Lark Task List", doc_name)
	if doc.lark_list_guid:
		frappe.throw("This task list is already linked to Lark.")

	token = get_lark_token()
	if not token:
		return

	payload = {
		"name": doc.list_name
	}
	
	url = f"{LARK_BASE_URL}/task/v2/tasklists"
	res = _lark_request("POST", url, token=token, json=payload)
	
	if res and res.get("data", {}).get("tasklist", {}).get("guid"):
		guid = res["data"]["tasklist"]["guid"]
		doc.db_set("lark_list_guid", guid)
		
		# Step 2: Add creator as member (Editor) so it's visible in Lark UI
		users_to_add = set(filter(None, [doc.owner, frappe.session.user]))
		for user_name in users_to_add:
			lark_id = frappe.db.get_value("User", user_name, "lark_user_id")
			if lark_id:
				members_url = f"{url}/{guid}/add_members"
				_lark_request("POST", members_url, token=token, json={
					"members": [{"id": lark_id, "type": "user", "role": "editor"}]
				}, params={"user_id_type": "user_id"})

		return {"status": "success", "lark_list_guid": guid}
	
	return {"status": "error", "message": "Failed to create task list in Lark."}


@frappe.whitelist()
def fetch_lark_task_lists():
	"""Fetch all task lists from Lark into ERPNext."""
	token = get_lark_token()
	if not token:
		return

	url = f"{LARK_BASE_URL}/task/v2/tasklists"
	res = _lark_request("GET", url, token=token)
	
	if not res or "data" not in res or "items" not in res.get("data", {}):
		return {"status": "success", "imported": 0}

	items = res["data"]["items"]
	
	counts = 0
	for item in items:
		guid = item.get("guid")
		name = item.get("name")
		if not guid or not name:
			continue
			
		# Search by GUID first
		existing = frappe.db.get_value("Lark Task List", {"lark_list_guid": guid}, ["name", "list_name"], as_dict=True)
		doc = None
		if not existing:
			# If GUID not found, check if a list with the same name exists without a GUID
			if frappe.db.exists("Lark Task List", name):
				doc = frappe.get_doc("Lark Task List", name)
				if not doc.lark_list_guid:
					doc.db_set("lark_list_guid", guid)
					counts += 1
			else:
				# Truly new list
				doc = frappe.get_doc({
					"doctype": "Lark Task List",
					"list_name": name,
					"lark_list_guid": guid,
					"owner": frappe.session.user
				}).insert(ignore_permissions=True)
				counts += 1
		else:
			doc = frappe.get_doc("Lark Task List", existing.name)
			# Update name if changed in Lark
			if existing.list_name != name:
				doc.db_set("list_name", name)
				counts += 1
		
		# Ensure current user is a member if not already (for visibility)
		current_lark_id = frappe.db.get_value("User", frappe.session.user, "lark_user_id")
		if current_lark_id:
			members_url = f"{url}/{guid}/add_members"
			_lark_request("POST", members_url, token=token, json={
				"members": [{"id": current_lark_id, "type": "user", "role": "editor"}]
			}, params={"user_id_type": "user_id"})
			
	return {"status": "success", "imported": counts}


def delete_lark_task_list(doc, method=None):
	"""Called on_trash for Lark Task List. Deletes the task list from Lark."""
	guid = doc.lark_list_guid
	if not guid:
		return
	token = get_lark_token()
	if not token:
		return
	try:
		url = f"{LARK_BASE_URL}/task/v2/tasklists/{guid}"
		_lark_request("DELETE", url, token=token, params={"user_id_type": "user_id"})
	except Exception:
		pass  # Don't block deletion in ERPNext if Lark call fails
	# Also clear the clear_lark_cache
	clear_lark_cache()


@frappe.whitelist()
def delete_lark_task_list_from_lark(list_name):
	"""Whitelisted: Delete a Lark Task List by ERPNext name, also deletes from Lark."""
	doc = frappe.get_doc("Lark Task List", list_name)
	delete_lark_task_list(doc)
	frappe.delete_doc("Lark Task List", list_name, ignore_permissions=True)
	return {"status": "success"}


@frappe.whitelist()
def link_lark_task_list(doc_name, guid):
	"""Link an ERPNext Lark Task List record to an existing Lark task list by GUID.
	Also adds the current user as an editor member so the app can see the list's tasks.
	"""
	guid = (guid or "").strip()
	if not guid:
		return {"status": "error", "msg": "GUID is required"}

	token = get_lark_token()
	if not token:
		return {"status": "error", "msg": "No Lark token"}

	# Update the ERPNext record with the GUID
	frappe.db.set_value("Lark Task List", doc_name, "lark_list_guid", guid)
	frappe.db.commit()

	# Add the current user as an editor on the Lark task list so the app can access it
	current_lark_id = frappe.db.get_value("User", frappe.session.user, "lark_user_id")
	if current_lark_id:
		url = f"{LARK_BASE_URL}/task/v2/tasklists/{guid}/add_members"
		_lark_request("POST", url, token=token, json={
			"members": [{"id": current_lark_id, "type": "user", "role": "editor"}]
		}, params={"user_id_type": "user_id"})

	clear_lark_cache()
	return {"status": "success"}


def _sync_lark_task_lists_with_erp(token):
	"""Bidirectional sync of Lark Task Lists:
	- Creates ERPNext records for new Lark task lists
	- Deletes ERPNext records for task lists deleted in Lark
	"""
	url = f"{LARK_BASE_URL}/task/v2/tasklists"
	res = _lark_request("GET", url, token=token)
	if not res or "data" not in res:
		return  # Don't modify anything if API call fails

	lark_items = res.get("data", {}).get("items", [])
	lark_guid_map = {item.get("guid"): item for item in lark_items if item.get("guid")}

	# --- Handle NEW lists (in Lark but not in ERPNext) ---
	current_lark_id = frappe.db.get_value("User", frappe.session.user, "lark_user_id")
	for guid, item in lark_guid_map.items():
		name = item.get("name") or guid
		existing = frappe.db.get_value("Lark Task List", {"lark_list_guid": guid}, "name")
		if not existing:
			# Create a new Lark Task List record in ERPNext
			try:
				new_doc = frappe.get_doc({
					"doctype": "Lark Task List",
					"list_name": name,
					"lark_list_guid": guid,
				}).insert(ignore_permissions=True)
				# Add current user as editor for visibility
				if current_lark_id:
					_lark_request("POST", f"{url}/{guid}/add_members", token=token, json={
						"members": [{"id": current_lark_id, "type": "user", "role": "editor"}]
					}, params={"user_id_type": "user_id"})
			except Exception:
				pass
		else:
			# Update name if changed in Lark
			stored_name = frappe.db.get_value("Lark Task List", existing, "list_name")
			if stored_name != name:
				frappe.db.set_value("Lark Task List", existing, "list_name", name, update_modified=False)

	# --- Handle DELETED lists (in ERPNext but no longer in Lark) ---
	erp_lists = frappe.get_all("Lark Task List", fields=["name", "lark_list_guid"])
	for erp_list in erp_lists:
		guid = erp_list.lark_list_guid
		if not guid:
			continue
		if guid not in lark_guid_map:
			# Task list was deleted in Lark → clean up ERPNext
			frappe.db.set_value("ToDo", {"lark_task_list": erp_list.name}, "lark_task_list", None, update_modified=False)
			frappe.delete_doc("Lark Task List", erp_list.name, ignore_permissions=True, force=True)

	frappe.db.commit()

def _get_lark_custom_fields(list_guid, token):
	"""Helper to fetch and cache custom field definitions for a task list."""
	if not list_guid:
		return []
		
	if not hasattr(frappe.local, "_lark_list_fields"):
		frappe.local._lark_list_fields = {}
	
	if list_guid not in frappe.local._lark_list_fields:
		res = _lark_request("GET", f"{LARK_BASE_URL}/task/v2/custom_fields", token=token, params={
			"resource_type": "tasklist",
			"resource_id": list_guid
		})
		if res and "data" in res:
			frappe.local._lark_list_fields[list_guid] = res.get("data", {}).get("items", [])
		else:
			frappe.local._lark_list_fields[list_guid] = []
	
	return frappe.local._lark_list_fields[list_guid]

def _sync_lark_task_priority(task_guid, priority_name, token):
	"""Helper to sync Priority custom field to a Lark task."""
	if not task_guid:
		return

	# Fetch task detail to get its current list
	url = f"{LARK_BASE_URL}/task/v2/tasks/{task_guid}"
	res = _lark_request("GET", url, token=token, params={"user_id_type": "user_id"})
	
	if res and "data" in res and "task" in res["data"]:
		tasklists = res["data"]["task"].get("tasklists", [])
		if tasklists:
			list_guid = tasklists[0].get("tasklist_guid")
			fields = _get_lark_custom_fields(list_guid, token)
			prio_field = next((f for f in fields if f.get("name") == "Priority"), None)
			
			if prio_field:
				options = prio_field.get("single_select_setting", {}).get("options", [])
				opt = next((o for o in options if o.get("name") == priority_name), None)
				
				if opt:
					payload = {
						"update_fields": ["custom_fields"],
						"task": {
							"custom_fields": [{
								"guid": prio_field["guid"],
								"single_select_value": opt["guid"]
							}]
						}
					}
					_lark_request("PATCH", url, token=token, json=payload, params={"user_id_type": "user_id"})
				elif not priority_name:
					# Clear the custom field
					payload = {
						"update_fields": ["custom_fields"],
						"task": {
							"custom_fields": [{
								"guid": prio_field["guid"],
								"single_select_value": "" # Empty string to clear single select
							}]
						}
					}
					_lark_request("PATCH", url, token=token, json=payload, params={"user_id_type": "user_id"})

@frappe.whitelist(allow_guest=True)
def lark_webhook():
	"""Webhook endpoint for Lark Events."""
	data = frappe.request.get_json()
	if not data:
		return {"status": "error", "message": "No data"}
	
	# 1. URL Verification
	if data.get("type") == "url_verification":
		return {"challenge": data.get("challenge")}
	
	# 2. Dispatch all other events to background job for performance
	frappe.enqueue(
		"lark_integration.api._handle_lark_webhook_event",
		data=data,
		queue="long",
		enqueue_after_commit=True
	)
	return {"status": "success", "message": "Event enqueued"}


def _handle_lark_webhook_event(data):
	"""Background job to process Lark Webhook events."""
	header = data.get("header", {})
	event_type = header.get("event_type")
	event = data.get("event", {})
	
	settings = frappe.get_single("Lark Integration Settings")
	token = get_lark_token()
	
	# --- TASK EVENTS ---
	if event_type in ("task.task.created_v2", "task.task.updated_v2"):
		if settings.todo_sync_method != "Webhook":
			return
		task_guid = event.get("task", {}).get("guid")
		if task_guid:
			# Fetch latest detail
			detail_url = f"{LARK_BASE_URL}/task/v2/tasks/{task_guid}"
			res = _lark_request("GET", detail_url, token=token, params={"user_id_type": "user_id"})
			if res and "data" in res and "task" in res["data"]:
				item = res["data"]["task"]
				todo_name = frappe.db.get_value("ToDo", {"lark_task_guid": task_guid}, "name")
				if todo_name:
					todo = frappe.get_doc("ToDo", todo_name)
					_sync_todo_from_lark_task(todo, item, settings, token)
				else:
					# Create new ToDo
					todo = frappe.new_doc("ToDo")
					todo.lark_task_guid = task_guid
					# Initial sync
					_sync_todo_from_lark_task(todo, item, settings, token)
					# For new docs, ensure they are inserted first since helper uses db_set
					todo.insert(ignore_permissions=True)
					# Re-save to apply all fields that might have been handled by helper's db_set logic
					# Actually, better to just call save() for new docs.
					todo.save(ignore_permissions=True)
				frappe.db.commit()
	
	elif event_type == "task.task.deleted_v2":
		if settings.todo_sync_method != "Webhook":
			return
		task_guid = event.get("task", {}).get("guid")
		if task_guid:
			todo_name = frappe.db.get_value("ToDo", {"lark_task_guid": task_guid}, "name")
			if todo_name:
				frappe.delete_doc("ToDo", todo_name, ignore_permissions=True)

	# --- CALENDAR EVENTS ---
	elif event_type in ("calendar.calendar_event.created_v4", "calendar.calendar_event.updated_v4"):
		if settings.calendar_sync_method != "Webhook":
			return
		calendar_id = event.get("calendar_id")
		event_id = event.get("calendar_event", {}).get("calendar_event_id")
		if calendar_id and event_id:
			# Fetch latest detail
			detail_url = f"{LARK_BASE_URL}/calendar/v4/calendars/{calendar_id}/events/{event_id}"
			res = _lark_request("GET", detail_url, token=token)
			if res and "data" in res and "event" in res["data"]:
				item = res["data"]["event"]
				event_name = frappe.db.get_value("Event", {"lark_event_id": event_id}, "name")
				if event_name:
					erp_event = frappe.get_doc("Event", event_name)
					_sync_event_from_lark_detail(erp_event, item, settings, token)
				else:
					# Create new Event
					erp_event = frappe.new_doc("Event")
					erp_event.lark_event_id = event_id
					erp_event.lark_calendar_id = calendar_id
					_sync_event_from_lark_detail(erp_event, item, settings, token)
					erp_event.insert(ignore_permissions=True)
				frappe.db.commit()

	elif event_type == "calendar.calendar_event.deleted_v4":
		if settings.calendar_sync_method != "Webhook":
			return
		event_id = event.get("calendar_event", {}).get("calendar_event_id")
		if event_id:
			event_name = frappe.db.get_value("Event", {"lark_event_id": event_id}, "name")
			if event_name:
				frappe.delete_doc("Event", event_name, ignore_permissions=True)
	

	return {"status": "ignored"}


def _sync_event_from_lark_detail(erp_event, item, settings, token):
	"""Helper to sync properties from a Lark calendar event detail to an ERPNext Event."""
	changed = False
	erp_event._sync_from_lark = True
	
	try:
		# Times are UTC timestamps in seconds
		lark_start = int(item["start_time"].get("timestamp", 0))
		lark_end = int(item["end_time"].get("timestamp", 0))
		
		# Threshold for drift (60 seconds)
		if erp_event.starts_on:
			erp_start = int(get_datetime(erp_event.starts_on).timestamp())
			if abs(lark_start - erp_start) > 60:
				erp_event.starts_on = get_datetime(lark_start)
				changed = True
		else:
			erp_event.starts_on = get_datetime(lark_start)
			changed = True
		
		if erp_event.ends_on:
			erp_end = int(get_datetime(erp_event.ends_on).timestamp())
			if abs(lark_end - erp_end) > 60:
				erp_event.ends_on = get_datetime(lark_end)
				changed = True
		else:
			erp_event.ends_on = get_datetime(lark_end)
			changed = True

		if item.get("summary") and item["summary"] != erp_event.subject:
			erp_event.subject = item["summary"]
			changed = True

		if changed:
			erp_event.save(ignore_permissions=True)
			frappe.db.commit()
	except Exception:
		frappe.log_error(title="Lark Webhook Event Sync Fail", message=frappe.get_traceback())

def _sync_todo_from_lark_task(todo, item, settings, token):
	"""Helper to sync properties from a Lark task object to an ERPNext ToDo."""
	changed = False
	guid = item.get("guid")
	# 1. Avoid loops and ERPNext defaults for Time fields
	todo._sync_from_lark = True
	
	# Ensure todo has custom fields loaded
	if not hasattr(todo, "lark_task_guid"):
		todo = frappe.get_doc("ToDo", todo.name)
		todo._sync_from_lark = True

	# Status
	lark_completed = item.get("completed_at") not in (None, "0", 0)
	erp_completed = todo.status == "Closed"
	if lark_completed != erp_completed:
		todo.status = "Closed" if lark_completed else "Open"
		changed = True

	# Description
	lark_summary = item.get("summary") or ""
	if lark_summary and str(todo.description or "") != str(lark_summary):
		todo.description = lark_summary
		changed = True

	# Due Date & Time
	# Lark timestamps are UTC milliseconds. We convert to LOCAL time for display in ERPNext.
	lark_due = item.get("due")
	if lark_due:
		try:
			lark_ts = float(lark_due.get("timestamp", 0)) / 1000
			is_all_day = lark_due.get("is_all_day", False)
			if lark_ts > 0:
				from datetime import datetime, timezone
				import pytz
				# Convert UTC ms → local datetime
				utc_dt = datetime.fromtimestamp(lark_ts, tz=timezone.utc)
				system_tz = frappe.utils.get_system_timezone() if hasattr(frappe, 'utils') else "Asia/Karachi"
				local_tz = pytz.timezone(system_tz)
				local_dt = utc_dt.astimezone(local_tz)
				
				new_date = local_dt.date()
				new_time = local_dt.strftime("%H:%M:%S") if not is_all_day else None
				
				if str(todo.date or "") != str(new_date):
					todo.date = new_date
					changed = True
				
				# Normalize time strings to HH:MM:SS for comparison (strip microseconds)
				erp_time = str(todo.get("lark_due_time") or "").split('.')[0]
				lark_time = str(new_time or "").split('.')[0]
				if erp_time != lark_time:
					todo.lark_due_time = new_time
					changed = True
		except Exception:
			pass
	else:
		# Clear if blank in Lark
		if todo.date or todo.lark_due_time:
			todo.date = None
			todo.lark_due_time = None
			changed = True

	# Priority
	if settings.todo_priority_mapping:
		custom_fields = item.get("custom_fields", [])
		prio_field = next((f for f in custom_fields if f.get("name") == "Priority"), None)
		if prio_field:
			opt_guid = prio_field.get("single_select_value")
			if opt_guid:
				tasklists = item.get("tasklists", [])
				if tasklists:
					list_guid = tasklists[0].get("tasklist_guid")
					fields = _get_lark_custom_fields(list_guid, token)
					f_def = next((f for f in fields if f.get("guid") == prio_field["guid"]), None)
					if f_def:
						options = f_def.get("single_select_setting", {}).get("options", [])
						opt = next((o for o in options if o.get("guid") == opt_guid), None)
						if opt and opt.get("name") and todo.priority != opt["name"]:
							todo.priority = opt["name"]
							changed = True
			else:
				# Clear if blank in Lark
				if todo.priority:
					todo.priority = None
					changed = True

	# Owner (Assignee)
	members = item.get("members", [])
	assignee = next((m for m in members if m.get("role") == "assignee"), None)
	if assignee:
		lark_user_id = assignee.get("id")
		erp_user = frappe.db.get_value("User", {"lark_user_id": lark_user_id}, "name")
		if erp_user and todo.allocated_to != erp_user:
			todo.allocated_to = erp_user
			changed = True
	else:
		# Clear if blank in Lark
		if todo.allocated_to:
			todo.allocated_to = None
			changed = True

	# Task List
	lark_lists = item.get("tasklists", [])
	if lark_lists:
		lark_list_id = lark_lists[0].get("tasklist_guid")
		erp_list_name = frappe.db.get_value("Lark Task List", {"lark_list_guid": lark_list_id}, "name")
		if erp_list_name and todo.lark_task_list != erp_list_name:
			todo.lark_task_list = erp_list_name
			changed = True

	# Reminders
	reminders = item.get("reminders", [])
	if guid and not reminders: # The List API does not include them
		task_detail_url = f"{LARK_BASE_URL}/task/v2/tasks/{guid}"
		detail_res = _lark_request("GET", task_detail_url, token=token, params={"user_id_type": "user_id"})
		if detail_res and "data" in detail_res and "task" in detail_res["data"]:
			reminders = detail_res["data"]["task"].get("reminders", [])

	if reminders:
		first_rem = reminders[0]
		offset_mins = first_rem.get("relative_fire_minute", 0)
		offset_label = REMINDER_MINUTES_TO_LABEL.get(int(offset_mins), str(offset_mins))
		if todo.lark_remind_at_due != 1 or str(todo.lark_reminder_offset or "") != offset_label:
			todo.lark_remind_at_due = 1
			todo.lark_reminder_offset = offset_label
			changed = True
	elif todo.lark_remind_at_due == 1:
		todo.lark_remind_at_due = 0
		# When unticked, we clear the offset or keep it as is? User said untick means none.
		# We'll set it to blank so the UI shows no value (Select field).
		todo.lark_reminder_offset = None
		changed = True

	if changed:
		todo.db_set("status", todo.status, update_modified=True)
		todo.db_set("description", todo.description, update_modified=True)
		todo.db_set("date", todo.date, update_modified=True)
		todo.db_set("lark_due_time", todo.lark_due_time, update_modified=True)
		todo.db_set("lark_remind_at_due", todo.lark_remind_at_due, update_modified=True)
		todo.db_set("lark_reminder_offset", todo.lark_reminder_offset, update_modified=True)
		if settings.todo_priority_mapping:
			todo.db_set("priority", todo.priority, update_modified=True)
		if lark_lists:
			todo.db_set("lark_task_list", todo.lark_task_list, update_modified=True)
	
	return changed




