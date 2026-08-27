"""
Generate three inconsistent 'legacy' HR sources, the way they actually arrive:
a HRIS extract, a payroll export, and an org hierarchy from a different system.

Faults are injected deliberately and at a known rate. Without them the
rejection path never runs and the reconciliation report is a page of zeros.
Every fault below is one that shows up in real HR migrations.
"""
import csv
import random
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

random.seed(20260906)  # deterministic: same faults every run, so counts are comparable

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

N_WORKERS = 300

FIRST = ["Aroha", "Wiremu", "Mere", "Tane", "Sione", "Ana", "Ravi", "Priya", "James",
         "Sarah", "Chen", "Li", "Mohammed", "Fatima", "Hemi", "Kiri", "Tom", "Ella"]
LAST = ["Ngata", "Smith", "Patel", "Wong", "Tui", "Brown", "Kaur", "Silva", "Taylor",
         "Nguyen", "Williams", "Ropata", "Ahmed", "Jones", "Kim", "Fa'alogo"]
TITLES = ["Lecturer", "Senior Lecturer", "Professor", "Technician", "Administrator",
          "Research Fellow", "Analyst", "Project Manager", "Librarian", "Cleaner"]
DEPTS = ["Computer Science", "Registry", "Library", "Facilities", "Human Resources",
         "Physics", "Student Services", "Finance"]
PAY_GROUPS = ["ACAD-MTH", "GEN-FTN", "CASUAL-WK"]


def fmt_date(d, style):
    """Legacy systems never agree on a date format. Neither do these."""
    if d is None:
        return ""
    if style == 0:
        return d.strftime("%Y-%m-%d")
    if style == 1:
        return d.strftime("%d/%m/%Y")
    if style == 2:
        return d.strftime("%d-%b-%Y")
    return str((d - date(1899, 12, 30)).days)  # Excel serial


def build_workers():
    workers = []
    for i in range(1, N_WORKERS + 1):
        wid = f"E{i:05d}"
        hire = date(2009, 1, 1) + timedelta(days=random.randint(0, 6000))
        terminated = random.random() < 0.18
        term = hire + timedelta(days=random.randint(200, 3000)) if terminated else None
        if term and term > date(2026, 8, 1):
            term = None
        workers.append({
            "employee_id": wid,
            "first_name": random.choice(FIRST),
            "last_name": random.choice(LAST),
            "hire_date": hire,
            "termination_date": term,
            "job_title": random.choice(TITLES),
            "department": random.choice(DEPTS),
            "manager_id": None,
            "employment_type": random.choice(["Permanent", "Fixed Term", "Casual"]),
            "fte": random.choice([1.0, 1.0, 1.0, 0.8, 0.5, 0.6]),
        })

    # assign managers from among the workers
    ids = [w["employee_id"] for w in workers]
    for w in workers:
        if random.random() < 0.9:
            m = random.choice(ids)
            w["manager_id"] = m if m != w["employee_id"] else None
    return workers


def write_hris(workers):
    """FAULTS: duplicate IDs with conflicting data, orphan manager refs,
    inconsistent department casing/whitespace, invalid FTE, mixed date formats."""
    rows = []
    for w in workers:
        style = random.choice([0, 0, 1, 2, 3])
        dept = w["department"]
        r = random.random()
        if r < 0.08:
            dept = "  " + dept.upper() + " "      # whitespace + case drift
        elif r < 0.14:
            dept = dept.lower()

        fte = w["fte"]
        if random.random() < 0.015:
            fte = random.choice([-1.0, 1.8, 0.0])  # out-of-range FTE

        mgr = w["manager_id"]
        if random.random() < 0.02:
            mgr = f"E{random.randint(9000, 9999):05d}"  # manager who does not exist

        rows.append({
            "employee_id": w["employee_id"],
            "first_name": w["first_name"],
            "last_name": w["last_name"],
            "hire_date": fmt_date(w["hire_date"], style),
            "termination_date": fmt_date(w["termination_date"], style),
            "job_title": w["job_title"],
            "department": dept,
            "manager_id": mgr or "",
            "employment_type": w["employment_type"],
            "fte": fte,
        })

    # duplicate employee IDs carrying conflicting attributes
    for w in random.sample(rows, k=int(N_WORKERS * 0.03)):
        dup = dict(w)
        dup["job_title"] = random.choice(TITLES)
        dup["fte"] = random.choice([1.0, 0.5])
        rows.append(dup)

    random.shuffle(rows)
    p = DATA / "hris_workers.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    return len(rows)


