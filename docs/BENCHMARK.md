# What the Treetop benchmark shows

## Purpose

The Treetop benchmark asks one question of a model: given a large, demanding creative brief, can it produce a complete, working, beautiful piece of software in a single attempt, with no chance to run it, test it, or revise it?

Most coding evaluations reward short, verifiable answers.
Real work is rarely like that.
It is long, it mixes disciplines, it has an aesthetic bar as well as a functional one, and the first draft has to hold together.
This benchmark is built to expose the difference between a model that knows the words and a model that can actually build the thing.

Every model receives exactly the same brief and is judged on exactly the same thing: open the file it produced and look.

## The task

Each model is given [the brief](prompt.txt) and must answer with one self-contained HTML file.
The file has to render an interactive 3D treetop village using three.js, with every texture, model, and material generated in code.
No other libraries, no image files, no external assets.

The brief is deliberately large.
It asks for a forest of giant trees with realistic trunks and layered canopies.
It asks for a dozen varied dwellings on platforms, connected by sagging, swaying rope bridges, with staircases winding down to a living forest floor.
It asks for a communal hall, a lookout tower, and a working lift.
It asks for close-up props, animated villagers walking believable paths, birds in the air, and leaves or snow drifting through the scene.
It asks for two camera modes, a help overlay, and a full control panel driving time of day, season, fog, wind, population, random seed, and shadow quality.
And it sets a quality bar: cohesive storybook art direction, considered lighting, zero console errors, and a steady 60 fps.

Nothing in the brief is optional.
A model that nails the trees but skips the villagers has not finished.

Every run is given the same completion token budget, and thinking counts against it. A reply that exhausts the budget, or arrives without a complete document, is refused and never shown.

Most runs are served by hosted providers. Some models are run locally on consumer hardware, with quantised weights served by Ollama, so a local result reflects the machine as well as the model. The provenance note on each run records which kind it was and, for local runs, the hardware.

## What it covers

A strong result demands several distinct abilities at once.

- **Scale and completeness.** A serious answer runs to thousands of lines. The model has to plan the whole structure up front and carry it through without dropping features or leaving placeholders.
- **Correctness without a feedback loop.** The model never gets to run the page. Every JavaScript call and every line of GLSL has to be right first time.
- **Procedural craft.** Bark, shingles, planks, foliage, water, and smoke all have to come from code. This is where familiarity with real three.js idioms shows.
- **Spatial reasoning.** Platforms must sit on trunks, bridges must connect them with believable sag, stairs must wind down, and a first-person walker must be able to stand on all of it.
- **Performance judgment.** Twelve detailed buildings in seven detailed trees at 60 fps forces real choices about instancing, merged geometry, and level of detail.
- **Taste.** The brief rejects default primitives with flat colours. Palette, lighting, and composition are part of the result.
- **Instruction following.** One file, one library at one pinned version, no assets, no UI frameworks, and a specific list of controls. Every deviation is visible.

It does not measure conversation, tool use, or iterative debugging.
It is closer to an exam than to a pairing session.

## What it shows

Because every model answers the same brief and the output is something you can walk around inside, the differences between models become visible rather than statistical.

- **From far away**, whether a model composes a scene or scatters objects.
- **At mid range**, whether buildings, bridges, and villagers read as distinct things.
- **Up close**, whether planks, ropes, and window frames are modelled or merely painted on.
- **In motion**, whether bridges sway, smoke drifts with the wind, and villagers walk routes that make sense.
- **Under the controls**, whether night actually lights the lanterns, whether winter actually brings snow, and whether a new seed produces a different but equally coherent village.
- **In the console**, whether the file runs clean, which is the hard line between a result and a near miss.

Models that look similar on leaderboards can land very far apart here.
Some produce something you would happily show someone.
Some produce something that almost works.
Some produce something that never loads.

## How it is judged

There is no automated score.
Each result goes into this viewer to be put in front of a person.
Load one full screen to explore it, or put two side by side and let your eyes do the comparing.
[The brief](prompt.txt) is one click away in the Prompt panel so you can check a scene against what was actually asked for.

The right way to read a result is from the outside in: does it load, does the silhouette read, do the parts hold up close, do the controls do what they claim, and does it feel like one place rather than a pile of parts.
