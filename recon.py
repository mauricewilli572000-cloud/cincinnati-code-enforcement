import json, re
from curl_cffi import requests as cr
S = cr.Session(impersonate="chrome")
def show(tag, obj): print(f"@@{tag}@@ " + json.dumps(obj, default=str)[:9000])
r = S.get("https://cagis.org/Opendata/Quarterly_GIS_Data/Parcel_DataDictionary.txt", timeout=60); show("dict", [r.status_code, r.text[:8500]])
r = S.get("https://cagis.org/Opendata/Quarterly_GIS_Data/", timeout=60)
show("folder", [r.status_code, sorted(set(re.findall(r'href=["\']([^"\']+)["\']', r.text)))[:80]])
