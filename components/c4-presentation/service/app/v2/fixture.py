"""Rebuild the explicitly fictional V2 research fixture; no official facts."""
import copy
import json
from pathlib import Path
from app.core.procedure_input import load_procedure_input
from app.core.procedure_graph import build_procedure_graph
from app.core.scaffolds import graph_fingerprint

root = Path(__file__).resolve().parents[3] / "research" / "data"
p = json.loads((root / "fixtures/parallel/plan.json").read_text())
e = json.loads((root / "fixtures/parallel/enrichment.json").read_text())
p["plan_id"] = e["plan_id"] = "synthetic-practice-v2"
p["steps"][-1]["name"] = "Practice application: prepare and submit"
e["parallel_groups"] = []
e["prerequisites"] = [r for r in e["prerequisites"] if r["prerequisite_id"] != "prerequisite:copy_before_submission"]
copy_action = next(a for a in e["actions"] if a["action_id"] == "action:prepare_copy")
copy_action["condition_ids"] = ["condition:have_copy"]
office_action = copy.deepcopy(copy_action)
office_action.update(action_id="action:obtain_copy", required_content_ids=["content:obtain_copy"], condition_ids=["condition:no_copy"])
e["actions"].insert(3, office_action)
e["conditions"] = [{"condition_id": "condition:have_copy", "text": "You already have the fictional supporting copy.", "evidence_ids": ["evidence:application_rules"]},
                   {"condition_id": "condition:no_copy", "text": "You do not have the fictional supporting copy.", "evidence_ids": ["evidence:application_rules"]}]
e["branch_groups"] = [{"group_id": "branch:copy_route", "service_id": "svc:demo_preparation", "selection": "XOR", "evidence_ids": ["evidence:application_rules"],
    "options": [{"option_id": "option:own", "action_ids": ["action:prepare_copy"], "condition_ids": ["condition:have_copy"]},
                {"option_id": "option:office", "action_ids": ["action:obtain_copy"], "condition_ids": ["condition:no_copy"]}]}]
e["prerequisites"].append({"prerequisite_id": "prerequisite:registration_before_office", "kind": "requires_completion", "required_action_id": "action:register_application", "dependent_action_id": "action:obtain_copy", "evidence_ids": ["evidence:application_rules"]})
texts = {
 "register_application": ("Register the practice application", "Register at the fictional Registration Desk before preparing the form or supporting copy. Each of registration, preparation and submission has a fictional LKR 0 fee. After registration, the form and the applicable copy route may proceed independently; both are required before submission.", "Registration is the common prerequisite for both preparation work areas. The copy routes are alternatives, while the form is required in either route."),
 "prepare_form": ("Prepare the form", "After registration, prepare the fictional application form. It can be prepared independently of the applicable supporting-copy route. Both items are required for submission.", "Form preparation does not replace copy preparation. You can work on either preparation area first after registration."),
 "prepare_copy": ("Prepare your existing copy", "If you already have the fictional supporting copy, prepare it after registration. Use this route instead of obtaining a copy at the Records Desk. Form preparation can proceed independently.", "This is one of two alternative copy routes. Submission still requires the form as well as this copy."),
 "obtain_copy": ("Obtain a copy at the Records Desk", "If you do not have the fictional supporting copy, obtain it from the fictional Records Desk after registration. Use this route instead of preparing an existing copy. Form preparation can proceed independently.", "The Records Desk supplies the copy for this route. It does not prepare the application form; that separate preparation is still required."),
 "submit_application": ("Submit both prepared items", "Submit to the fictional Submission Desk only after preparing the form and completing the applicable copy route. Include both the fictional completed form and supporting copy. Completing just one preparation is insufficient.", "The final action joins two work areas: the form and one copy route. The two copy alternatives are not both required.")}
for c in e["content"]:
    key = c["content_id"].split(":")[1]
    if key in texts:
        c["text"] = texts[key][1]
e["content"].append({"content_id": "content:obtain_copy", "role": "required", "text": texts["obtain_copy"][1], "evidence_ids": ["evidence:application_rules"], "fact_ids": ["svc:demo_submission:document:copy"]})
e["evidence"][0]["text"] = "Authored fictional V2 rules. " + " ".join(t[1] + " " + t[2] for t in texts.values())
e["disclaimer"] = "Fictional practice procedure authored for C4 research. All desks and charges are fictional. Viewing guidance never confirms completion. This is not government advice."
folder = root / "v2/practice"
folder.mkdir(parents=True, exist_ok=True)
for name, value in (("plan", p), ("enrichment", e)):
    (folder / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
g = build_procedure_graph(load_procedure_input(folder / "plan.json", folder / "enrichment.json"))
overlay = {"schema_version": "c4-enrichment-v2.1", "graph_fingerprint": graph_fingerprint(g), "reviewer": "synthetic-fixture-author-v2; not official-source review",
 "variants": [{"action_id": a["action_id"], "title": texts[a["action_id"].split(":")[1]][0], "concise": texts[a["action_id"].split(":")[1]][1],
               "expanded": texts[a["action_id"].split(":")[1]][1] + "\n\n" + texts[a["action_id"].split(":")[1]][2], "recap": texts[a["action_id"].split(":")[1]][0],
               "required_content_ids": a["required_content_ids"], "evidence_ids": ["evidence:application_rules"]} for a in e["actions"]],
 "owners": [{"action_id": "action:" + k, "actor": actor, "evidence_ids": ["evidence:application_rules"]} for k, actor in (("register_application", "Fictional Registration Desk"), ("obtain_copy", "Fictional Records Desk"), ("submit_application", "Fictional Submission Desk"))],
 "joins": [{"target": "action:submit_application", "requirement": {"kind": "all_of", "children": [{"kind": "action", "ref": "action:prepare_form"}, {"kind": "selected_option_of", "ref": "branch:copy_route"}]}, "evidence_ids": ["evidence:application_rules"]}],
 "parallel_areas": [[{"kind": "action", "ref": "action:prepare_form"}, {"kind": "selected_option_of", "ref": "branch:copy_route"}]],
 "evidence_ids": ["evidence:application_rules"], "optional_content_ids": ["content:preparation_explanation"]}
(folder / "overlay.json").write_text(json.dumps(overlay, indent=2), encoding="utf-8")
