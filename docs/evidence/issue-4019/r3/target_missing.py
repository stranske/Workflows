import json,sys
d=json.load(open(sys.argv[1]))
t=d["totals"];n=t["num_statements"]+t["num_branches"];c=t["covered_lines"]+t["covered_branches"]
print("TOTAL",c,n,100*c/n)
tot=0
for f in ["scripts/aggregate_agent_metrics.py","scripts/check_consumer_sync_drift.py","tools/llm_provider.py"]:
    s=d["files"][f]["summary"];m=s["missing_lines"]+s["missing_branches"];tot+=m
    print(f,s["missing_lines"],"+",s["missing_branches"],"=",m, d["files"][f]["missing_lines"], d["files"][f].get("missing_branches"))
print("TARGET_MISSING",tot)
