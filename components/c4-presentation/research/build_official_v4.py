"""Build the three main official-service graphs and their demo wording from the SAME definitions, so the graph and the wording cannot drift.

  python research/build_official_v4.py

Writes, for each service, the planner inputs (research/data/official/<folder>/plan.json and enrichment.json: source-attached passages,
conditions, branches, prerequisites) and the demo-accepted 3.1 wording (research/data/guidance/provisional-v31/<plan_id>.json).
Sources are the official pages listed in SOURCES (retrieved 22 October 2026). The passages are short paraphrases written for this
snapshot; every number and name in the wording must occur in them, and the automatic checks in app.guidance.provisional gate the output.
The wording is AI-assisted, has no human or agency review, and is accepted only for the local research demonstration.
Earlier versions (official-*-v3) are untouched research evidence; these are new immutable versions with new identifiers.
"""
import json
import sys
from pathlib import Path

C4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C4 / "service"))
from app.guidance import provisional  # noqa: E402
from app.guidance.content_v31 import GuidanceContent31  # noqa: E402
from app.guidance.sources import ProcedureSource  # noqa: E402
from app.core.procedure_graph import build_procedure_graph  # noqa: E402
from app.core.procedure_input import load_procedure_input  # noqa: E402

STAMP = "2026-10-22T09:00:00Z"
OFFICIAL = C4 / "research" / "data" / "official"


def prose(*lines):
    return " ".join(lines)


def fact(role, phrase, fid, qualification=None, qual_phrase=None):
    return {"role": role, "phrase": phrase, "fact_id": fid, "qualification": qualification, "qual_phrase": qual_phrase}


# --------------------------------------------------------------------------------------------------------------------- BIRTH CERTIFICATE COPY
RGD = "https://www.rgd.gov.lk/web/index.php/en/services/civil-registration/birth/obtain-certified-copies-translations"
RGD_CHARGES = "https://www.rgd.gov.lk/web/index.php/en/services/civil-registration/birth/charges"
GIC_BIRTH = "https://gic.gov.lk/services/citizens-registrations/birth/obtain-a-certified-copy-of-the-certificate-of-birth"
BIRTH_PAY = "at the Divisional Secretariat or at the Registrar General's Bank of Ceylon branch at Battaramulla"
BIRTH_SUBMIT = prose("Submit the completed application with the bank slip to the Divisional Secretariat of the place of birth.",
                     "For delivery by post, enclose a stamped, self-addressed envelope.",
                     "If the birth is registered you receive as many copies as you paid for; if it is not registered you are notified on Form B38.")
