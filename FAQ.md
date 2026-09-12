# Frequently Asked Questions

*This page explains the HR Data Migration Sandbox in plain English, no technical
background needed. If you just want to look at the finished result, open
[the live replay of a migration run](https://dinushitj.github.io/hr-migration-sandbox/).*

---

## What is this, in one sentence?

It's a practice project I built myself that copies messy, made-up HR and payroll records
from three old-style systems into one clean, correctly-structured target, the way a real
company would move data when it switches HR systems (for example, onto Workday).

## Is this real company data?

No. Every record is invented by a script on my computer: fake names, fake salaries, fake
departments. Nothing here comes from a real employer, and no real person's information was
ever involved. I built it specifically so I could demonstrate the *process* of a data
migration without touching anything sensitive.

## Why did you build it?

To show, concretely, how I think about moving and checking data. Not just "I've used SQL
before," but: how do you decide what to keep, what to flag, and what to reject when three
different systems disagree with each other? Screenshots and a CV bullet point can't really
show that; a working example can.

## What does "data migration" actually mean here?

Imagine a company has three old files: one lists staff details, one lists what everyone
gets paid, and one lists the org chart. They don't quite agree: some dates are typed in
different formats, a few people appear twice, a few payroll rows belong to people who've
already left. The migration is the process of reading all three, deciding what's
trustworthy, fixing what can be safely fixed, and loading the result into one clean
system, while keeping a record of every decision made along the way.

## What happens to the records that don't make it in?

Every record that fails a check is set aside, not deleted, with three things attached:
*which* rule stopped it, *why*, and the original record exactly as it arrived. That
set-aside pile is what the project calls "quarantine." Nothing disappears silently; anyone
reviewing the run afterwards can see exactly what was rejected and why.

Some records are a judgement call rather than a clear pass/fail, for example, a staff
record whose manager can't be found. Rather than deleting it, the record is loaded *and*
flagged, because a person with no listed manager is more useful in the system than a
person deleted from it entirely. The project is upfront about how many records fall into
each of these categories, rather than only reporting the tidy ones.

## How do you know nothing got lost or silently changed?

Two ways. First, every value the process *cleans up* (like standardising a date format) is
logged with what it looked like before and after, so the change is visible rather than
hidden inside the process. Second, and more importantly, the project adds up every dollar
in the original payroll files and checks that the total is accounted for at the end,
either loaded into the new system or listed in the quarantine pile, down to the cent. If a
single dollar went missing or was silently altered, that check would catch it. Counting
rows isn't enough for this; a salary that got quietly cut in half would still "count" as
one row.

## What's the "Migration Control Room" page?

It's a self-contained web page that replays one complete run of the process, record by
record. It has Run, Step and Reset buttons, a speed selector and a scrubber you can drag
to any point in the run, so moving through it feels like scrubbing through a video. It
shows each record as it's checked, whether it passed, was flagged, or was rejected (and
why), a running tally of the money check above, and a browsable table of every record
before and after. You can
[open the Migration Control Room](https://dinushitj.github.io/hr-migration-sandbox/).

## What does this actually demonstrate about how I work?

- Reading messy, real-world-shaped data and making it trustworthy rather than just
  "making it run."
- Writing down *why* a decision was made (a rule ID, a reason, the original record) so
  someone else can check my work later.
- Checking the things that are easy to get quietly wrong, like assuming a dollar total
  survived a transformation just because the row count did.
- Being upfront about limitations rather than only showing what worked (see the "Known
  issues" section in the main [README](README.md); I list defects I found by auditing my
  own finished build).

## What are the honest limitations of this project?

It's a personal sandbox, not production experience with a live system:

- The data is entirely synthetic.
- The target is *shaped* like Workday's data model, but has never actually been loaded
  into a Workday system.
- There's no real approval process behind the cleaning rules. In a real migration, those
  decisions would be signed off by the people who actually own the HR and payroll data,
  not decided solely by the person writing the code.

I think stating that plainly is part of demonstrating good practice, not a weakness to
hide.

## Where can I see the code or run it myself?

The full project, including the step-by-step instructions, is in the
[main README](README.md).
