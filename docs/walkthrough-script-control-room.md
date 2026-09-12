# Walkthrough script: the Migration Control Room

A narration script for a screen-recorded walkthrough of
[the Migration Control Room](https://dinushitj.github.io/hr-migration-sandbox/), the
replay page this project generates. Written for a viewer with no technical background,
and timed at roughly 4 minutes read aloud at a natural pace.

Lines in square brackets are screen directions for whoever is recording. Everything else
is the spoken narration.

Pick a colour theme before recording. The page has a light and dark toggle in its top
left corner, and switching it mid-take is distracting.

---

[The Migration Control Room, loaded, nothing pressed yet.]

I'm going to walk you through something I built called the Migration Control Room. It's a
self-contained web page that replays a data migration I ran, so you can watch, step by
step, how nearly a thousand messy records get sorted into "this is fine," "this needs a
flag," or "this gets rejected."

Quick bit of context first. Imagine a company is moving to a new HR system. Before that
happens, someone has to take the old, messy data, spread across a few different systems
that don't quite agree with each other, and turn it into something clean enough to load
into the new one. That's called a data migration, and it's what this project practices.
Everything here is made-up data I generated myself. No real company and no real person is
involved.

[Scroll to "How a record travels".]

This diagram is the whole story in one picture. Three old files come in on the left: one
for staff records, one for pay, one for the org chart. They get copied in exactly as they
are, with nothing changed yet. That's the "staged" box. Then some values get cleaned up,
like fixing inconsistent date formats. Then everything gets checked against a set of
rules. And from there a record goes one of three ways: it passes and lands in the new
system, it gets rejected and set aside, or, and this is the interesting one, it gets
flagged, which means it's loaded anyway but with a note attached, because deleting it
would lose more information than keeping it with a warning.

[Press Run. Let several records play through.]

Now let's watch it happen. I'll press Run, and individual records flow through in real
time. Each one shows its raw details and then a verdict: loaded, flagged, or rejected,
along with the specific reason.

[Scroll slightly to the "Rule ledger" panel while the run continues.]

And this panel is why I can say that with a straight face. Every rule in the migration has
a number, and the ledger counts how many records each one caught. So if someone asks "why
was this record rejected," the answer is a specific rule, not "the system said so." You
can click any rule to see the records it stopped.

[Scroll to "Financial control total".]

This part is the one I'm proudest of. It's easy to check that the number of rows survived
a migration. It's much harder, and much more important, to check that the money did. So
this section adds up every dollar that came in from the original pay files and proves that
every one of them is accounted for at the end: either it made it into the new system, or
it's sitting in the rejected pile, itemised. The gap between those is called the residual,
and here it sits at exactly zero, to the cent. If even one salary had been quietly
miscalculated along the way, this is the check that would have caught it.

[Scroll to "Records by entity" and "Effective-dating integrity".]

Down here is the same story broken out by record type, staff, org structure and pay, and a
set of integrity checks confirming the data behaves the way a real HR system expects. For
example, that nobody ends up with two overlapping pay records covering the same period.

[Scroll to the data browser tabs: Before, After, Quarantine, Cleansed.]

And finally, a browsable table of the actual records. You can look at any record before
the migration, after it, the full list of what got rejected and why, or everything that
got cleaned up along the way. Nothing is hidden or summarised away.

[Back to the top. End.]

So that's the Migration Control Room: a way of making a data migration visible and
checkable, rather than something you have to take on trust. Thanks for watching.

---

## Recording notes

- Pause a second or two after each screen direction before speaking, so the movement
  lands before the narration covers it.
- The run has a speed control offering 1x, 8x, 40x and Max. If the recording restarts the
  replay, let it finish or push it to Max before narrating any section that quotes a
  number, so what is on screen matches what is being said.
- Consider on-screen captions for the rule identifiers, such as `CMP-007`, so a viewer
  who pauses can read them.