BIRTH = {
    "folder": "birth_copy_v4", "plan_id": "official-birth_copy-v4", "service": "svc:birth_certificate_copy", "key": "birth_certificate_copy",
    "stage": "Birth certificate copy: counter application", "agency": "Registrar General's Department",
    "fee": (120, "Recorded base charge for one copy when no search of the records is needed"),
    "documents": ["Completed application form", "Bank slip (payment receipt)", "Stamped, self-addressed envelope"],
    "sources": {"rgd": (RGD, "Get the form from the Registrar Division of any DS"), "charges": (RGD_CHARGES, "a search of records is not required"),
                "search": (RGD_CHARGES, "a search of records for a period of not more than two years is required"),
                "atm": (RGD, "Payments made via Automated Teller Machines (ATMs) or Online payments will not be accepted")},
    "scope": prose("Manually curated official-source snapshot retrieved 22 October 2026 from the Registrar General's Department pages on obtaining certified copies and on charges;",
                   "not independently validated, not live output, and not an official application service.",
                   "Scope: the counter application for a certified copy of a birth certificate through a Divisional Secretariat.",
                   "The separate online eBMD application, with its own payment instructions, is a different channel and is not covered.",
                   "An older Government Information Centre page lists Rs. 100 and Rs. 200 for the same two cases; the Registrar General's Department figures of Rs. 120 and Rs. 250 are used.",
                   "Verify current requirements with the department."),
    "conditions": {"known": ("The birth certificate number and registration date are known, so no search of the records is needed.", "charges"),
                   "search": ("The number or date is not known, so a search of the records for up to two years is needed.", "search")},
    "actions": [
        {"id": "form", "heading": "Get the application form", "src": "rgd",
         "text": "Get the application form from the Registrar Division of any Divisional Secretariat, or download it from the Registrar General's Department website.",
         "concise": "Collect the form from any Divisional Secretariat, or download it from the department's website.",
         "detailed": "Get the application form from the Registrar Division of any Divisional Secretariat, or download it from the website of the Registrar General's Department. You can collect it from any office; you submit it later to the one for the place of birth.",
         "supplement": "You do not have to collect it from the office where you will submit it: the Registrar Division of any Divisional Secretariat can give it to you.",
         "recap": "You looked at where to get the application form.",
         "dest": ("Registrar Division of any Divisional Secretariat", "Registrar Division of any Divisional Secretariat"), "facts": []},
        {"id": "complete", "heading": "Complete the application", "src": "rgd",
         "text": "Complete the application for the Divisional Secretariat of the place of birth, giving the birth certificate number and registration date if you know them, because this decides which charge applies.",
         "concise": "Fill in the form, giving the birth certificate number and registration date if you know them.",
         "detailed": "Complete the application for the Divisional Secretariat of the place of birth. If you know the birth certificate number and registration date, give them: this decides which charge applies, because a search of the records costs more than a copy from a known entry.",
         "supplement": "If you are not sure of the number or date, you can still apply; you then follow the search route in the next step.",
         "recap": "You looked at completing the application and why the number and date matter.",
         "facts": [fact("prepare", "Complete the application", "svc:birth_certificate_copy:document:0")]},
        {"id": "pay_known", "heading": "Pay the charge for a known entry", "src": "charges", "cond": "known",
         "text": prose("If the birth certificate number and registration date are known, pay Rs. 120 per copy", BIRTH_PAY + ", and keep the bank slip.",
                      "Payments by ATM or online are not accepted."),
         "concise": "Pay Rs. 120 per copy and keep the bank slip.",
         "detailed": "When the birth certificate number and registration date are known, the charge is Rs. 120 per copy. Pay it at the Divisional Secretariat or at the Registrar General's Bank of Ceylon branch at Battaramulla, and keep the bank slip: you submit it with the application. ATM and online payments are not accepted.",
         "supplement": "The charge is per copy, so multiply by the number of copies you want before you pay.",
         "recap": "You looked at paying Rs. 120 per copy and keeping the bank slip.",
         "dest": (BIRTH_PAY, "Divisional Secretariat or the Registrar General's Bank of Ceylon branch, Battaramulla"),
         "facts": [fact("pay", "pay Rs. 120 per copy", "svc:birth_certificate_copy:fee", "Per copy. ATM and online payments are not accepted.", "Payments by ATM or online are not accepted"),
                   fact("keep", "keep the bank slip", "svc:birth_certificate_copy:document:1")]},
        {"id": "submit_known", "heading": "Submit the application and bank slip", "src": "rgd", "cond": "known", "text": BIRTH_SUBMIT,
         "concise": "Submit the completed application and bank slip to the Divisional Secretariat of the place of birth.",
         "detailed": "Take the completed application and the bank slip to the Divisional Secretariat of the place of birth. For delivery by post, enclose a stamped, self-addressed envelope. If the birth is registered you receive as many copies as you paid for; if it is not registered you are notified on Form B38.",
         "supplement": "The copies are issued only if the birth is found in the register, so a notification on Form B38 is a possible outcome rather than an error.",
         "recap": "You looked at submitting the application and bank slip, and what you receive.",
         "dest": ("to the Divisional Secretariat of the place of birth", "Divisional Secretariat of the place of birth"),
         "facts": [fact("submit", "the completed application", "svc:birth_certificate_copy:document:0"), fact("submit", "the bank slip", "svc:birth_certificate_copy:document:1"),
                   fact("bring", "a stamped, self-addressed envelope", "svc:birth_certificate_copy:document:2", "Only if you want the copies sent by post.", "For delivery by post")]},
        {"id": "pay_search", "heading": "Pay the charge when a search is needed", "src": "search", "cond": "search",
         "text": prose("If the number or date is not known and a search of the records for up to two years is needed, pay Rs. 250 for the first copy and Rs. 120 for each additional copy",
                      BIRTH_PAY + ", and keep the bank slip. Payments by ATM or online are not accepted."),
         "concise": "Pay Rs. 250 for the first copy and Rs. 120 for each extra copy, and keep the bank slip.",
         "detailed": "When a search of the records for up to two years is needed, the charge is Rs. 250 for the first copy and Rs. 120 for each additional copy. Pay it at the Divisional Secretariat or at the Registrar General's Bank of Ceylon branch at Battaramulla, and keep the bank slip: you submit it with the application. ATM and online payments are not accepted.",
         "supplement": "The Rs. 250 first-copy charge applies because a search of the records is required; it is not charged when the number and date are known.",
         "recap": "You looked at paying when a search is needed and keeping the bank slip.",
         "dest": (BIRTH_PAY, "Divisional Secretariat or the Registrar General's Bank of Ceylon branch, Battaramulla"),
         "facts": [fact("keep", "keep the bank slip", "svc:birth_certificate_copy:document:1")]},
        {"id": "submit_search", "heading": "Submit the application and bank slip", "src": "rgd", "cond": "search", "text": BIRTH_SUBMIT,
         "concise": "Submit the completed application and bank slip to the Divisional Secretariat of the place of birth.",
         "detailed": "Take the completed application and the bank slip to the Divisional Secretariat of the place of birth. For delivery by post, enclose a stamped, self-addressed envelope. If the birth is registered you receive as many copies as you paid for; if it is not registered you are notified on Form B38.",
         "supplement": "The copies are issued only if the birth is found in the register, so a notification on Form B38 is a possible outcome rather than an error.",
         "recap": "You looked at submitting the application and bank slip, and what you receive.",
         "dest": ("to the Divisional Secretariat of the place of birth", "Divisional Secretariat of the place of birth"),
         "facts": [fact("submit", "the completed application", "svc:birth_certificate_copy:document:0"), fact("submit", "the bank slip", "svc:birth_certificate_copy:document:1"),
                   fact("bring", "a stamped, self-addressed envelope", "svc:birth_certificate_copy:document:2", "Only if you want the copies sent by post.", "For delivery by post")]},
    ],
    "prereq": [("form", "complete"), ("complete", "submit_known"), ("complete", "submit_search"), ("pay_known", "submit_known"), ("pay_search", "submit_search")],
    "branches": [("branch:birth_fee", "known", [["pay_known", "submit_known"], ["pay_search", "submit_search"]], ["known", "search"], "rgd")],
    "phases": [("phase:prepare", "Get and complete the form", ["form", "complete"], "The form must be obtained and completed before it can be submitted."),
               ("phase:pay_submit", "Pay and submit", ["pay_known", "submit_known", "pay_search", "submit_search"], "Payment and submission follow once the application is complete; the two fee cases are alternatives.")],
}