def write_payroll(workers):
    """FAULTS: payroll for unknown employees, pay periods after termination,
    missing/zero/negative salary, cost centre whitespace and case drift."""
    by_id = {w["employee_id"]: w for w in workers}
    rows = []
    for w in workers:
        for _ in range(random.randint(1, 3)):
            start = w["hire_date"] + timedelta(days=random.randint(0, 2000))
            end = start + timedelta(days=30)
            salary = round(random.uniform(48000, 145000), 2)

            r = random.random()
            if r < 0.02:
                salary = ""            # missing
            elif r < 0.03:
                salary = 0             # zero
            elif r < 0.035:
                salary = -salary       # negative

            cc = f"CC-{random.randint(1000, 1099)}"
            if random.random() < 0.1:
                cc = " " + cc.lower() + "  "

            rows.append({
                "employee_id": w["employee_id"],
                "pay_period_start": fmt_date(start, random.choice([0, 1])),
                "pay_period_end": fmt_date(end, random.choice([0, 1])),
                "annual_salary": salary,
                "currency": random.choice(["NZD", "NZD", "NZD", "nzd"]),
                "cost_centre": cc,
                "pay_group": random.choice(PAY_GROUPS),
            })

    # payroll rows for employees who are not in the HRIS extract at all
    for _ in range(int(N_WORKERS * 0.02)):
        rows.append({
            "employee_id": f"E{random.randint(9000, 9999):05d}",
            "pay_period_start": fmt_date(date(2024, 5, 1), 0),
            "pay_period_end": fmt_date(date(2024, 5, 31), 0),
            "annual_salary": round(random.uniform(50000, 90000), 2),
            "currency": "NZD",
            "cost_centre": "CC-1050",
            "pay_group": "GEN-FTN",
        })

    # pay periods that start after the worker was terminated
    terminated = [w for w in workers if w["termination_date"]]
    for w in random.sample(terminated, k=min(8, len(terminated))):
        after = by_id[w["employee_id"]]["termination_date"] + timedelta(days=60)
        rows.append({
            "employee_id": w["employee_id"],
            "pay_period_start": fmt_date(after, 0),
            "pay_period_end": fmt_date(after + timedelta(days=30), 0),
            "annual_salary": round(random.uniform(50000, 90000), 2),
            "currency": "NZD",
            "cost_centre": "CC-1001",
            "pay_group": "GEN-FTN",
        })

    random.shuffle(rows)
    p = DATA / "payroll_export.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    return len(rows)


def write_org_xml():
    """FAULT: one department points at a parent org that does not exist."""
    root = ET.Element("organisations")
    ids = {}
    for i, d in enumerate(DEPTS, start=1):
        oid = f"ORG-{i:03d}"
        ids[d] = oid
        e = ET.SubElement(root, "organisation")
        ET.SubElement(e, "org_id").text = oid
        ET.SubElement(e, "org_name").text = d
        ET.SubElement(e, "cost_centre").text = f"CC-{1000 + i}"
        parent = "ORG-001" if i > 1 else ""
        if d == "Facilities":
            parent = "ORG-999"          # orphan: parent does not exist
        ET.SubElement(e, "parent_org_id").text = parent

    p = DATA / "org_hierarchy.xml"
    ET.ElementTree(root).write(p, encoding="utf-8", xml_declaration=True)
    return len(DEPTS)


if __name__ == "__main__":
    workers = build_workers()
    h = write_hris(workers)
    p = write_payroll(workers)
    o = write_org_xml()
    print(f"hris_workers.csv    {h:>6} rows")
    print(f"payroll_export.csv  {p:>6} rows")
    print(f"org_hierarchy.xml   {o:>6} orgs")
