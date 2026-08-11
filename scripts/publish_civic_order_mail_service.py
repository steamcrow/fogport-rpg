"""Publish and verify the Civic Order Mail Service organization."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import request, all_pages, exact
install_api_pacing()
CAMPAIGN_ID=410879
CAMPAIGN_NAME="Fogport"

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("manifest",type=Path); parser.add_argument("--receipt",type=Path,required=True); args=parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES")!="FOGPORT_410879": raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    doc=json.loads(args.manifest.read_text(encoding="utf-8"))
    if doc.get("campaign_id")!=CAMPAIGN_ID or str(doc.get("campaign_name","")).casefold()!=CAMPAIGN_NAME.casefold(): raise SystemExit("Manifest is not locked to Fogport 410879.")
    approval=doc.get("approval",{})
    if approval.get("status")!="approved" or approval.get("approved_by")!="Daniel Davis": raise SystemExit("Daniel Davis approval is required.")
    token=os.environ["KANKA_API_TOKEN"]
    campaign=request(token,"GET",f"campaigns/{CAMPAIGN_ID}").get("data",{})
    if str(campaign.get("name","")).casefold()!=CAMPAIGN_NAME.casefold(): raise SystemExit("Kanka campaign identity lock failed.")
    spec=doc["organization"]
    path=f"campaigns/{CAMPAIGN_ID}/organisations"; orgs=all_pages(token,path); match=exact(orgs,str(spec["name"]),"organization")
    payload={"name":str(spec["name"]),"type":str(spec["type"]),"entry":str(spec["entry"]),"is_private":bool(spec.get("is_private",False))}
    if match:
        oid=int(match["id"]); request(token,"PATCH",f"{path}/{oid}",payload=payload); created=False
    else:
        oid=int(request(token,"POST",path,payload=payload).get("data",{})["id"]); created=True
    final=request(token,"GET",f"{path}/{oid}").get("data",{})
    if str(final.get("name"))!=payload["name"] or str(final.get("type"))!=payload["type"] or str(final.get("entry") or "")!=payload["entry"]: raise SystemExit("Civic Order Mail Service read-back failed.")
    receipt={"published":True,"campaign":CAMPAIGN_NAME,"campaign_id":CAMPAIGN_ID,"organization":final["name"],"organization_id":oid,"entity_id":int(final["entity_id"]),"created":created,"entry_verified":True,"overview_url":f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{int(final['entity_id'])}"}
    args.receipt.parent.mkdir(parents=True,exist_ok=True); args.receipt.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8"); print(json.dumps(receipt,indent=2))
if __name__=="__main__": main()