# --------------------------------------------------------------------------------------------------------------------- NIC AMENDMENT
DRP = "https://drp.gov.lk/en/normal.php"
NIC_RECEIVE = prose("After certification the application goes to the District Secretariat's ID card division, which forwards it to the Department.",
                    "Under the normal service the amended card is then sent to you by registered post.")
NIC_ONE_DAY = ("The department also offers a one-day service in person at its Head Office in Battaramulla or at the Galle Provincial Office. It is arranged separately and has its own fee, "
               "so read the one-day section of the department's page before you choose it.")
NIC = {
    "split_note": "Your route decides which of these steps apply to you.",
    "supp_passages": {"one_day": NIC_ONE_DAY},
    "folder": "nic_amendment_v4", "plan_id": "official-nic_amendment-v4", "service": "svc:nic_amendment_card", "key": "nic_amendment_card",
    "stage": "NIC amendment: estate and non-estate routes", "agency": "Department for Registration of Persons",
    "fee": (500, "Recorded fee for an amended National Identity card"),
    "documents": ["Completed application (Form D.R.P/1,7,8)", "Previously used National Identity card", "Birth certificate or certified birth-register extract",
                  "ICAO-standard photograph taken within the last 6 months", "Receipt for the application fee",
                  "Probable age certificate or register search results, with proof of name and date of birth",
                  "Affidavit, recognised written evidence and register search results (applicants over 40)", "Citizenship certificate (born abroad to a Sri Lankan parent)",
                  "Dual citizenship certificate", "Clergy documents", "Attested marriage certificate (using a husband's name or surname)"],
    "sources": {"amend": (DRP, "It is mandatory for every applicant to forward the application through the relevant certifying officer"), "countersign": (DRP, "Counter signature of the Divisional Secretary is mandatory"),
                "docs": (DRP, "Duly completed application (Form D.R.P/1,7,8)")},
    "scope": prose("Manually curated official-source snapshot retrieved 22 October 2026 from the Amending National Identity card section of the Department for Registration of Persons page;",
                   "not independently validated, not live output, and not an official application service.",
                   "Scope: amending an existing card under the normal service through a certifying officer, with the one-day service mentioned only as a separate in-person option.",
                   "First-issue and lost-card procedures are different services. The age threshold for the affidavit requirement is 40 in this section but 50 in the page's first-issue section,",
                   "and the affidavit paragraph contains a stray '(delete)' marker, so that requirement should be confirmed with the department. Verify current requirements with the department."),
    "conditions": {"estate": ("The applicant is an estate resident seeking an NIC amendment.", "amend"), "non_estate": ("The applicant is not an estate resident and seeks an NIC amendment.", "amend")},
    "actions": [
        {"id": "docs_core", "heading": "Prepare your application and core documents", "src": "docs",
         "text": prose("Prepare the completed amendment application (Form D.R.P/1,7,8), the previously used National Identity card, a birth certificate or a birth-register extract certified by the Additional District Registrar,",
                      "and an ICAO-standard photograph taken within the last 6 months."),
         "concise": "Prepare the completed application, your old NIC, your birth certificate and a recent photograph.",
         "detailed": "Prepare the completed amendment application (Form D.R.P/1,7,8), the National Identity card you have been using, a birth certificate or a birth-register extract certified by the Additional District Registrar, and an ICAO-standard photograph taken within the last 6 months. These are the documents everyone needs; the next step covers extra evidence some people must add.",
         "supplement": "The department's page links the application form (Form D.R.P/1,7,8) as a download.",
         "recap": "You looked at the core documents for the application.",
         "facts": [fact("prepare", "the completed amendment application (Form D.R.P/1,7,8)", "svc:nic_amendment_card:document:0"), fact("bring", "the previously used National Identity card", "svc:nic_amendment_card:document:1"),
                   fact("prepare", "a birth certificate or a birth-register extract certified by the Additional District Registrar", "svc:nic_amendment_card:document:2"),
                   fact("prepare", "an ICAO-standard photograph taken within the last 6 months", "svc:nic_amendment_card:document:3")]},
        {"id": "docs_extra", "heading": "Check whether you need extra evidence", "src": "docs",
         "text": prose("Some applicants must add further evidence: a probable age certificate or register search results with proof of name and date of birth if there is no birth certificate;",
                      "an affidavit, recognised written evidence and register search results for applicants over 40 with neither;",
                      "a citizenship certificate for those born abroad to a Sri Lankan parent; a dual citizenship certificate where it applies; clergy documents where they apply;",
                      "and an attested marriage certificate when using a husband's name or surname."),
         "concise": "Add extra evidence only if one of the listed circumstances applies to you.",
         "detailed": "The core documents are enough unless one of these circumstances applies: you have no birth certificate, you were born abroad to a Sri Lankan parent, you hold dual citizenship, you are clergy, or you want to use a husband's name or surname. Each case has its own document, shown on the card with the circumstance it belongs to.",
         "supplement": "An applicant who has a birth certificate and none of the other listed circumstances adds nothing more to the core documents.",
         "recap": "You looked at which extra evidence applies to different circumstances.",
         "facts": [fact("prepare", "a probable age certificate or register search results with proof of name and date of birth", "svc:nic_amendment_card:document:5", "Only if you have no birth certificate.", "if there is no birth certificate"),
                   fact("prepare", "an affidavit, recognised written evidence and register search results", "svc:nic_amendment_card:document:6", "Only for applicants over 40 who have neither a birth certificate nor a probable age certificate.", "for applicants over 40 with neither"),
                   fact("prepare", "a citizenship certificate", "svc:nic_amendment_card:document:7", "Only if you were born abroad to a Sri Lankan parent.", "for those born abroad to a Sri Lankan parent"),
                   fact("prepare", "a dual citizenship certificate", "svc:nic_amendment_card:document:8", "Only where it applies to you.", "where it applies"),
                   fact("prepare", "clergy documents", "svc:nic_amendment_card:document:9", "Only where they apply to you.", "where they apply"),
                   fact("prepare", "an attested marriage certificate", "svc:nic_amendment_card:document:10", "Only if you want to use a husband's name or surname.", "when using a husband's name or surname")]},
        {"id": "estate_certify", "heading": "Have it certified by the Estate Superintendent", "src": "amend", "cond": "estate",
         "text": prose("If you live on an estate, forward the application through the Estate Superintendent, who certifies it.",
                      "Pay the Rs. 500 amended-card fee through the certifying officer and keep the receipt. Registered-post delivery under the normal service adds Rs. 120."),
         "concise": "Forward your application through the Estate Superintendent and pay the fee there.",
         "detailed": "Because you live on an estate, forward the application and your documents through the Estate Superintendent, who certifies it. Pay the Rs. 500 amended-card fee through the same certifying officer and keep the receipt, which is one of the documents the department requires. Registered-post delivery under the normal service adds Rs. 120.",
         "supplement": "Every applicant must forward the application through the certifying officer, so applying directly to the department is not an alternative for the normal service.",
         "recap": "You looked at certification and payment through the Estate Superintendent.",
         "dest": ("through the Estate Superintendent", "Estate Superintendent"),
         "facts": [fact("pay", "Pay the Rs. 500 amended-card fee", "svc:nic_amendment_card:fee", "Paid through the certifying officer. Registered-post delivery under the normal service adds Rs. 120.", "Registered-post delivery under the normal service adds Rs. 120"),
                   fact("keep", "keep the receipt", "svc:nic_amendment_card:document:4")]},
        {"id": "estate_receive", "heading": "Receive your amended card", "src": "amend", "cond": "estate", "text": NIC_RECEIVE,
         "concise": "Wait for the amended card, which is sent to you by registered post.",
         "detailed": "After certification your application goes to the District Secretariat's ID card division, which forwards it to the Department for Registration of Persons. Under the normal service the amended card is then sent to you by registered post.",
         "supplement": NIC_ONE_DAY, "supp": "one_day", "recap": "You looked at how the amended card reaches you.", "facts": []},
        {"id": "gn_certify", "heading": "Have it certified by your Grama Niladhari", "src": "amend", "cond": "non_estate",
         "text": prose("If you do not live on an estate, forward the application through the Grama Niladhari for your area of residence, who certifies it.",
                      "Pay the Rs. 500 amended-card fee through the certifying officer and keep the receipt. Registered-post delivery under the normal service adds Rs. 120."),
         "concise": "Forward your application through your Grama Niladhari and pay the fee there.",
         "detailed": "Because you do not live on an estate, forward the application and your documents through the Grama Niladhari for your area of residence, who certifies it. Pay the Rs. 500 amended-card fee through the same certifying officer and keep the receipt, which is one of the documents the department requires. The Divisional Secretary then countersigns, as the next step explains.",
         "supplement": "Every applicant must forward the application through the certifying officer, so applying directly to the department is not an alternative for the normal service.",
         "recap": "You looked at certification and payment through the Grama Niladhari.",
         "dest": ("through the Grama Niladhari for your area of residence", "Grama Niladhari for your area"),
         "facts": [fact("pay", "Pay the Rs. 500 amended-card fee", "svc:nic_amendment_card:fee", "Paid through the certifying officer. Registered-post delivery under the normal service adds Rs. 120.", "Registered-post delivery under the normal service adds Rs. 120"),
                   fact("keep", "keep the receipt", "svc:nic_amendment_card:document:4")]},
        {"id": "ds_countersign", "heading": "Divisional Secretary's countersignature", "src": "countersign", "cond": "non_estate",
         "text": "The Divisional Secretary must countersign the application certified by the Grama Niladhari; the countersignature is mandatory.",
         "concise": "Ask the Divisional Secretary to countersign the application your Grama Niladhari certified.",
         "detailed": "After the Grama Niladhari certifies the application, the Divisional Secretary must countersign it. The countersignature is mandatory for the non-estate route and is in addition to the Grama Niladhari's certification, not a substitute for it.",
         "supplement": "The countersignature is needed for the application certified by the Grama Niladhari; the estate route does not have this step.",
         "recap": "You looked at the Divisional Secretary's countersignature.",
         "dest": ("The Divisional Secretary must countersign", "Divisional Secretary"), "facts": []},
        {"id": "gn_receive", "heading": "Receive your amended card", "src": "amend", "cond": "non_estate", "text": NIC_RECEIVE,
         "concise": "Wait for the amended card, which is sent to you by registered post.",
         "detailed": "After certification and countersignature your application goes to the District Secretariat's ID card division, which forwards it to the Department for Registration of Persons. Under the normal service the amended card is then sent to you by registered post.",
         "supplement": NIC_ONE_DAY, "supp": "one_day", "recap": "You looked at how the amended card reaches you.", "facts": []},
    ],
    "prereq": [("docs_core", "estate_certify"), ("docs_core", "gn_certify"), ("gn_certify", "ds_countersign"), ("estate_certify", "estate_receive"), ("ds_countersign", "gn_receive")],
    "branches": [("branch:nic_route", "estate", [["estate_certify", "estate_receive"], ["gn_certify", "ds_countersign", "gn_receive"]], ["estate", "non_estate"], "amend")],
    "phases": [("phase:prepare", "Prepare your documents", ["docs_core", "docs_extra"], "Both steps assemble the documents that go with the application."),
               ("phase:certify", "Certification and payment", ["estate_certify", "gn_certify", "ds_countersign"], "Certification through the certifying officer follows the preparation of the application; the two routes are alternatives."),
               ("phase:receive", "Receive your card", ["estate_receive", "gn_receive"], "The card is issued after certification.")],
}

