"""Publish GM-only Civic Order secrets as an administrator-only Kanka post."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages,exact,request
install_api_pacing()
CID=410879
def main():
 p=argparse.ArgumentParser();p.add_argument("manifest",type=Path);p.add_argument("--receipt",required=True,type=Path);a=p.parse_args()
 if os.environ.get("KANKA_ENABLE_WRITES")!="FOGPORT_410879": raise SystemExit("Campaign write lock missing.")
 d=json.loads(a.manifest.read_text()); 
 if d.get("campaign_id")!=CID or d.get("approval",{}).get("status")!="approved": raise SystemExit("Invalid approval.")
 t=os.environ["KANKA_API_TOKEN"]; orgs=all_pages(t,f"campaigns/{CID}/organisations"); org=exact(orgs,d["organization_name"],"organization")
 if not org: raise SystemExit("The Civic Order organization is missing.")
 eid=int(org["entity_id"]); path=f"campaigns/{CID}/entities/{eid}/posts"; posts=all_pages(t,path); spec=d["post"]; matches=[x for x in posts if str(x.get("name","")).casefold()==spec["name"].casefold()]
 if len(matches)>1: raise SystemExit("Duplicate GM post; refusing to guess.")
 payload={"name":spec["name"],"entry":spec["entry"],"entity_id":eid,"visibility_id":3}
 if matches: pid=int(matches[0]["id"]); request(t,"PATCH",f"{path}/{pid}",payload=payload); created=False
 else: made=request(t,"POST",path,payload=payload).get("data",{}); pid=int(made["id"]); created=True
 final=request(t,"GET",f"{path}/{pid}").get("data",{})
 if str(final.get("name"))!=spec["name"] or str(final.get("entry") or "")!=spec["entry"] or int(final.get("visibility_id",0))!=3: raise SystemExit("GM post read-back failed.")
 r={"published":True,"created":created,"organization":d["organization_name"],"post":final["name"],"post_id":pid,"visibility_id":3,"overview_url":f"https://app.kanka.io/w/{CID}/entities/{eid}"}
 a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2))
if __name__=="__main__": main()
