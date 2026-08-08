"""Publish and verify the underground Church of Orra in Fogport."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os
from pathlib import Path
from typing import Any
import requests

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import headers, request, all_pages, exact
install_api_pacing()

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

def validate_manifest(document: dict[str, Any]) -> None:
    if document.get("campaign_id") != CAMPAIGN_ID or str(document.get("campaign_name","")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Manifest is not locked to Fogport 410879.")
    approval=document.get("approval",{})
    if approval.get("status")!="approved" or approval.get("approved_by")!="Daniel Davis":
        raise SystemExit("Daniel Davis approval is required.")

def upsert_post(token: str, entity_id: int, name: str, entry: str, visibility_id: int) -> dict[str, Any]:
    path=f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts"
    posts=all_pages(token,path)
    matches=[p for p in posts if str(p.get("name","")).strip().casefold()==name.strip().casefold()]
    if len(matches)>1: raise SystemExit(f"Multiple GM posts named {name!r}; refusing to guess.")
    payload={"name":name,"entry":entry,"visibility_id":visibility_id,"is_private":True}
    if matches:
        post_id=int(matches[0]["id"]); request(token,"PATCH",f"{path}/{post_id}",payload=payload)
    else:
        post_id=int(request(token,"POST",path,payload=payload).get("data",{})["id"])
    final=request(token,"GET",f"{path}/{post_id}").get("data",{})
    if (str(final.get("name",""))!=name or str(final.get("entry") or "")!=entry
        or int(final.get("visibility_id",0))!=visibility_id):
        raise SystemExit("GM-only post read-back failed.")
    return final

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("manifest",type=Path); parser.add_argument("--receipt",type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES")!="FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document=json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(document); token=os.environ["KANKA_API_TOKEN"]
    campaign=request(token,"GET",f"campaigns/{CAMPAIGN_ID}").get("data",{})
    if str(campaign.get("name","")).casefold()!=CAMPAIGN_NAME.casefold(): raise SystemExit("Kanka campaign identity lock failed.")
    locations=all_pages(token,f"campaigns/{CAMPAIGN_ID}/locations")
    fogport=exact(locations,"Fogport","location")
    if not fogport: raise SystemExit("Fogport location is missing; refusing to publish unlinked text.")
    fogport_link=f"[entity:{int(fogport['entity_id'])}|Fogport]"
    spec=document["organization"]; entry=str(spec["entry"]).replace("{{FOGPORT_LINK}}",fogport_link)
    org_path=f"campaigns/{CAMPAIGN_ID}/organisations"; organizations=all_pages(token,org_path)
    match=exact(organizations,str(spec["name"]),"organization")
    payload={"name":str(spec["name"]),"type":str(spec["type"]),"entry":entry,"is_private":bool(spec.get("is_private",False))}
    if match:
        organization_id=int(match["id"]); request(token,"PATCH",f"{org_path}/{organization_id}",payload=payload); created=False
    else:
        organization_id=int(request(token,"POST",org_path,payload=payload).get("data",{})["id"]); created=True
    final=request(token,"GET",f"{org_path}/{organization_id}").get("data",{})
    if (str(final.get("name"))!=payload["name"] or str(final.get("type"))!=payload["type"]
        or bool(final.get("is_private")) is not payload["is_private"] or str(final.get("entry") or "")!=entry):
        raise SystemExit("Church of Orra organization read-back failed.")
    entity_id=int(final["entity_id"])
    gm_spec=document["gm_post"]; gm_entry=str(gm_spec["entry"])
    gm_post=upsert_post(token,entity_id,str(gm_spec["name"]),gm_entry,int(gm_spec["visibility_id"]))
    receipt={"published":True,"campaign":CAMPAIGN_NAME,"campaign_id":CAMPAIGN_ID,"organization":final["name"],
      "organization_id":organization_id,"entity_id":entity_id,"created":created,"type":final["type"],
      "is_private":bool(final["is_private"]),"entry_verified":True,"fogport_link_verified":fogport_link in entry,
      "gm_post_id":int(gm_post["id"]),"gm_post_visibility_id":int(gm_post["visibility_id"]),
      "gm_post_verified":True,"overview_url":f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"}
    args.receipt.parent.mkdir(parents=True,exist_ok=True); args.receipt.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2))

if __name__=="__main__": main()