# --------------------------------------------------------------------------------------------------------------------- TIN
IRD_PDF = "https://www.ird.gov.lk/en/Downloads/SiteAssets/TPR_Guidelines_2026_E.pdf"
IRD_REG = "https://www.ird.gov.lk/en/eservices/sitepages/registration.aspx?menuid=1801"
TIN_SUBMIT = prose("Submit your TIN registration through the IRD e-Services portal, which the 2026 taxpayer guideline names as the way to obtain a TIN.",
                   "The department's registration page also describes registering in person or by post; the IRD Call Centre on 1944 can confirm which options you can use.",
                   "The older service description lists no application form fee and no service fee.")
TIN_SUPPLEMENT = ("Registering for a TIN is separate from registering for tax types. After you have a TIN you register only for the taxes that apply to you, such as income tax or VAT, "
                  "so do not assume you must register for all of them.")
TIN = {
    "split_note": "Only the steps for your applicant category apply to you.",
    "folder": "tin_registration", "plan_id": "official-tin_registration-v1", "service": "svc:tin_registration", "key": "tin_registration",
    "stage": "Taxpayer ID (TIN): by applicant category", "agency": "Inland Revenue Department",
    "fee": (0, "Application form and service fee listed as nil in the older GIC service description"),
    "documents": ["NIC (Sri Lankans) or valid passport (foreign nationals)", "Business registration certificate (if a proprietorship is to be added)",
                  "Proof of address: utility bill, bank statement or passbook, or Grama Niladhari certificate", "Partnership registration certificate",
                  "NIC or valid passport of every partner", "Certificate of Incorporation (Form 2A, 2D, 42, 41 etc.)", "Form 01, 05 or 40 certified by the Registrar of Companies",
                  "All Form 20s certified by the Registrar of Companies", "NIC or valid passport of all directors", "Articles of Association",
                  "Form 13 certified by the Registrar of Companies (if applicable)", "Form 18 certified by the Registrar of Companies (where applicable)",
                  "Board of Investment registration certificate and relevant agreement"],
    "sources": {"docs": (IRD_PDF, "Supporting Documents required for obtaining a TIN"), "reg": (IRD_REG, "Register as a Taxpayer and get your Taxpayer Identification Number (TIN), in person, through post, or online")},
    "scope": prose("Manually curated official-source snapshot retrieved 22 October 2026 from the 2026 Inland Revenue Department taxpayer guideline (TIN section) and its registration overview page,",
                   "cross-checked against an older Government Information Centre service description supplied for this project; not independently validated, not live output, and not an official application service.",
                   "Scope: obtaining a TIN as an individual, a partnership or a registered company. Other entity types (institutions, branches, joint ventures, projects, trusts) have separate document lists in the guideline and are not covered.",
                   "Counter hours, the 20-minute service time and the old tax-category names in the older description are historical and are not used. The registration overview page was last updated in 2020.",
                   "In the 2026 guideline the wording of the Form 18 condition was only partly readable in the copy used, so that document is marked as applying only where applicable. Verify current requirements with the department."),
    "conditions": {"a_individual": ("The applicant is an individual, including a proprietor.", "docs"), "b_partnership": ("The applicant is a partnership.", "docs"),
                   "c_company": ("The applicant is a registered company.", "docs")},
    "actions": [
        {"id": "individual_docs", "heading": "Prepare your identity and address documents", "src": "docs", "cond": "a_individual",
         "text": prose("Individuals prepare their NIC (Sri Lankans) or valid passport (foreign nationals).",
                      "Add the business registration certificate if a proprietorship is to be added, and proof of address (a utility bill, a bank statement or passbook, or a Grama Niladhari certificate) if the address is different from the NIC.",
                      "Foreign nationals need a local address proof."),
         "concise": "Prepare your NIC or passport, plus proof of address if it differs from your NIC.",
         "detailed": "Prepare your NIC if you are a Sri Lankan, or a valid passport if you are a foreign national. Add the business registration certificate only if a proprietorship is to be added, and proof of address (a utility bill, a bank statement or passbook, or a Grama Niladhari certificate) only if your address is different from the one on your NIC. Foreign nationals need a local address proof.",
         "supplement": "The older service description says that photocopies of the supporting documents accompany the application.",
         "recap": "You looked at the documents an individual needs.",
         "facts": [fact("prepare", "their NIC (Sri Lankans) or valid passport (foreign nationals)", "svc:tin_registration:document:0"),
                   fact("prepare", "the business registration certificate", "svc:tin_registration:document:1", "Only if a proprietorship is to be added.", "if a proprietorship is to be added"),
                   fact("prepare", "proof of address (a utility bill, a bank statement or passbook, or a Grama Niladhari certificate)", "svc:tin_registration:document:2", "Only if the address is different from the NIC. Foreign nationals need a local address proof.", "if the address is different from the NIC")]},
        {"id": "individual_submit", "heading": "Submit your TIN registration", "src": "reg", "cond": "a_individual", "text": TIN_SUBMIT,
         "concise": "Submit your TIN registration through the IRD e-Services portal.",
         "detailed": "Submit your TIN registration through the IRD e-Services portal, which the 2026 taxpayer guideline names as the way to obtain a TIN. The department's registration page also describes registering in person or by post, and the IRD Call Centre on 1944 can confirm which options you can use. The older service description lists no application form fee and no service fee.",
         "supplement": TIN_SUPPLEMENT, "recap": "You looked at how to submit the registration.",
         "dest": ("through the IRD e-Services portal", "IRD e-Services portal"),
         "facts": [fact("charge", "no application form fee and no service fee", "svc:tin_registration:fee", "As listed in the older GIC service description; the 2026 guideline does not restate a fee.", "The older service description lists")]},
        {"id": "partnership_docs", "heading": "Prepare your partnership documents", "src": "docs", "cond": "b_partnership",
         "text": "Partnerships prepare the partnership registration certificate and the NIC (Sri Lankans) or valid passport (foreign nationals) of all the partners.",
         "concise": "Prepare the partnership registration certificate and every partner's NIC or passport.",
         "detailed": "Prepare the partnership registration certificate, and the NIC of every partner who is a Sri Lankan or a valid passport for every partner who is a foreign national. The identity documents are needed for all the partners, not only for the person submitting the registration.",
         "supplement": "Collect the partners' identity documents early, since you need them all before you can submit.",
         "recap": "You looked at the documents a partnership needs.",
         "facts": [fact("prepare", "the partnership registration certificate", "svc:tin_registration:document:3"),
                   fact("prepare", "the NIC (Sri Lankans) or valid passport (foreign nationals) of all the partners", "svc:tin_registration:document:4")]},
        {"id": "partnership_submit", "heading": "Submit your TIN registration", "src": "reg", "cond": "b_partnership", "text": TIN_SUBMIT,
         "concise": "Submit your partnership's TIN registration through the IRD e-Services portal.",
         "detailed": "Submit the partnership's TIN registration through the IRD e-Services portal, which the 2026 taxpayer guideline names as the way to obtain a TIN. The department's registration page also describes registering in person or by post, and the IRD Call Centre on 1944 can confirm which options you can use. The older service description lists no application form fee and no service fee.",
         "supplement": TIN_SUPPLEMENT, "recap": "You looked at how to submit the registration.",
         "dest": ("through the IRD e-Services portal", "IRD e-Services portal"),
         "facts": [fact("charge", "no application form fee and no service fee", "svc:tin_registration:fee", "As listed in the older GIC service description; the 2026 guideline does not restate a fee.", "The older service description lists")]},
        {"id": "company_docs", "heading": "Prepare your company documents", "src": "docs", "cond": "c_company",
         "text": prose("Registered companies prepare the Certificate of Incorporation (Form 2A, 2D, 42, 41 etc.), Form 01, 05 or 40 certified by the Registrar of Companies, all Form 20s certified by the Registrar of Companies,",
                      "the NIC or valid passport of all directors, and the Articles of Association.",
                      "Form 13 certified by the Registrar of Companies is needed if applicable, and Form 18 certified by the Registrar of Companies where applicable.",
                      "A Board of Investment registration certificate and the relevant agreement are listed for companies that have them."),
         "concise": "Prepare your Certificate of Incorporation, the certified company forms and the directors' identity documents.",
         "detailed": "Prepare the Certificate of Incorporation (Form 2A, 2D, 42, 41 etc.), Form 01, 05 or 40 certified by the Registrar of Companies, all Form 20s certified by the Registrar of Companies, the NIC or valid passport of all directors, and the Articles of Association. Add Form 13 only if it applies to your company, Form 18 only where it applies, and a Board of Investment registration certificate with its agreement only if your company has them.",
         "supplement": "Not every form the guideline names applies to every company: Form 13 and Form 18 are marked as applicable only in some cases.",
         "recap": "You looked at the documents a registered company needs.",
         "facts": [fact("prepare", "the Certificate of Incorporation (Form 2A, 2D, 42, 41 etc.)", "svc:tin_registration:document:5"),
                   fact("prepare", "Form 01, 05 or 40 certified by the Registrar of Companies", "svc:tin_registration:document:6"),
                   fact("prepare", "all Form 20s certified by the Registrar of Companies", "svc:tin_registration:document:7"),
                   fact("prepare", "the NIC or valid passport of all directors", "svc:tin_registration:document:8"),
                   fact("prepare", "the Articles of Association", "svc:tin_registration:document:9"),
                   fact("prepare", "Form 13 certified by the Registrar of Companies is needed if applicable", "svc:tin_registration:document:10", "Only if it applies to your company.", "if applicable"),
                   fact("prepare", "Form 18 certified by the Registrar of Companies where applicable", "svc:tin_registration:document:11", "Only where it applies to your company.", "where applicable"),
                   fact("prepare", "A Board of Investment registration certificate and the relevant agreement", "svc:tin_registration:document:12", "Only for companies that have them.", "for companies that have them")]},
        {"id": "company_submit", "heading": "Submit your TIN registration", "src": "reg", "cond": "c_company", "text": TIN_SUBMIT,
         "concise": "Submit your company's TIN registration through the IRD e-Services portal.",
         "detailed": "Submit the company's TIN registration through the IRD e-Services portal, which the 2026 taxpayer guideline names as the way to obtain a TIN. The department's registration page also describes registering in person or by post, and the IRD Call Centre on 1944 can confirm which options you can use. The older service description lists no application form fee and no service fee.",
         "supplement": TIN_SUPPLEMENT, "recap": "You looked at how to submit the registration.",
         "dest": ("through the IRD e-Services portal", "IRD e-Services portal"),
         "facts": [fact("charge", "no application form fee and no service fee", "svc:tin_registration:fee", "As listed in the older GIC service description; the 2026 guideline does not restate a fee.", "The older service description lists")]},
    ],
    "prereq": [("individual_docs", "individual_submit"), ("partnership_docs", "partnership_submit"), ("company_docs", "company_submit")],
    "branches": [("branch:tin_category", "individual", [["individual_docs", "individual_submit"], ["partnership_docs", "partnership_submit"], ["company_docs", "company_submit"]], ["a_individual", "b_partnership", "c_company"], "docs")],
    "phases": [("phase:documents", "Prepare your documents", ["individual_docs", "partnership_docs", "company_docs"], "Each applicant category first assembles its own documents."),
               ("phase:submit", "Submit your registration", ["individual_submit", "partnership_submit", "company_submit"], "Submission follows once the documents for your category are ready.")],
}

