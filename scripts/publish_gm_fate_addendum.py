"""Merge an approved Fate addendum into the approved GM guide, then publish via the exact-note writer."""
from copy import deepcopy
import hashlib, json, os, tempfile
from pathlib import Path
from scripts.publish_exact_gamemaster_guide import digest, verify_manifest, main as publish_main

BASE = Path("kanka_librarian/approved_notes/gamemaster-guide-v3.json")
ADD = Path("kanka_librarian/approved_notes/gamemaster-guide-fate-addendum.json")
LOCKS = (410879, 332976, 9626686, 1413484)

def add_digest(d):
    u=deepcopy(d); u.pop("approval",None)
    return hashlib.sha256(json.dumps(u,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def main():
    base=json.loads(BASE.read_text(encoding="utf-8")); verify_manifest(base)
    add=json.loads(ADD.read_text(encoding="utf-8"))
    if add.get("mode")!="gm-guide-section-addendum": raise SystemExit("Wrong addendum mode")
    locks=(int(add.get("campaign_id",0)),int(add.get("note_id",0)),int(add.get("entity_id",0)),int(add.get("post_id",0)))
    if locks!=LOCKS: raise SystemExit("Addendum identity lock failed")
    ap=add.get("approval",{})
    if ap.get("status")!="approved" or ap.get("document_sha256")!=add_digest(add): raise SystemExit("Addendum approval digest failed")
    sections=base["post"]["sections"]
    if any(s.get("heading")==add["section"]["heading"] for s in sections): raise SystemExit("Fate section already present")
    for i,s in enumerate(sections):
        if s.get("heading")==add["insert_after"]:
            s["body"] += add["danger_append"]
            sections.insert(i+1, add["section"])
            break
    else: raise SystemExit("Insertion heading not found")
    base["post"]["introduction"]=base["post"]["introduction"].replace("Version 2.1","Version 2.2")
    base["approval"]={"status":"approved","approved_by":ap["approved_by"],"approved_at":ap["approved_at"],"document_sha256":digest(base)}
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"merged.json"; p.write_text(json.dumps(base,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        old=os.environ.get("MANIFEST_PATH"); os.environ["MANIFEST_PATH"]=str(p)
        try: publish_main()
        finally:
            if old is None: os.environ.pop("MANIFEST_PATH",None)
            else: os.environ["MANIFEST_PATH"]=old

if __name__=="__main__": main()
