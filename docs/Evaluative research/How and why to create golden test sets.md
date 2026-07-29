Camp one trusts AI outputs most of the time. If it looks coherent, and the findings sound plausible, it seems good enough to roll with.

Camp two trusts almost nothing, and spends the hours AI just saved combing back through the data by hand, re-doing AI’s work to be 100% sure it’s right.

Both are extreme, not ideal, and I don’t want either one for you. But most people I work with are in camp two, and there’s a big piece of the puzzle missing in their workflows that leaves them there.

They need to get systematic about testing their AI and their workflows, so they know what can and can’t be trusted before a real decision is riding on it.

I’ve talked a little bit about testing workflows and tools more systematically before. This time, we’re talking about an essential tool that is required for nearly every test you might want to run:

Golden test sets.

Maybe you’re thinking, I already have data, do I really need some other version of it? This feels like overkill. My answer is almost always yes.

A few places your golden test sets earn the time it takes to create them (please don’t hate me for giving you a little extra work 🙃):

A new model released — everyone swears it’s smarter. A golden test set tells you whether it does your specific task better, or if it just sounds more confident while missing the same things. Without one, you’re guessing.

You rewrite a prompt or agent instructions — did it sharpen the output, or break something you won’t catch until it’s already in a deck? You find out before a stakeholder does.

You’re deciding whether to keep checking by hand — once a workflow clears the bar, you trust it, spot check in specific places (not everywhere) and move on. The test set is what earns that trust: it shows the findings lined up where they mattered repeatedly, even if the AI got a few minor details wrong.

This edition covers what a golden test set is, how many you need, and how to build your first one this week.

In this edition:
📍 New from me — Episode with Patricia Reiners coming soon! + June Claude Code course enrollment ends in 5 days.

🏕️ What’s a golden test set? — diagnose where you are, with the smallest next move at each rung

🗺️ Build your first golden test set next week - do it now, not later. Use it forever.

Let’s get into it —

📍 New from me
Future of UX podcast episode coming soon!
I just recorded an episode with Patricia Reiners last week all about files. Yes, files. Like, the files Claude Code and agents need to do really good work. (I promise it’s more interesting than it sounds). Episode coming soon.

Follower her and find our chat, soon, over here: Apple Podcasts, Spotify

Claude Code for Customers Insights - enrollment ends in 5 days
Last cohort built 16+ real research workflows together — Cohort 3 runs June 8–19, and enrollment is closing....

→ Sign up here

And did you know you get a subscriber-only discount to this course? Email me if you want it!

🏕️ BASE CAMP
What a golden test set actually is
You run a new prompt or instructions set on your data. The output looks believable, so you send it along to your stakeholders.

“Looks right” tells you the output is coherent. It tells you nothing about whether it’s correct — whether the AI found what you would have, or missed the nuance that changes the decision. The only way to know is to compare it against an answer you already trust.

That’s what a golden test set gives you: it’s a study where you already know the “right answers” you’d ideally like to replicate with AI. It has the right findings, right themes, right counts, right prioritization of what to work on next based on findings — all so you can hold any new prompt, process, or model against a tangible bar instead of using gut feels.

GOLDEN = the answer key exists before you run the test.

You did the study by hand and trust the result — the findings, the surprises, the things you’d flag in a junior’s first draft. New AI output either matches that key, or it doesn’t.

The anatomy: five folders
Every test set I keep has the same five folders inside:

Why it matters: the structure is the boring part, but it’s what makes testing a 15-minute habit instead of a giant project each time. When every study looks the same, you can choose a new model or experiment setup but you’ll know exactly where the answer key is waiting.

How many test sets do you need?
Start with three — but before you ask, I bet “three of what?” is your follow-up, so…

→ A test set belongs to a workflow.

❌ The question isn’t “how many data types should we create golden test sets of?”

✅ It should be, “what’s the range this one workflow will be used and trusted on?”

You build enough sets to cover that range for that repeatable workflow, and the dimension worth covering is the one most likely to break it.

One workflow, one data type (say, thematic synthesis of interviews) → three sets that might cover easy, typical, and very messy or complicated data or topics.

One workflow, several data types (the same synthesis run on interviews, survey open-ends, and support tickets) → cover the types instead: then you need a few sets of each, weighted toward the messiest formats. .

You don’t need three of every type all the time. Three interview sets plus three survey sets plus three ticket sets is the best combo for a multi-source workflow, but if all of your data sets are pretty much exactly the same, you might also be proving the same thing nine times (and not testing the model’s on something more likely to make it struggle). So use your common sense here, too, and not just my numbers.

Here’s a simple decision tree for checking how many sets to target:

“How granular do I go? Separate sets for JTBD interviews vs. exploratory interviews?”
Split by failure mode, not by topic. Ask: would the workflow break differently on this?

JTBD synthesis and usability issue-spotting are entirely different jobs — different methodology, different workflow instructions, different right answers. Each earns its own test set coverage.

JTBD interviews about onboarding vs. about billing are the same job and methodology (JTBD) on different topics. One set probably covers both well enough.

The rule: add a set only when you can name a new way the workflow could break that your current sets wouldn’t catch. If you can’t name the failure, you’re being too granular — which is why, for most small teams, this still end up at three to five total sets, not thirty.

How many times to run each one:
It’s three again! AI output shifts from run to run, so a single pass is an anecdote, not a test. Run your workflow against a golden set three times. If it clears all three you can trust it; if it clears two, you’ve got a reliability gap to close before it touches live work.

“But this will take too long.”
It’s time well spent, I promise. Plus let’s be honest: skipping the test was not saving us time - it costs us a wrong finding shipped into a roadmap, or the hours you’ll spend re-reading transcripts to check if our AI workflow actually worked.

Curious what my folders look like? This 👇

🗺️ THE ROUTE
Build your first golden test set this week
Three is the target, but you’ll build them one at a time. For most of us, this looks like filling in documentation gaps for a study you already ran, so start there.

1. Pick a study you know well
   The best first test set is a study where you’d notice if the AI got it wrong -- a past project you ran end-to-end and still remember well: the key finding that wasn’t obvious, the quote that reframed the whole study for stakeholders, the point a stakeholder pushed back on but had a lot of evidence.

Skip studies you only skimmed. If you can’t confidently grade the output, it can’t be your answer key.

2. Strip it so you can sleep at night
   I always advise teams to anonymize and remove PII to the level your legal sense and your gut both sign off on — while keeping enough that the analysis still means something.
3. Write the answer key
   This is the part that makes it golden, and the part most people skip.

Open your 00 folder and write down, in plain language in a doc:

The findings — what the study found.

The surprises — what you didn’t expect going in.

The junior-analyst flags — what you’d correct if someone handed you a first-pass draft: missed the secondary theme, overweighted one loud participant, called a one-off a pattern.

That third bullet is a valuable addition, don’t skip it if you have time. It’s the difference between “the AI produced themes” and “the AI produced the right themes without the mistakes a rushed human would make.”

f