SERVICES = (BIRTH, NIC, TIN)


def evidence_id(key):
    return "evidence:" + key


def plan_and_enrichment(s):
    fid = lambda n: f"{s['service']}:document:{n}"
    fee_id = s["service"] + ":fee"
    # Fact provenance: every fact comes from the cited pages.
    source_of = {"birth_certificate_copy": RGD, "nic_amendment_card": DRP, "tin_registration": IRD_PDF}[s["key"]]
    fee_source = {"birth_certificate_copy": RGD_CHARGES, "nic_amendment_card": DRP, "tin_registration": "https://gic.gov.lk/"}[s["key"]]
    provenance = {fee_id: {"source_url": fee_source, "retrieved_at": STAMP}}
    for n in range(len(s["documents"])):
        provenance[fid(n)] = {"source_url": source_of, "retrieved_at": STAMP}
    plan = {"plan_id": s["plan_id"], "requested_service_id": s["service"], "generated_at": STAMP,
            "steps": [{"order": 1, "service_id": s["service"], "name": s["stage"], "agency": s["agency"], "fee": {"value": s["fee"][0], "currency": "LKR", "fact_id": fee_id},
                       "documents": [{"name": d, "fact_id": fid(n)} for n, d in enumerate(s["documents"])], "depends_on": []}],
            "provenance": provenance}
    evidence, content, actions, conditions = {}, [], [], []
    for k, (url, anchor) in s["sources"].items():
        evidence[k] = {"evidence_id": evidence_id(k), "kind": "source_passage", "source_url": url, "text": "Short source anchor: " + anchor, "retrieved_at": STAMP}
    first_src = next(iter(s["sources"]))
    content.append({"content_id": "content:scope", "role": "required", "text": s["scope"], "evidence_ids": [evidence_id(first_src)], "fact_ids": []})
    for key, (text, src) in s["conditions"].items():
        conditions.append({"condition_id": "condition:" + key, "text": text, "evidence_ids": [evidence_id(src)]})
    extra = s.get("supp_passages", {})
    for key, text in extra.items():
        content.append({"content_id": "content:" + key, "role": "supplementary", "text": text, "evidence_ids": [evidence_id(next(iter(s["sources"])))], "fact_ids": []})
    for a in s["actions"]:
        fact_ids = sorted({f["fact_id"] for f in a["facts"]})
        content.append({"content_id": "content:" + a["id"], "role": "required", "text": a["text"], "evidence_ids": [evidence_id(a["src"])], "fact_ids": fact_ids})
        actions.append({"action_id": "action:" + a["id"], "service_id": s["service"], "required_content_ids": ["content:" + a["id"], "content:scope"], "supplementary_content_ids": ["content:" + a["supp"]] if a.get("supp") else [],
                        "condition_ids": []})
    prereq = [{"prerequisite_id": f"prerequisite:{i}", "kind": "requires_completion", "required_action_id": "action:" + r, "dependent_action_id": "action:" + d,
               "evidence_ids": [evidence_id(first_src if s["key"] != "nic_amendment_card" else "amend")]} for i, (r, d) in enumerate(s["prereq"])]
    branches = []
    for gid, _first, options, conds, src in s["branches"]:
        branches.append({"group_id": gid, "service_id": s["service"], "selection": "XOR",
                         "options": [{"option_id": f"option:{c}", "action_ids": ["action:" + x for x in acts], "condition_ids": ["condition:" + c]} for acts, c in zip(options, conds)],
                         "evidence_ids": [evidence_id(src)]})
    enrichment = {"schema_version": "1.0", "plan_id": s["plan_id"], "base_generated_at": STAMP, "synthetic": False, "disclaimer": s["scope"], "actions": actions, "content": content,
                  "evidence": list(evidence.values()), "conditions": conditions, "prerequisites": prereq, "branch_groups": branches, "parallel_groups": [],
                  "completeness": {"service_dependencies": "complete", "actions": "complete", "content": "complete", "conditions": "complete", "branch_groups": "complete",
                                   "prerequisites": "complete", "parallel_groups": "unknown"}}
    return plan, enrichment


