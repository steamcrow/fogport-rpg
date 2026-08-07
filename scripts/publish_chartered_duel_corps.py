"""Publish the Chartered Duel Corps and its GM-only secrets."""
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
 d=json.loads(a.manifest.read_text());t=os.environ["KANKA_API_TOKEN"]
 if d.get("campaign_id")!=CID or d.get("approval",{}).get("status")!="approved": raise SystemExit("Invalid approval.")
 orgs=all_pages(t,f"campaigns/{CID}/organisations");spec=d["organization"];match=exact(orgs,spec["name"],"organization");path=f"campaigns/{CID}/organisations";payload={k:spec[k] for k in ("name","type","entry","is_private")}
 if match: oid=int(match["id"]);request(t,"PATCH",f"{path}/{oid}",payload=payload);created=False
 else: oid=int(request(t,"POST",path,payload=payload).get("data",{})["id"]);created=True
 final=request(t,"GET",f"{path}/{oid}").get("data",{})
 if str(final.get("entry") or "")!=payload["entry"]: raise SystemExit("Organization read-back failed.")
 eid=int(final["entity_id"]);pp=f"campaigns/{CID}/entities/{eid}/posts";posts=all_pages(t,pp);ps=d["post"];pm=[x for x in posts if str(x.get("name","")).casefold()==ps["name"].casefold()]
 if len(pm)>1: raise SystemExit("Duplicate GM post; refusing to guess.")
 pld={"name":ps["name"],"entry":ps["entry"],"entity_id":eid,"visibility_id":3}
 if pm: pid=int(pm[0]["id"]);request(t,"PATCH",f"{pp}/{pid}",payload=pld);pc=False
 else: pid=int(request(t,"POST",pp,payload=pld).get("data",{})["id"]);pc=True
 post=request(t,"GET",f"{pp}/{pid}").get("data",{})
 if str(post.get("entry") or "")!=ps["entry"] or int(post.get("visibility_id",0))!=3: raise SystemExit("GM post read-back failed.")
 r={"published":True,"created":created,"organization":final["name"],"entity_id":eid,"overview_url":f"https://app.kanka.io/w/{CID}/entities/{eid}","gm_post":post["name"],"gm_post_id":pid,"gm_post_created":pc,"gm_visibility_id":3}
 a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2))
if __name__=="__main__":main()
