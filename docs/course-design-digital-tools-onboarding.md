# Course design note: Digital Tools Onboarding

A design for a small self-paced course covering a new staff member's first week with
their core digital tools. It is written as a practice piece, built in the public
[Moodle demo sandbox](https://moodle.org/demo) to work through the structural and
accessibility decisions a real onboarding course would need, not as delivered training.

Total learner time is deliberately small, roughly 30 to 45 minutes. The interesting part
of a course this size is not its content volume; it is whether the structure holds up,
whether the pattern repeats predictably, and whether a learner can find the one thing they
came for without reading the rest.

## Structure

### Section 0: Welcome

A short `Page` resource, three or four sentences in plain language: what the course
covers and how long it takes. Plus a "How to use this course" note stating that it is
self-paced, has no facilitator, can be completed in any order, and naming where to go
when stuck.

Stating "complete in any order" up front is a design decision, not a disclaimer. It
commits the rest of the course to being genuinely modular, which is what stops section 3
from quietly depending on section 1.

### Section 1: Your core tools

One short `Page` per tool, each following the same three-part template:

> What it is for, one thing to try today, where to get help.

Covering Outlook for email and calendar, Teams for chat and meetings, and
OneDrive with SharePoint for files and sharing.

Each page carries three or four annotated screenshots rather than embedded video.
Screenshots are far faster to produce and revise, they are searchable, and a learner
skimming for one answer does not have to scrub through a video to find it. Video earns
its place when the thing being taught is a sequence of motions; most of this is not.

One low-stakes `Quiz` closes the section, three to five multiple-choice questions of the
form "Where would you save a file you want your whole team to access?". It demonstrates
a knowledge-check pattern. It does not gate progress, because a first-week onboarding
course is the wrong place to make someone fail something.

### Section 2: AI tools at work

Two pages. One on which AI tools are approved and available. One on responsible use,
specifically what should not be pasted into an AI tool, such as personal or confidential
data.

The second page is the one that matters. Adoption guidance that covers capability but not
boundaries pushes the hard question onto the learner at exactly the moment they are least
equipped to answer it.

### Section 3: Where to go next

A short FAQ page in the same plain-language style as
[this project's FAQ](../FAQ.md), and a "Get help" page naming the self-service channel,
the service desk contact, and how to give feedback on the course itself.

### Section 4: Wrap-up

Activity completion tracking, so a learner can see what they have finished. Core Moodle
handles this; the commonly suggested `Checklist` activity is a third-party plugin and is
not available on the demo site.

One optional `Feedback` activity, two or three questions: was this clear, what was
missing. This is the piece most worth building even in a mock course, because a resource
with no feedback path cannot be improved except by guesswork.

## Design decisions worth defending

- **One repeated template per tool.** The value is in the standard, not the pages. A
  consistent shape means a new tool can be added by someone else without a style debate,
  and a learner who has read one page knows how to read the next.
- **Short and skimmable over comprehensive.** This mirrors how self-service content is
  actually used. People arrive with one question and leave once they have the answer.
- **A feedback loop from the start, not bolted on.** Included in the first version rather
  than added after the first complaint.
- **Accessibility applied throughout, not audited afterwards.** Descriptive page titles;
  heading levels that nest without skipping; alt text on every screenshot describing what
  it shows rather than "screenshot 1"; and link text that names its destination, never
  "click here". The same standards are applied and measured against this project's own
  published pages in [the accessibility review](accessibility-review.md).

## Build notes

The public Moodle demo site resets periodically, so a finished course should be captured
in screenshots as it is built. The demo teacher login is sufficient to create everything
described here.