def provisional_content(s, source):
    g = source.graph
    passages = {c.content_id: c for c in g.content}
    claims, actions, attachments = [], [], []
    by_id = {}
    for a in s["actions"]:
        aid = "action:" + a["id"]
        cid = "content:" + a["id"]
        p = passages[cid]
        scope = passages["content:scope"]
        ev = list(p.evidence_ids)
        core = []
        for i, (c, kind) in enumerate(((p, "instruction"), (scope, "qualification"))):
            claims.append({"id": f"{aid}:claim:{i}", "source_kind": "content", "source_id": c.content_id, "start": 0, "end": len(c.text), "quote": c.text, "action_ids": [aid], "required": True,
                           "kind": kind, "evidence_ids": list(c.evidence_ids)})
            core.append(f"{aid}:claim:{i}")
        raw = p.text + "\n\n" + scope.text
        t = lambda text, ids=(): {"text": text, "status": "draft", "claim_ids": list(ids), "evidence_ids": ev}
        action = {"id": aid, "heading": t(a["heading"]), "heading_actionable": True, "source_wording": {"text": raw, "status": "source_fallback", "claim_ids": core, "evidence_ids": ev},
                  "concise": t(a["concise"], core), "detailed": t(a["detailed"], core), "supplement": {"text": t(a["supplement"]), "role": "clarification", "adds_information": True},
                  "recap": t(a["recap"]), "actor": None, "destination": None, "visible_condition_ids": [], "visible_attachment_ids": []}
        actions.append(action)
        by_id[aid] = action
        for n, f in enumerate(a["facts"]):
            if f["phrase"] not in p.text:
                raise ValueError(f"{aid}: phrase not in passage: {f['phrase']}")
            start = p.text.index(f["phrase"])
            kind = "fee" if f["fact_id"].endswith(":fee") else "document"
            claim = {"id": f"{aid}:{kind}:{n}", "source_kind": "content", "source_id": cid, "start": start, "end": start + len(f["phrase"]), "quote": f["phrase"], "action_ids": [aid], "required": False, "kind": kind, "evidence_ids": ev}
            claims.append(claim)
            qualification = None
            if f["qualification"]:
                qp = f["qual_phrase"]
                if qp not in p.text:
                    raise ValueError(f"{aid}: qualification phrase not in passage: {qp}")
                qs = p.text.index(qp)
                qclaim = {"id": f"{aid}:qualification:{n}", "source_kind": "content", "source_id": cid, "start": qs, "end": qs + len(qp), "quote": qp, "action_ids": [aid], "required": False, "kind": "qualification", "evidence_ids": ev}
                claims.append(qclaim)
                qualification = {"text": f["qualification"], "status": "draft", "claim_ids": [qclaim["id"]], "evidence_ids": ev}
            att = {"id": f"attachment:{aid}:{f['fact_id'].split(':', 2)[2]}", "fact_id": f["fact_id"], "scope": "action", "action_id": aid, "stage_id": None, "service_id": None, "branch_id": None, "option_ids": [], "condition_ids": [],
                   "claim_ids": [claim["id"]], "evidence_ids": ev, "qualification": qualification, "status": "draft", "role": f["role"]}
            attachments.append(att)
            action["visible_attachment_ids"].append(att["id"])
        if a.get("dest"):
            phrase, label = a["dest"]
            if phrase not in p.text:
                raise ValueError(f"{aid}: destination phrase not in passage: {phrase}")
            start = p.text.index(phrase)
            claim = {"id": f"{aid}:destination", "source_kind": "content", "source_id": cid, "start": start, "end": start + len(phrase), "quote": phrase, "action_ids": [aid], "required": False, "kind": "destination", "evidence_ids": ev}
            claims.append(claim)
            action["destination"] = {"text": label, "status": "draft", "claim_ids": [claim["id"]], "evidence_ids": ev}
    # Conditions must stay visible on conditional actions.
    for ga in g.actions:
        by_id[ga.action_id]["visible_condition_ids"] = list(ga.applicability.condition_ids)
    first_ev = list(passages["content:" + s["actions"][0]["id"]].evidence_ids)
    phase_defs = [{"id": pid, "label": {"text": label, "status": "draft", "claim_ids": [], "evidence_ids": first_ev}, "action_ids": ["action:" + x for x in members], "basis": "purpose",
                   "why_grouped": why, "adds_orientation": True, "evidence_ids": first_ev,
                   "branch_split_note": s.get("split_note")} for pid, label, members, why in s["phases"]]
    content = {"schema_version": "c4-guidance-content-3.1", "procedure_id": s["plan_id"], "language": "en", "source_graph_fingerprint": source.graph_fingerprint,
               "relationship_fingerprint": source.relationship_fingerprint, "content_version": "demo-accepted-v4-1", "origin": "demo_mock", "source_limit": g.disclaimer, "claims": claims,
               "actions": actions, "attachments": attachments, "phases": phase_defs, "phase_order": [], "phase_order_basis": "none",
               "phase_order_evidence_ids": [], "review": None}
    return content


def main():
    for s in SERVICES:
        plan, enrichment = plan_and_enrichment(s)
        folder = OFFICIAL / s["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "enrichment.json").write_text(json.dumps(enrichment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        graph = build_procedure_graph(load_procedure_input(folder / "plan.json", folder / "enrichment.json"))
        source = ProcedureSource(graph=graph).validate()
        content = provisional_content(s, source)
        model = GuidanceContent31.model_validate(content)
        report = provisional.check(source, model)
        packet = {"procedure_id": s["plan_id"], "status": "provisional_demo_only", "label": provisional.LABEL,
                  "provenance": "Authored with AI assistance from the official pages cited in the planner inputs (research/data/official/" + s["folder"] + "). No human, expert or government review; accepted by the project owner for the local research demonstration only.",
                  "automatic_checks": report, "content": content}
        (provisional.PROVISIONAL_DIR / (s["plan_id"] + ".json")).write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(s["plan_id"], "checks passed" if report["passed"] else "ISSUES", report["grounding_and_contradiction_issues"], "structural:", report["structural"])


if __name__ == "__main__":
    main()
