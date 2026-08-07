"""Publish and verify Varkesh race entry and artwork."""
from __future__ import annotations
import argparse,hashlib,json,mimetypes,os
from pathlib import Path
import requests
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages,exact,request
install_api_pacing()
CID=410879
def main():
 p=argparse.ArgumentParser();p.add_argument("proposal",type=Path);p.add_argument("--receipt",required=True,type=Path);a=p.parse_args()
 if os.environ.get("KANKA_ENABLE_WRITES")!="FOGPORT_410879": raise SystemExit("Campaign write lock missing.")
 d=json.loads(a.proposal.read_text()); c=d["campaign_id"]; ch=d["proposals"][0]; root=Path(__file__).resolve().parents[1]; img=(root/d["image_path"]).resolve()
 if c!=CID or d["approval"]["status"]!="approved" or not img.is_file() or hashlib.sha256(img.read_bytes()).hexdigest()!=d["sha256"]: raise SystemExit("Varkesh approval or image checksum failed.")
 t=os.environ["KANKA_API_TOKEN"]; path=f"campaigns/{CID}/creatures"; creatures=all_pages(t,path); match=exact(creatures,ch["name"],"creature"); payload={"name":ch["name"],"type":ch["type"],"entry":ch["entry"],"is_private":False}
 if match: rid=int(match["id"]); request(t,"PATCH",f"{path}/{rid}",payload=payload); created=False
 else: rid=int(request(t,"POST",path,payload=payload).get("data",{})["id"]); created=True
 final=request(t,"GET",f"{path}/{rid}").get("data",{})
 if str(final.get("entry") or "")!=payload["entry"]: raise SystemExit("Varkesh read-back failed.")
 eid=int(final["entity_id"]); mime=mimetypes.guess_type(img.name)[0] or "application/octet-stream"
 with img.open("rb") as stream: up=requests.post(f"https://api.kanka.io/1.0/campaigns/{CID}/entities/{eid}/image",headers={"Authorization":f"Bearer {t}","Accept":"application/json"},files={"file":(img.name,stream,mime)},timeout=120)
 if not up.ok: raise SystemExit(f"Varkesh image upload failed: {up.status_code}")
 uuid=up.json().get("data",{}).get("image",{}).get("uuid"); read=request(t,"GET",f"campaigns/{CID}/entities/{eid}/image").get("data",{}).get("image",{})
 if not uuid or read.get("uuid")!=uuid or not read.get("full") or not read.get("thumbnail"): raise SystemExit("Varkesh image read-back failed.")
 r={"published":True,"created":created,"name":final["name"],"creature_id":rid,"entity_id":eid,"image_verified":True,"overview_url":f"https://app.kanka.io/w/{CID}/entities/{eid}"}
 a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2))
if __name__=="__main__": main()
